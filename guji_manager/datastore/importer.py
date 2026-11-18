"""guji-workspace（某个 git 提交）→ 中心库（2026-11-18 起 Cloudflare D1，经 ``d1conn``），幂等（GUJI-603）。

做法：扫出该提交里每个工作区「应有的行」（scope.py），和库里现有的行按主键比
raw 的 sha256，只写有差别的；每写一行在 ``changes`` 记一条、分配全局递增的 rev。
同一提交重跑：0 写入，rev 不动。

D1 没有交互式事务和锁：先读（库版本、现有行的 row_sha）、在本机算好全部写入，退出事务时一批提交，
带「守卫」核对库版本没被别人动过（动过就整次不写、抛 ``d1conn.Stale``）。一次写得多会分几段提交，
每段自己原子、带守卫；数据行和它的 changes 记录总在同一段里，中途失败重跑即补齐（差分写）。
rev、import_id 不再由库里的序列发：按读到的库版本往上顺延（守卫保证没人插队）。

库里不算 sha256：每行存 ``row_sha``（= scope.fingerprint），差分直接比它。
整文件表 files 一行 raw＋doc 到 1.5 MB 时原文先传 R2（Worker ``/v1/file-bodies``），表里 raw 存空串、``body_r2=1``。

删除：某行在提交里没了 → 库里也删（镜像）。但 ``append_only`` 的台账（events、consumed、
anchors）发现要删行就中止，除非显式 ``allow_delete``——防止拿旧提交把新人裁冲掉。
行号变了但内容没变（字形库导出重排）只更新 src_line，不算变更、不记 rev。
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field

from . import gitsource
from .d1conn import JSON_COLS, Rollback, insert_stmts
from .d1sql import NOW
from .scope import TABLES, Row, ScanResult, fingerprint, scan_files, sha256

SCHEMA_FILE = "schema_d1.sql"
#: files 一行 raw＋doc 到这么大就把原文放 R2（D1 一行上限 2 MB；与 Worker files.ts ROW_BUDGET 同口径）
ROW_BUDGET = 1_500_000
R2_BODY_MIN = 1_000_000
#: 一段（一条 INSERT 的 JSON 参数）里行的大致字节上限
PIECE_BYTES = 1_200_000


class DeleteRefused(RuntimeError):
    pass


#: 字形库账本表：本地一整张表突然是空的、库里却有一大批，多半是本机 glyph.db／glyph_store 被删后重建成了空壳
#: （2026-11-04 殿本账本被清空，GUJI-事故）。这类删除即使是「整表缺」也不放行，除非 ``allow_delete``。
GLYPH_LEDGER_TABLES = frozenset({"glyphs", "glyph_exemplars", "glyph_admissions", "glyph_instances", "glyph_sources"})
LEDGER_EMPTIED_MIN = 50


def emptied_ledger(tbl: str, n_existing: int, n_local: int, n_deletes: int) -> bool:
    """库里 ``n_existing`` 行、本地只剩 ``n_local`` 行、要删 ``n_deletes`` 行：是不是「账本被清空」。
    改键重写（删得多但插得也多）不算：本地行数比库里少了 5% 以上、且删的行也到 5% 以上才算
    （2026-11-10 史記 6,465→3,554 是 55%，原先「一半」的门槛没拦住）。"""
    return (tbl in GLYPH_LEDGER_TABLES and n_existing >= LEDGER_EMPTIED_MIN
            and n_deletes * 20 >= n_existing and n_local * 20 < n_existing * 19)


def apply_schema(conn) -> None:
    """D1 的表结构由迁移／部署时建（``schema_d1.sql``，由 guji-workspace-data ``d1/gen_schema.py`` 生成），导入时不再建表。"""
    return None


def scan_commit(repo, commit: str, only_ws: set[str] | None = None) -> list[ScanResult]:
    tree = gitsource.list_tree(repo, commit)
    reader = gitsource.BlobReader(repo)
    try:
        out = []
        for d, files in gitsource.workspaces_in_tree(tree).items():
            items = [(rel, (lambda oid=oid: reader.read(oid))) for rel, oid in files]
            res = scan_files(items, d)
            if only_ws and res.ws not in only_ws and d not in only_ws:
                continue
            out.append(res)
        return out
    finally:
        reader.close()


# ─── 差分（纯函数，可单测） ─────────────────────────────────────────────

@dataclass
class Plan:
    inserts: list[Row] = field(default_factory=list)
    updates: list[Row] = field(default_factory=list)       # 内容变了
    moves: list[Row] = field(default_factory=list)         # 只是行号变了
    deletes: list[tuple] = field(default_factory=list)     # 主键（不含 ws）
    old_sha: dict[tuple, str] = field(default_factory=dict)

    @property
    def n_changes(self) -> int:
        return len(self.inserts) + len(self.updates) + len(self.deletes)


def diff(rows: list[Row], existing: dict[tuple, tuple[str, int]]) -> Plan:
    """``existing``：{主键: (fingerprint, src_line)}。"""
    plan = Plan()
    want: dict[tuple, Row] = {}
    for r in rows:
        want[r.key] = r                   # 主键重复：后者覆盖（scope 已记入问题）
    for k, r in want.items():
        old = existing.get(k)
        if old is None:
            plan.inserts.append(r)
        elif old[0] != fingerprint(r):
            plan.updates.append(r)
            plan.old_sha[k] = old[0]
        elif old[1] != r.src_line:
            plan.moves.append(r)
    for k, (sha, _) in existing.items():
        if k not in want:
            plan.deletes.append(k)
            plan.old_sha[k] = sha
    return plan


# ─── 读写库 ─────────────────────────────────────────────────────────────

def _columns(cur, tbl: str) -> list[tuple[str, str]]:
    """[(列名, 类型)]，按建表顺序。"""
    cur.execute("SELECT name, type FROM pragma_table_info(%s) ORDER BY cid", (tbl,))
    return [(r[0], "jsonb" if r[0] in JSON_COLS else str(r[1]).lower()) for r in cur.fetchall()]


def _pk_cols(tbl: str) -> list[str]:
    return ["ws", *TABLES[tbl].key]


def load_existing(cur, tbl: str, ws: str, paths: set[str] | None = None) -> dict[tuple, tuple[str, int]]:
    """``paths`` 给了就只取这些文件的行（``import_scans(only_paths=)``）。"""
    keys = TABLES[tbl].key
    sel = ", ".join(keys) + ", " if keys else ""
    where, args = "ws = %s", [ws]
    if paths is not None:
        where += " AND src_path = ANY(%s)"
        args.append(sorted(paths))
    cur.execute(f"SELECT {sel}row_sha, src_line FROM {tbl} WHERE {where}", args)
    n = len(keys)
    return {tuple(r[:n]): (r[n], r[n + 1]) for r in cur.fetchall()}


def _doc_json(doc) -> str | None:
    return None if doc is None else json.dumps(doc, ensure_ascii=False)


def body_in_r2(row: Row) -> bool:
    """files 这一行的原文要不要放 R2（与 Worker files.ts 同口径）。"""
    if row.tbl != "files":
        return False
    n = len(row.raw.encode("utf-8"))
    if n >= R2_BODY_MIN:
        return True
    d = _doc_json(row.doc)
    return n + (len(d.encode("utf-8")) if d and len(d.encode("utf-8")) < ROW_BUDGET else 0) >= ROW_BUDGET


def _record(row: Row, ws: str, rev: int, cols: list[tuple[str, str]]) -> tuple:
    base = {"ws": ws, "src_path": row.src_path, "src_line": row.src_line,
            "raw": row.raw, "rev": rev, "row_sha": fingerprint(row), "body_r2": 0}
    if TABLES[row.tbl].has_doc:
        base["doc"] = row.doc
        if row.tbl == "files" and row.doc is not None and len(_doc_json(row.doc).encode("utf-8")) >= ROW_BUDGET:
            base["doc"] = None
    if body_in_r2(row):
        base["raw"], base["body_r2"] = "", 1
    for k, v in zip(TABLES[row.tbl].key, row.key):
        base[k] = v
    base.update(row.cols)
    out = []
    for c, typ in cols:
        v = base.get(c)
        if v is not None and typ == "jsonb":
            v = json.dumps(v, ensure_ascii=False)
        elif isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False, sort_keys=True)
        out.append(v)
    return tuple(out)


def _pieces(rows: list, size=lambda r: len(r.raw.encode("utf-8")) * 2 + 300) -> list[list]:
    """按大致字节切段（一段的行和它们的 changes 一起提交）。"""
    out, part, n = [], [], 0
    for r in rows:
        k = size(r)
        if part and n + k > PIECE_BYTES:
            out.append(part)
            part, n = [], 0
        part.append(r)
        n += k
    if part:
        out.append(part)
    return out


def _upsert_stmts(typed, tbl: str, ws: str, rows: list[Row], revs: list[int]) -> list:
    cols = [c for c, _ in typed]
    pk = _pk_cols(tbl)
    upd = ", ".join(f"{c} = excluded.{c}" for c in cols if c not in pk)
    return insert_stmts(tbl, cols, [_record(r, ws, revs[i], typed) for i, r in enumerate(rows)],
                        conflict=f"ON CONFLICT ({', '.join(pk)}) DO UPDATE SET {upd}, ingested_at = {NOW}")


def _move_stmts(tbl: str, ws: str, rows: list[Row]) -> list:
    """只改行号（内容没变）。"""
    pk = _pk_cols(tbl)
    data = json.dumps([[ws, *r.key, r.src_line] for r in rows], ensure_ascii=False)
    cond = " AND ".join(f"{tbl}.{c} = j.value->>{i}" for i, c in enumerate(pk))
    return [(f"UPDATE {tbl} SET src_line = j.value->>{len(pk)} FROM json_each(?) AS j WHERE {cond}", [data])]


def _delete_stmts(tbl: str, ws: str, keys: list[tuple]) -> list:
    if not keys:
        return []
    pk = TABLES[tbl].key
    if not pk:
        return [(f"DELETE FROM {tbl} WHERE ws = ?", [ws])]
    sel = ", ".join(f"value->>{i}" for i in range(len(pk)))
    out = []
    for i in range(0, len(keys), 5000):
        data = json.dumps([list(k) for k in keys[i:i + 5000]], ensure_ascii=False)
        out.append((f"DELETE FROM {tbl} WHERE ws = ? AND ({', '.join(pk)}) IN (SELECT {sel} FROM json_each(?))",
                    [ws, data]))
    return out


class _Revs:
    """在守卫下顺延的 rev 号（代替 Postgres 序列）。"""

    def __init__(self, last: int):
        self.last = last

    def take(self, n: int) -> list[int]:
        out = list(range(self.last + 1, self.last + 1 + n))
        self.last += n
        return out


def current_rev(cur) -> int:
    cur.execute("SELECT COALESCE(max(rev), 0) FROM changes")
    return cur.fetchone()[0]


@dataclass
class ImportReport:
    commit: str
    import_id: int | None = None
    rev_from: int = 0
    rev_to: int = 0
    per_table: dict = field(default_factory=dict)
    per_ws: dict = field(default_factory=dict)
    problems: dict = field(default_factory=dict)
    skipped: dict = field(default_factory=dict)
    dry_run: bool = False

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def import_commit(conn, repo, commit: str = "HEAD", *, only_ws: set[str] | None = None,
                  allow_delete: bool = False, actor: str | None = None,
                  dry_run: bool = False, source: str = "git:open-guji/guji-workspace"
                  ) -> ImportReport:
    commit = gitsource.resolve(repo, commit)
    scans = scan_commit(repo, commit, only_ws)
    return import_scans(conn, scans, label=commit, allow_delete=allow_delete, actor=actor,
                        dry_run=dry_run, source=source)


def import_scans(conn, scans: list[ScanResult], *, label: str, allow_delete: bool = False,
                 actor: str | None = None, dry_run: bool = False, source: str = "",
                 guard=None, only_paths: set[str] | None = None) -> ImportReport:
    """把扫描结果写进库（幂等差分）。``guard(cur)`` 在读库版本之后、算写入之前调用，抛错即整次不写
    （``db push`` 用它比版本号）；之后库被别人写过，提交时守卫失败抛 ``d1conn.Stale``。
    ``label`` 记进 ``imports.git_commit``。

    ``only_paths``：只差分这些文件（扫描里别的行不看，库里别的文件不动）。给一次性改几个文件的脚本用
    （如 ``feedback.migrate_v1``），省得为了改几行台账把整个工作区连图带库拉下来再整推。"""
    commit = label
    rep = ImportReport(commit=commit, dry_run=dry_run)
    with conn.transaction(guard=True):
        cur = conn.cursor()
        if guard is not None:
            guard(cur)
        rep.rev_from, last_import = conn.heads()
        rep.import_id = last_import + 1
        revs = _Revs(rep.rev_from)
        conn.add_group([("INSERT INTO imports (import_id, source, git_commit, actor, rev_from) VALUES (?, ?, ?, ?, ?)",
                         [rep.import_id, source, commit, actor, rep.rev_from])])
        refused = []
        plans: list[tuple[str, str, Plan, list[Row]]] = []
        for sc in scans:
            by_tbl: dict[str, list[Row]] = {t: [] for t in TABLES}
            for r in sc.rows:
                if only_paths is None or r.src_path in only_paths:
                    by_tbl[r.tbl].append(r)
            rep.problems[sc.ws] = sc.problems
            rep.skipped[sc.ws] = dict(Counter(_top(p) for p in sc.skipped))
            for tbl in TABLES:
                existing = load_existing(cur, tbl, sc.ws, only_paths)
                plan = diff(by_tbl[tbl], existing)
                if (plan.deletes and not allow_delete
                        and emptied_ledger(tbl, len(existing), len(by_tbl[tbl]), len(plan.deletes))):
                    refused.append(f"{sc.ws}/{tbl}: 本地只有 {len(by_tbl[tbl])} 行、库里有 {len(existing)} 行，"
                                   f"要删 {len(plan.deletes)} 行——像是本机字形库被清空后推上来的")
                if plan.deletes and TABLES[tbl].append_only and not allow_delete:
                    refused.append(f"{sc.ws}/{tbl}: 要删 {len(plan.deletes)} 行"
                                   f"（如 {plan.deletes[0]}）")
                plans.append((sc.ws, tbl, plan, by_tbl[tbl]))
        if refused:
            raise DeleteRefused("只追加的台账在这个提交里少了行，拒绝导入（确认无误再加 "
                                "--allow-delete）：\n" + "\n".join(refused))
        typed_of: dict[str, list] = {}
        bodies: dict[str, str] = {}
        # 写入顺序：先 workspaces（外键），删除倒序
        for ws, tbl, plan, rows in plans:
            st = rep.per_table.setdefault(tbl, Counter())
            st["rows"] += len(rows)
            st["insert"] += len(plan.inserts)
            st["update"] += len(plan.updates)
            st["delete"] += len(plan.deletes)
            st["moved"] += len(plan.moves)
            w = rep.per_ws.setdefault(ws, Counter())
            w["changes"] += plan.n_changes
            if dry_run or not (plan.inserts or plan.updates or plan.moves or plan.deletes):
                continue
            if tbl not in typed_of:
                typed_of[tbl] = [c for c in _columns(cur, tbl) if c[0] != "ingested_at"]
            typed = typed_of[tbl]
            ups = plan.inserts + plan.updates
            for r in ups:
                if body_in_r2(r):
                    bodies[sha256(r.raw.encode("utf-8"))] = r.raw
            if _is_bulk(plan):
                # 首次灌这张表：整批记一条变更、共用一个 rev（逐行记会让 changes 白占约 60 MB）
                rev = revs.take(1)[0]
                pieces = _pieces(ups)
                for i, part in enumerate(pieces):
                    g = _upsert_stmts(typed, tbl, ws, part, [rev] * len(part))
                    if i == len(pieces) - 1:          # 最后一段带上那条整批变更：中途断了没有这条，重跑补齐
                        g.append(_bulk_change(rep.import_id, tbl, ws, ups, rev))
                    conn.add_group(g)
                continue
            for part in _pieces(ups):
                prevs = revs.take(len(part))
                conn.add_group(_upsert_stmts(typed, tbl, ws, part, prevs)
                               + _change_stmts(rep.import_id, tbl, ws, plan, list(zip(prevs, part)), []))
            for part in _pieces(plan.moves, size=lambda r: 200 + len(str(r.key))):
                conn.add_group(_move_stmts(tbl, ws, part))
        if not dry_run:
            for ws, tbl, plan, _ in reversed(plans):
                for i in range(0, len(plan.deletes), 5000):
                    part = plan.deletes[i:i + 5000]
                    drevs = revs.take(len(part))
                    conn.add_group(_delete_stmts(tbl, ws, part)
                                   + _change_stmts(rep.import_id, tbl, ws, plan, [], list(zip(drevs, part))))
        rep.rev_to = revs.last if not dry_run else rep.rev_from
        rep.per_table = {k: dict(v) for k, v in rep.per_table.items()}
        rep.per_ws = {k: dict(v) for k, v in rep.per_ws.items()}
        conn.add_group([(f"UPDATE imports SET finished_at = {NOW}, rev_to = ?, stats = ? WHERE import_id = ?",
                         [rep.rev_to, json.dumps({"per_table": rep.per_table, "per_ws": rep.per_ws,
                                                  "problems": rep.problems}, ensure_ascii=False),
                          rep.import_id])])
        if dry_run:
            raise Rollback()
        for h, text in bodies.items():                 # 大文件原文先进 R2（内容寻址，导入失败也无害）
            conn.put_body(h, text)
    return rep


#: 一张表（某工作区）首次导入超过这么多行就整批记一条变更
BULK_MIN_ROWS = 1000


def _is_bulk(plan: Plan) -> bool:
    return (len(plan.inserts) >= BULK_MIN_ROWS and not plan.updates and not plan.deletes
            and not plan.moves and not plan.old_sha)


def _bulk_change(import_id, tbl, ws, rows: list[Row], rev: int):
    """整批一条：pk 记行数，new_sha 是全部行 fingerprint 按主键排序后再取 sha256。"""
    fps = "\n".join(fingerprint(r) for r in sorted(rows, key=lambda r: [str(k) for k in r.key]))
    return ("INSERT INTO changes (rev, import_id, tbl, op, ws, pk, old_sha, new_sha) "
            "VALUES (?, ?, ?, 'insert', ?, ?, NULL, ?)",
            [rev, import_id, tbl, ws, json.dumps({"bulk_rows": len(rows)}), sha256(fps.encode())])


def _change_stmts(import_id, tbl, ws, plan: Plan, ups: list[tuple[int, Row]], dels: list[tuple[int, tuple]]) -> list:
    rows = []
    for rev, r in ups:
        rows.append((rev, import_id, tbl, "update" if r.key in plan.old_sha else "insert", ws,
                     json.dumps(list(r.key), ensure_ascii=False), plan.old_sha.get(r.key), fingerprint(r)))
    for rev, k in dels:
        rows.append((rev, import_id, tbl, "delete", ws, json.dumps(list(k), ensure_ascii=False),
                     plan.old_sha.get(k), None))
    if not rows:
        return []
    return insert_stmts("changes", ["rev", "import_id", "tbl", "op", "ws", "pk", "old_sha", "new_sha"], rows)


def _top(rel: str) -> str:
    parts = rel.split("/")
    return "/".join(parts[:2]) if len(parts) > 2 else rel
