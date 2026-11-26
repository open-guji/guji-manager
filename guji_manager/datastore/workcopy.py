"""工作区的中心库数据副本（GUJI-608 写入切换之后）：数据不在工作区里，在工作区外的数据目录。

    guji db migrate -w <工作区>   # 一次性：工作区里的数据核对后挪进数据目录，工作区里删掉
    guji db pull    -w <工作区>   # 中心库 → 数据目录（只在本地没有未推改动时）
    guji db push    -w <工作区>   # 数据目录 → 中心库（先比版本号）

**布局**：工作区根只留 ``workspace.yaml``（身份）与标记 ``.central.json``（{ws, branch}）；
册 yaml、人裁、台账、批次、人工配置、字形库在 ``core.workspace.central_data_dir``
（``$GUJI_DATA_HOME/<分支>/<工作区 id>/``，布局同旧工作区），``core.workspace`` 的路径函数
见到标记就指过去。原图、products、cache、glyph.db 照旧在工作区。

**版本**：数据目录里的 ``.central-state.json`` 记拉取时的 rev、每个文件的基准 sha（``base``）和
当时 glyph.db 的指纹。``local_changes`` 不连网，对的是基准：改了、新增、删掉都算。
push 拿库锁后查这个工作区在 rev 之后有没有别人写过，有就整次拒绝（``StaleBase``）；
只追加的台账少了行、整个文件丢了也拒绝。

**glyph.db**：人裁消费者改的是 glyph.db，要导出成字形库账本才进得了库。push、pull 前看 glyph.db
指纹与上次记的是否相同，不同就先导出。pull 拉到新的字形库账本才重建 glyph.db；迁移不碰它
（重建会让库指纹变、各书产物判过期）。导出、重建、指纹由调用方（``cli_db``）传进来，本层不 import 聚类。
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .._cv import _CENTRAL_NAME, CENTRAL_MARKER, borrowed_root, central_data_dir, central_marker, resolve_borrow
from .scope import BLOB_TABLES, GS, TABLES, classify, sha256

SCOPE = ("books/", "feedback/", "review/", "config/", "corpus/", GS)
STATE = ".central-state.json"
WS_YAML = "workspace.yaml"
BORROW_STATE = ".borrowed-state.json"

#: 共享层的只读工作区（共享方案 3.2 节）：普通 push／sync 一律拒绝，只有升级脚本能写；
#: ``glyphlib-*`` 每版一个工作区，只能写新开的版本（sheldon 10-19：升级时脚本可写）
SHARED_PREFIX = "glyphlib-"
SHARED_NAMES = frozenset({"corpus-base", "pua-wyg"})
#: 单个工作区里按版本目录出的共享层（``corpus-base`` 的 ``b<M>``、``pua-wyg`` 的 ``v<N>``）：升级脚本只能加新版本，
#: 已有版本目录里的文件一概不许改、不许删（出新版不覆盖）。键＝工作区名，值＝版本目录所在前缀
VERSIONED_SHARED = {"pua-wyg": "config/pua-wyg/"}


def is_shared_ws(ws: str) -> bool:
    return ws.startswith(SHARED_PREFIX) or ws in SHARED_NAMES


class StaleBase(RuntimeError):
    pass


class FileDeleteRefused(RuntimeError):
    pass


@dataclass
class GlyphHooks:
    """glyph.db 相关的三件事（由 cli_db 用聚类层实现）。"""
    fingerprint: Callable[[Path], str]                 # (db_path) -> 指纹；库不存在返回 ""
    export: Callable[[Path, Path], dict]               # (db_path, store_dir) -> 统计
    rebuild: Callable[..., dict]                       # (ws_dir, store_dir, db_path, extras) -> 统计；extras＝借来的字形库
    db_path: Path


# ---- 布局 ----

def data_dir(ws_dir: Path) -> Path:
    m = central_marker(Path(ws_dir))
    if not m:
        raise SystemExit(f"{ws_dir} 还没迁到中心库（没有 {CENTRAL_MARKER}）：先 guji db migrate -w {ws_dir}")
    return central_data_dir(str(m["ws"]), str(m.get("branch") or "main"))


def _walk(root: Path, patches: bool = True):
    """root 下归中心库管的文件（不含 workspace.yaml）：(相对路径, 绝对路径)。

    用 ``os.walk`` 拼字符串，不逐个 ``Path.relative_to``／``is_file``（殿本 4.2 万个文件，旧写法一遍 20 秒，2026-11-18）。"""
    root = Path(root)
    out: list[tuple[str, Path]] = []
    base = str(root)
    for pre in SCOPE:
        d = os.path.join(base, pre.rstrip("/"))
        if not os.path.isdir(d):
            continue
        is_gs = pre == GS
        for dirpath, dirnames, filenames in os.walk(d):
            rel_dir = os.path.relpath(dirpath, base).replace(os.sep, "/")
            if not patches and is_gs and (rel_dir + "/").startswith(GS + "patches/"):
                dirnames[:] = []                   # 刻例图目录：不要图时整个跳过
                continue
            for name in filenames:
                rel = f"{rel_dir}/{name}"
                kind = classify(rel)
                if kind is not None and (patches or kind != "patch"):
                    out.append((rel, Path(dirpath) / name))
    out.sort(key=lambda x: x[0])
    yield from out


#: manifest 的 sha 缓存（数据目录下，不归中心库管）：{相对路径: [大小, mtime_ns, sha]}。大小或修改时间变了才重读重算。
SHA_CACHE = ".central-shacache.json"


def _sha_of(rel: str, p: Path, cache: dict, fresh: dict) -> str:
    st = p.stat()
    hit = cache.get(rel)
    if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
        sha = hit[2]
    else:
        sha = sha256(p.read_bytes())
    fresh[rel] = [st.st_size, st.st_mtime_ns, sha]
    return sha


def manifest(ws_dir: Path, data: Path) -> dict[str, str]:
    """{相对路径: sha}：数据目录里的文件（刻例图除外，图跟着实例行走）＋工作区的 workspace.yaml。

    文件大小与修改时间（ns）都没变的沿用上次算的 sha（``SHA_CACHE``），一次 sync 里要算两三遍清单，
    殿本每遍原来约 7 秒（2026-11-18）。``GUJI_DB_NO_SHA_CACHE=1`` 关。"""
    data = Path(data)
    cpath = data / SHA_CACHE
    cache: dict = {}
    use = os.environ.get("GUJI_DB_NO_SHA_CACHE") != "1"
    if use and cpath.exists():
        try:
            cache = json.loads(cpath.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
    fresh: dict = {}
    out = {rel: _sha_of(rel, p, cache, fresh) for rel, p in _walk(data, patches=False)}
    y = Path(ws_dir) / WS_YAML
    if y.exists():
        out[WS_YAML] = sha256(y.read_bytes())
    if use and fresh != cache and data.is_dir():
        tmp = cpath.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(fresh, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp, cpath)
        except OSError:
            pass
    return out


def scan(ws_dir: Path, data: Path, only: set[str] | None = None):
    """``only`` 给了就只扫这些文件（增量推，见 ``push``）；workspace.yaml 总要带上（scan_files 要读工作区 id）。"""
    from .scope import scan_files
    if not (Path(ws_dir) / WS_YAML).exists():
        raise SystemExit(f"工作区 {ws_dir} 没有 {WS_YAML}（工作区身份文件，在工作区仓里）：-w 指对了吗？先在工作区仓 git pull 取回")
    items = [(WS_YAML, (lambda: (Path(ws_dir) / WS_YAML).read_bytes()))]
    items += [(rel, (lambda p=p: p.read_bytes())) for rel, p in _walk(data) if only is None or rel in only]
    return scan_files(items, Path(ws_dir).name)


def read_state(data: Path) -> dict | None:
    p = Path(data) / STATE
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def write_state(data: Path, **kw) -> None:
    kw["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    p = Path(data) / STATE
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(kw, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, p)


#: 增量推（只扫、只比改了的文件）适用的表：主键里带 src_path，或一个文件就对应一组固定的主键（consumed 一个消费者一个文件、
#: books 一册一个 yaml、workspaces）。字形库各表主键是实例 id 等、行会在文件间挪，照旧全量比。
INCREMENTAL_TABLES = frozenset({"workspaces", "source_files", "books", "events", "consumed", "anchors",
                                "verdicts", "pending_items", "list_rows", "files", *BLOB_TABLES})
FULL_SCAN_ENV = "GUJI_DB_FULL_SCAN"


def incremental_ok(paths) -> bool:
    """这些改了的文件能不能只扫它们自己（纯函数）。"""
    for rel in paths:
        if rel.startswith(GS):
            return False
        tbl = classify(rel)
        if tbl is None or tbl not in INCREMENTAL_TABLES:
            return False
    return True


def _diff(base: dict[str, str], cur: dict[str, str]) -> list[str]:
    """两份清单不同的路径。``cur`` 里没有 workspace.yaml 不算改动：它是工作区身份文件、在工作区仓里（不在数据目录），
    本机缺它推不掉也不该推删除（SJ 11-26：status 把本机不存在的 workspace.yaml 列成「未推」）；推送时 ``scan`` 另行报错。"""
    return sorted(k for k in set(base) | set(cur)
                  if base.get(k) != cur.get(k) and not (k == WS_YAML and k not in cur))


ALLOW_GLYPH_SHRINK_ENV = "GUJI_ALLOW_GLYPH_SHRINK"      # 设 1：确要缩小字形库（人为清理）时放行
GLYPH_SHRINK_RATIO = 0.95                                # 导出后某个账本行数 < 原来的这个比例（且少 ≥3 行）就拦：缩水超 5% 即停（2026-11-10 史記 6,465→3,554 没被「一半」拦住）


ALLOW_DUP_KEYS_ENV = "GUJI_ALLOW_DUP_KEYS"
#: 状态里的标记：数据目录的字形账本比 glyph.db 新（``db pull --no-rebuild`` 拉到了新账本却没重建库）
GLYPH_DB_STALE = "glyph_db_stale"
ALLOW_STALE_GLYPH_ENV = "GUJI_ALLOW_STALE_GLYPH_EXPORT"


def dup_key_problems(problems: list[str], changed: set[str]) -> list[str]:
    """扫描报的「主键与第 N 行重复」里，属于这次要推（相对基准改了）的文件的那些（纯函数）。"""
    out = []
    for pr in problems:
        if "行重复" not in pr or "主键" not in pr:
            continue
        path = pr.split(":", 1)[0]
        if path in changed:
            out.append(pr)
    return out


def _jsonl_rows(store: Path) -> dict[str, int]:
    """字形库目录顶层各 .jsonl 账本的行数（不数子目录）。"""
    out: dict[str, int] = {}
    if store.is_dir():
        for f in sorted(store.glob("*.jsonl")):
            with f.open("rb") as fh:
                out[f.name] = sum(1 for ln in fh if ln.strip())
    return out


def glyph_shrink_problems(before: dict[str, int], after: dict[str, int], ratio: float = GLYPH_SHRINK_RATIO) -> list[str]:
    """导出前后账本行数对比：原来有行、导出后归零或掉到不足 ratio 的，每个报一条（纯函数，便于测）。"""
    bad = []
    for name, n0 in before.items():
        n1 = after.get(name, 0)
        if n0 > 0 and (n1 == 0 or (n1 < n0 * ratio and n0 - n1 >= 3)):
            bad.append(f"{name}：{n0} → {n1} 行")
    return bad


def _export_if_changed(glyph: GlyphHooks | None, data: Path, state: dict | None) -> bool:
    """glyph.db 自上次记录后变过就导出进数据目录的字形库。返回是否导出了。

    缩水闸（2026-11-09，用户要求）：本机 glyph.db 是空的或没重建（`db pull --no-rebuild` 之后、或只跑过别的
    pin 的库）时，导出会把数据目录里原有的字形账本写成空，随后 sync／push 就把中心库的字形表清掉
    （2026-11-04 事故同类）。导出前备份账本，导出后任一账本行数归零或缩水超 5% 就还原备份并停下；
    确要缩小的人为清理设环境变量 `GUJI_ALLOW_GLYPH_SHRINK=1`。"""
    if glyph is None or not Path(glyph.db_path).exists():
        return False
    fp = glyph.fingerprint(glyph.db_path)
    if state is not None and fp == state.get("glyph_db_fp"):
        return False
    if state is not None and state.get(GLYPH_DB_STALE) and os.environ.get(ALLOW_STALE_GLYPH_ENV) != "1":
        # 2026-11-18（全唐文开放行格回库前查出的洞）：`db pull --no-rebuild` 拉到了新的字形账本、glyph.db 却还是旧的，
        # 状态里的指纹也还是旧库的。之后有人往这个旧库里写（回库、人裁落库），导出就会拿旧库把新账本整个盖掉，
        # 别人新加的刻例在推库时被删——少于 5% 时缩水闸拦不住。
        raise SystemExit(
            f"✗ 本机 glyph.db 比数据目录的字形账本旧（上次 `guji db pull` 带了 --no-rebuild），之后又被改过：导出会用旧库"
            f"盖掉账本、推库时删掉别人新加的刻例，已停下、没导出。先备份要留的本地改动，`guji db pull --force`"
            f"（重建 glyph.db，会丢本地没推的改动），再重做刚才的回库／落库；确知本机库是新的设 {ALLOW_STALE_GLYPH_ENV}=1。")
    store = data / GS.rstrip("/")
    before = _jsonl_rows(store)
    backup: dict[str, bytes] = {f.name: f.read_bytes() for f in store.glob("*.jsonl")} if store.is_dir() else {}
    glyph.export(glyph.db_path, store)
    bad = glyph_shrink_problems(before, _jsonl_rows(store))
    if bad and os.environ.get(ALLOW_GLYPH_SHRINK_ENV) != "1":
        for name, raw in backup.items():                 # 还原：不让缩水的账本留在数据目录里
            (store / name).write_bytes(raw)
        raise SystemExit(
            "✗ 导出字形库会让账本缩水，已还原、没推：" + "；".join(bad) + "。多半是本机 glyph.db 没重建或是空库："
            "先 `guji db pull --force -w <工作区>`（会重建字形库，约 2 分钟）再 sync／push；"
            f"确要缩小的人为清理设 {ALLOW_GLYPH_SHRINK_ENV}=1。")
    return True


def _refresh_stale_db(glyph: GlyphHooks | None, ws_dir: Path, data: Path, st: dict, *, src=None, cache=None,
                      bucket: str = "main") -> dict:
    """账本比 glyph.db 新、而 glyph.db 自那以后没被动过（指纹仍是状态里记的）：现在按账本重建，清掉标记。

    换单（``GUJI_DB_NO_GLYPH``）的 sync 只拉不重建，之后一次正常 sync 就在这里补上；库被动过就不碰，
    交 ``_export_if_changed`` 拦下（重建会丢掉那些改动）。"""
    if glyph is None or not st.get(GLYPH_DB_STALE) or not Path(glyph.db_path).exists():
        return st
    if glyph.fingerprint(glyph.db_path) != st.get("glyph_db_fp"):
        return st
    if borrow_entries(ws_dir) and src is None:          # 借库要连库解析，拿不到就不重建（重建成不带借库的库更糟）
        return st
    extras = borrow_stores(src, ws_dir, cache=cache, bucket=bucket)[0] if borrow_entries(ws_dir) else []
    glyph.rebuild(ws_dir, data / GS.rstrip("/"), glyph.db_path, extras)
    st = {k: v for k, v in st.items() if k not in (GLYPH_DB_STALE, "at")}
    st["glyph_db_fp"] = glyph.fingerprint(glyph.db_path)
    write_state(data, **st)
    return st


def local_changes(ws_dir: Path, glyph: GlyphHooks | None = None) -> list[str]:
    """相对上次拉取／推送的基准，本地改了的文件（glyph.db 有未导出的改动会先导出）。"""
    data = data_dir(ws_dir)
    st = read_state(data)
    if st is None:
        raise SystemExit(f"数据目录 {data} 没有 {STATE}：先 guji db pull -w {ws_dir}")
    _export_if_changed(glyph, data, st)
    return _diff(st["base"], manifest(ws_dir, data))


def _db_manifest(src, ws: str) -> dict[str, str]:
    """库里这个工作区的文件 {相对路径: sha}：文本在 source_files，锚图、整理本在 BLOB_TABLES。"""
    from .materialize import _rows, blob_rows
    out = {r["src_path"]: r["sha256"] for r in _rows(src, "source_files", ws, ("src_path", "sha256"))}
    for tbl in BLOB_TABLES:
        out.update({r["src_path"]: r["sha256"] for r in blob_rows(src, tbl, ws)})
    return out


def _local(ws_dir: Path, data: Path):
    """``materialize`` 的 ``reuse``：相对路径 → 本机现有文件（workspace.yaml 在工作区，别的在数据目录）。"""
    def f(rel: str) -> Path | None:
        p = (Path(ws_dir) if rel == WS_YAML else Path(data)) / rel
        return p if p.is_file() else None
    return f


# ---- 工作区快照（新机器整拉殿本走中心库约 50 MB、读行多；快照包约 6–7 MB 走 R2，不计 D1 读行）----

SNAPSHOT_ENV = "GUJI_DATA_SNAPSHOT"      # 设 0 关掉快照（不下也不传）
SNAPSHOT_SKIP_EXT = (".png",)            # 图另有 R2 缓存，不进快照


def _snapshots_on(src) -> bool:
    return os.environ.get(SNAPSHOT_ENV, "1") != "0" and hasattr(src, "get_snapshot")


def _seed_from_snapshot(src, ws: str, seed: Path) -> int | None:
    """把最新快照解到 ``seed``（只收普通文件、相对路径、不许 ..）。返回快照 rev；没有返回 None。出错只当没有。"""
    import io
    import sys
    import tarfile
    try:
        got = src.get_snapshot(ws)
        if not got:
            return None
        rev, blob = got
        if seed.exists():
            shutil.rmtree(seed)
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
            for m in tf.getmembers():
                name = m.name
                if not m.isfile() or name.startswith("/") or ".." in Path(name).parts:
                    continue
                f = tf.extractfile(m)
                if f is None:
                    continue
                out = seed / name
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(f.read())
        return int(rev)
    except Exception as e:                       # 快照只是缓存：坏了、断了都退回整拉
        print(f"[db] 快照不可用，改从库里整拉：{e}", file=sys.stderr)
        shutil.rmtree(seed, ignore_errors=True)
        return None


def _publish_snapshot(src, ws: str, rev: int, ws_dir: Path, data: Path, base: dict[str, str]) -> int | None:
    """把本机已与库一致的文本文件打成 tar.gz 存上去。只放 sha 与 ``base`` 一致的；令牌不能写就算了。返回字节数。"""
    import io
    import sys
    import tarfile
    if not hasattr(src, "put_snapshot"):
        return None
    if _read_only(src):
        # 读令牌存不上（403），先问一句，省得白打一个包（殿本约 9 s；云端新机器拉库都是读令牌）
        print("[db] 读令牌不存快照（不影响本次拉取）", file=sys.stderr)
        return None
    local = _local(ws_dir, data)
    buf = io.BytesIO()
    try:
        with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=9) as tf:
            for rel in sorted(base):
                if rel.endswith(SNAPSHOT_SKIP_EXT):
                    continue
                p = local(rel)
                if p is None:
                    continue
                b = p.read_bytes()
                if sha256(b) != base[rel]:
                    continue
                ti = tarfile.TarInfo(rel)
                ti.size = len(b)
                tf.addfile(ti, io.BytesIO(b))
        src.put_snapshot(ws, rev, buf.getvalue())
        return len(buf.getvalue())
    except Exception as e:                       # 读令牌、旧 Worker、网络问题：不影响拉取
        print(f"[db] 快照没存上（不影响本次拉取）：{e}", file=sys.stderr)
        return None


def _read_only(src) -> bool:
    """令牌是不是只读（``whoami`` 的 ``role == "read"``）；问不到当可写，照旧去试。"""
    try:
        return hasattr(src, "whoami") and (src.whoami() or {}).get("role") == "read"
    except Exception:                            # noqa: BLE001 —— 旧 Worker、网络问题：照旧试着存
        return False


def _materialize(src, ws: str, tmp: Path, cache, bucket: str, retries: int = 3,
                 prefixes: tuple[str, ...] = (WS_YAML,) + SCOPE, reuse=None,
                 exclude: tuple[str, ...] = (), repair_gaps: bool = False) -> tuple[int, dict]:
    from .materialize import MaterializeError, materialize
    for _ in range(retries):
        r0 = src.status()
        try:
            stats = materialize(src, ws, tmp, prefixes, cache=cache, bucket=bucket, reuse=reuse, exclude=exclude,
                           repair_gaps=repair_gaps)
        except MaterializeError:
            # 先读 source_files、后读行：中间有人推了新行（如 admissions.jsonl 追加），行数对不上会报
            # 「超出 n_lines」或 sha 不符。读的过程中工作区有新写入就重读，否则是真不一致，照抛（10-23 A30 sync 撞上）
            if src.status() == r0 or not src.changes_since(ws, r0, limit=1):
                raise
            continue
        if src.status() == r0 or not src.changes_since(ws, r0, limit=1):
            return r0, stats
    raise SystemExit("读的过程中工作区一直有新写入，稍后再拉")


#: 增量拉（只取基准 rev 之后库里改了的文件，11-18）：设 1 退回整拉（每次都读整个工作区的清单和文件）
FULL_PULL_ENV = "GUJI_DB_FULL_PULL"
#: 变更记录超过这么多条、或要取的文件超过这么多个，就整拉（按路径分批取省不了多少）
INCR_MAX_CHANGES = 20000
INCR_MAX_FILES = 400


def _change_rows(src, ws: str, rev: int, cap: int) -> list[dict]:
    """库里工作区 ``ws`` 在 ``rev`` 之后的变更记录（tbl、op、pk），至多读 ``cap + 1`` 条。"""
    if hasattr(src, "conn"):                         # 直连 Postgres（测试、库机器）
        cur = src.conn.cursor()
        cur.execute("SELECT tbl, op, pk FROM changes WHERE ws = %s AND rev > %s ORDER BY rev LIMIT %s",
                    (ws, int(rev), cap + 1))
        return [{"tbl": t, "op": o, "pk": k} for t, o, k in cur.fetchall()]
    out: list[dict] = []
    for r in src._rows("changes", ws, None, {"since_rev": int(rev)}):
        out.append(r)
        if len(out) > cap:
            break
    return out


def _remote_delta(src, ws: str, rev: int, extra: set[str] = frozenset()):
    """基准 rev 之后库里改了的文件路径和刻例实例 id；拿不准（整批导入、太多、旧数据源）回 None 走整拉。

    文件一级的改动都记在 ``source_files``／``BLOB_TABLES`` 的变更里（主键就是路径）；刻例图换了记在
    ``glyph_instances``（主键实例 id，指纹含 patch_sha）。行在文件里挪位置不记变更，但那个文件的 sha 变了，
    ``source_files`` 照样有一条。"""
    if os.environ.get(FULL_PULL_ENV) == "1":
        return None
    try:
        rows = _change_rows(src, ws, rev, INCR_MAX_CHANGES)
    except Exception:                                 # noqa: BLE001 —— 旧 Worker、简易数据源：整拉
        return None
    if len(rows) > INCR_MAX_CHANGES:
        return None
    paths: set[str] = set()
    inst: set[str] = set()
    keys: dict[str, list[list]] = {}
    for r in rows:
        pk = r["pk"]
        if isinstance(pk, str):
            pk = json.loads(pk)
        if not isinstance(pk, list) or not pk:       # {"bulk_rows": n}：首次整批导入，不知道是哪些文件
            return None
        if r["tbl"] == "source_files" or r["tbl"] in BLOB_TABLES:
            paths.add(str(pk[0]))
        elif r["op"] != "delete":
            keys.setdefault(r["tbl"], []).append(pk)
            if r["tbl"] == "glyph_instances":
                inst.add(str(pk[0]))
    return paths, inst, set(extra) - paths, keys


#: 按主键补行时，一次请求带这么多个键值（URL 长度）；一张表要补的键超过 PATCH_MAX_KEYS 就整文件取
PATCH_KEY_BATCH = 200
PATCH_MAX_KEYS = 4000


def _patch_lines(src, ws: str, need: dict[str, dict], base: dict[str, str], keys: dict[str, list[list]],
                 reuse) -> dict[str, bytes]:
    """逐行表的文件只差几行时，不整文件向库要（殿本 instances 一份 1.5 万行、要 20 多次请求、约 30 s）：
    本机那份还是基准版本的，就按变更记录里的主键只取改了／新增的行，盖到本机行上，按库里登记的行数截齐，
    整文件 sha 对得上才用。行挪了位置（中间删行）不记变更，sha 会对不上，那个文件照旧整文件取。"""
    from .materialize import LINE_COLS, NOT_LINE, _rows
    from .scope import split_lines
    out: dict[str, bytes] = {}
    if reuse is None:
        return out
    by_tbl: dict[str, dict[str, list[str]]] = {}
    for p, f in need.items():
        tbl = f["tbl"]
        if tbl in NOT_LINE or tbl not in TABLES or not base.get(p):
            continue
        lp = reuse(p)
        if lp is None:
            continue
        try:
            b = Path(lp).read_bytes()
        except OSError:
            continue
        if sha256(b) != base[p]:
            continue
        by_tbl.setdefault(tbl, {})[p] = split_lines(b)[0]
    for tbl, have in by_tbl.items():
        kcols = TABLES[tbl].key
        pks = keys.get(tbl, [])
        if not kcols or len(pks) > PATCH_MAX_KEYS or any(len(k) != len(kcols) for k in pks):
            continue
        # 用不同值最多的那一列过滤（src_path 只在它是唯一主键列时用）
        cand = [i for i, c in enumerate(kcols) if c != "src_path"] or [0]
        col = max(cand, key=lambda i: len({str(k[i]) for k in pks}))
        vals = sorted({str(k[col]) for k in pks})
        got: dict[str, dict[int, str]] = {p: {} for p in have}
        try:
            for i in range(0, len(vals), PATCH_KEY_BATCH):
                for r in _rows(src, tbl, ws, LINE_COLS, **{kcols[col]: vals[i:i + PATCH_KEY_BATCH]}):
                    if r["src_path"] in got:
                        got[r["src_path"]][int(r["src_line"])] = r["raw"]
        except Exception:                             # noqa: BLE001 —— 数据源不认这个过滤：整文件取
            continue
        for p, lines in have.items():
            f = need[p]
            n = int(f["n_lines"])
            new = (lines + [None] * n)[:n]
            for i, raw in got[p].items():
                if i < n:
                    new[i] = raw
            if any(x is None for x in new):
                continue
            b = ("\n".join(new) + ("\n" if f["final_newline"] else "")).encode("utf-8")
            if sha256(b) == f["sha256"] and len(b) == int(f["bytes"]):
                out[p] = b
    return out


def _materialize_delta(src, ws: str, tmp: Path, cache, bucket: str, base: dict[str, str], rev: int, *,
                       reuse=None, extra: set[str] = frozenset(), want_patch=lambda name: True,
                       retries: int = 3):
    """``_materialize`` 的增量版：只把基准 ``rev`` 之后库里改了的文件（加上 ``extra``，库里现在的版本）还原到 ``tmp``，
    库里清单由 ``base`` 加这些改动算出。返回 (rev, 库里清单, 统计)；不能增量就回 None（调用方整拉）。"""
    from .materialize import MaterializeError, _rows, _safe, _texts
    prefixes = (WS_YAML,) + SCOPE
    sel = lambda p: p.startswith(prefixes)          # noqa: E731
    for _ in range(retries):
        r0 = src.status()
        d = _remote_delta(src, ws, rev, extra)
        if d is None:
            return None
        changed, inst, more, keys = d
        want = sorted(changed | more)
        if len(want) > INCR_MAX_FILES or len(inst) > INCR_MAX_CHANGES:
            return None
        try:
            files = {r["src_path"]: r for r in _rows(src, "source_files", ws, None, src_path=want)} if want else {}
            blobs: dict[str, dict[str, str]] = {}
            for tbl in BLOB_TABLES:
                blobs[tbl] = ({r["src_path"]: r["sha256"] for r in _rows(src, tbl, ws, ("src_path", "sha256"),
                                                                          src_path=want)} if want else {})
            patch = ({r["instance_id"]: r.get("patch_sha") for r in
                      _rows(src, "glyph_instances", ws, ("instance_id", "patch_sha"), instance_id=sorted(inst))}
                     if inst and sel(GS + "patches/") else {})
        except Exception:                             # noqa: BLE001 —— 数据源不认按路径过滤：整拉
            return None
        remote = {k: v for k, v in base.items() if k not in changed}
        remote.update({p: r["sha256"] for p, r in files.items() if p in changed})
        for got in blobs.values():
            remote.update({p: sha for p, sha in got.items() if p in changed})
        need = {p: r for p, r in files.items() if sel(p) and r["tbl"] not in BLOB_TABLES}
        patched = _patch_lines(src, ws, need, base, keys, reuse)
        try:
            texts, reused, fetched, _ = _texts(src, ws, {p: r for p, r in need.items() if p not in patched}, reuse)
            texts.update(patched)
        except MaterializeError:
            if src.status() != r0:
                continue
            return None
        images: dict[str, str] = {}
        by_ext: dict[str, set[str]] = {}
        for i, sha in patch.items():
            name = f"{_safe(i)}.png"
            if sha and want_patch(name):
                images[f"{GS}patches/{name}"] = sha
                by_ext.setdefault("png", set()).add(sha)
        for tbl, got in blobs.items():
            for p, sha in got.items():
                if sel(p):
                    images[p] = sha
                    by_ext.setdefault(BLOB_TABLES[tbl], set()).add(sha)
        absent: set[str] = set()
        if images:
            if cache is None:
                from .._cv import BlobCache
                cache = BlobCache()
            for ext in sorted(by_ext):
                absent.update(cache.ensure(src, by_ext[ext], bucket=bucket, ext=ext).get("missing", ()))
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        for p, b in texts.items():
            (tmp / p).parent.mkdir(parents=True, exist_ok=True)
            (tmp / p).write_bytes(b)
        for p, sha in images.items():
            if sha not in absent:
                (tmp / p).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(cache.path(sha), tmp / p)
        if src.status() == r0 or not src.changes_since(ws, r0, limit=1):
            return r0, remote, {"scan": "incremental", "changed_files": len(changed), "files": len(texts),
                                "patched": len(patched),
                                "reused": reused, "fetched": fetched, "images": len(images) - len(absent)}
    return None


def _install(tmp: Path, ws_dir: Path, data: Path) -> tuple[int, int]:
    """把 tmp 里还原的文件换进数据目录（镜像；没被引用的刻例图留着），workspace.yaml 进工作区。"""
    got = {p.relative_to(tmp).as_posix() for p in tmp.rglob("*") if p.is_file()}
    removed = 0
    for rel, p in list(_walk(data)):
        if rel not in got and classify(rel) != "patch":
            p.unlink()
            removed += 1
    for rel in sorted(got):
        dst = (Path(ws_dir) if rel == WS_YAML else data) / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp / rel, dst)
    shutil.rmtree(tmp, ignore_errors=True)
    return len(got), removed


def _install_delta(tmp: Path, ws_dir: Path, data: Path, changed: set[str]) -> tuple[int, int]:
    """增量拉的 ``_install``：tmp 里的文件换上去（刻例图也覆盖，库里换了图），库里删掉的 ``changed`` 路径本机也删。"""
    got = {p.relative_to(tmp).as_posix() for p in tmp.rglob("*") if p.is_file()}
    removed = 0
    for rel in sorted(changed - got):
        p = (Path(ws_dir) if rel == WS_YAML else data) / rel
        if p.is_file() and classify(rel) != "patch":
            p.unlink()
            removed += 1
    for rel in sorted(got):
        dst = (Path(ws_dir) if rel == WS_YAML else data) / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp / rel, dst)
    shutil.rmtree(tmp, ignore_errors=True)
    return len(got), removed


# ---- 借库（共享方案 S4）----

@dataclass(frozen=True)
class BorrowSpec:
    """``glyph_lib.borrow`` 的一条（借库参照方案缺口 1、2，2026-11-05）。

    旧写法是一个字符串（被借工作区名或路径）＝借全部、不钉；新写法是对象
    ``{from: <名>, scope: human, pin: <N>}``：``scope`` 缺省 ``all``，``human`` 只借被借库的人裁刻例，``human+auto`` 再加看图确认过的自动刻例；
    ``pin`` 钉被借工作区的字形库快照 g<N>（读那一版的内容，不读最新），只对中心库工作区名有意义。
    """
    name: str
    scope: str = "all"
    pin: int | None = None

    @property
    def dir_name(self) -> str:
        """被借库在本机的目录名（借库名取这一级，``borrow_fingerprint`` 认它）；钉了号的另放一份，不碰最新副本。"""
        return f"{self.name}@g{self.pin}" if self.pin else self.name


def parse_borrow(x) -> BorrowSpec:
    if isinstance(x, dict):
        extra = set(x) - {"from", "scope", "pin"}
        if "from" not in x or extra:
            raise SystemExit(f"glyph_lib.borrow 的对象写法只认 from、scope、pin，不认 {sorted(extra) or '（缺 from）'}：{x}")
        name, scope, pin = str(x["from"]), str(x.get("scope") or "all"), x.get("pin")
    else:
        name, scope, pin = str(x), "all", None
    if scope not in ("all", "human", "human+auto"):
        raise SystemExit(f"glyph_lib.borrow {name}：scope 只能是 all、human 或 human+auto，不是 {scope!r}")
    if pin is not None:
        if isinstance(pin, bool) or not isinstance(pin, int) or pin < 1:
            raise SystemExit(f"glyph_lib.borrow {name}：pin 要写被借库的字形库快照号（正整数），不是 {pin!r}")
        if not _CENTRAL_NAME.match(name):
            raise SystemExit(f"glyph_lib.borrow {name}：pin 只对中心库工作区名有意义，路径写法不能钉")
    return BorrowSpec(name, scope, pin)


def borrow_specs(ws_dir: Path) -> list[BorrowSpec]:
    """``workspace.yaml`` 的 ``glyph_lib.borrow``，每条解析成 ``BorrowSpec``（没配返回空表）。"""
    import yaml
    y = Path(ws_dir) / WS_YAML
    cfg = (yaml.safe_load(y.read_text(encoding="utf-8")) or {}) if y.exists() else {}
    return [parse_borrow(x) for x in ((cfg.get("glyph_lib") or {}).get("borrow") or [])]


def borrow_entries(ws_dir: Path) -> list[str]:
    """``workspace.yaml`` 的 ``glyph_lib.borrow`` 各条的被借工作区名／路径（没配返回空表；不含借法，借法用 ``borrow_specs``）。"""
    return [b.name for b in borrow_specs(ws_dir)]


def borrow_dir(spec: BorrowSpec, ws_dir: Path) -> Path:
    """一条借库在本机的字形库目录。钉了号的是 ``.borrowed/<名>@g<N>/output/glyph_store``，其余同 ``resolve_borrow``。"""
    if spec.pin:
        m = central_marker(Path(ws_dir)) or {}
        return borrowed_root(spec.dir_name, str(m.get("branch") or "main")) / "output" / "glyph_store"
    return resolve_borrow(spec.name, ws_dir)


def borrow_dir_of_root(root_name: str, ws_dir: Path) -> Path:
    """字形库快照清单里 ``borrow:<名>`` 的目录名 → 本机目录（名里带 ``@g<N>`` 的是钉过号的被借库）。"""
    base, _, g = root_name.partition("@g")
    if g.isdigit():
        return borrow_dir(BorrowSpec(base, pin=int(g)), ws_dir)
    return resolve_borrow(root_name, ws_dir)


def readonly_copy(src, name: str, branch: str, prefixes: tuple[str, ...], *, cache=None,
                  bucket: str = "main") -> tuple[int, bool]:
    """把中心库工作区 ``name`` 里 ``prefixes`` 下的文件拉成本机只读副本（``core.workspace.borrowed_root``）。

    副本旁 ``.borrowed-state.json`` 记拉到的 rev；库里那个工作区没新写入、要的目录都在就不重拉。
    返回 (rev, 这次是否重拉了)。借字形库（S4）和底库清单（S2）共用。"""
    root = borrowed_root(name, branch)
    stf = root / BORROW_STATE
    st = json.loads(stf.read_text(encoding="utf-8")) if stf.exists() else None
    have = st is not None and list(st.get("prefixes") or [GS]) == list(prefixes) \
        and all((root / p.rstrip("/")).exists() for p in prefixes)
    if have and not src.changes_since(name, int(st["rev"]), limit=1):
        return int(st["rev"]), False
    tmp = root.parent / f".{name}.borrow.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    rev, _ = _materialize(src, name, tmp, cache, bucket, prefixes=prefixes,
                          reuse=(lambda rel: (root / rel) if (root / rel).is_file() else None) if root.exists() else None)
    (tmp / BORROW_STATE).write_text(json.dumps({"ws": name, "branch": branch, "rev": rev,
                                                "prefixes": list(prefixes)}) + "\n", encoding="utf-8")
    if root.exists():
        shutil.rmtree(root)
    root.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, root)
    return rev, True


PINNED_LENDER = ".pinned-lender.json"


def pinned_tag(spec: BorrowSpec, ws_dir: Path) -> str:
    """钉了号的借库，本机副本记的快照 digest（没钉是空串）。没拼过就报错让先 pull。"""
    if not spec.pin:
        return ""
    mark = borrow_dir(spec, ws_dir).parent.parent / PINNED_LENDER
    try:
        return str(json.loads(mark.read_text(encoding="utf-8"))["digest"])
    except (OSError, ValueError, KeyError) as e:
        raise SystemExit(f"借库 {spec.dir_name} 没有钉号记录（{mark}）；先 guji db pull -w {ws_dir}") from e


def local_borrow_stores(ws_dir: Path, specs: "list[BorrowSpec] | None" = None) -> list[Path]:
    """不连网：按 ``workspace.yaml``（或给定的条目）认本机已有的借库副本，返回 ``rebuild_from_store`` 要的目录。
    副本不在就报错让先 ``guji db pull``。缺省借法给普通路径，非缺省给 ``BorrowedStore``。"""
    from .._cv import borrowed_store
    out: list[Path] = []
    for b in (borrow_specs(ws_dir) if specs is None else specs):
        d = borrow_dir(b, ws_dir)
        if ".borrowed" in d.parts and not d.is_dir():
            raise SystemExit(f"借库不存在：{d}（写中心库工作区名的，先 guji db pull 拉一次）")
        tag = pinned_tag(b, ws_dir)
        out.append(borrowed_store(d, b.scope, tag) if (b.scope != "all" or tag) else d)
    return out
_PACK_MAN = "config/glyph-pack/g{n}/manifest.json"


def pinned_lender_copy(src, name: str, n: int, branch: str, *, cache=None, bucket: str = "main") -> str:
    """把被借工作区 ``name`` 的字形库快照 g<n> 拼成本机只读副本 ``.borrowed/<名>@g<n>/output/glyph_store``，返回快照 digest。

    快照清单（``config/glyph-pack/g<n>/manifest.json``）一个号只写一次、不会变，所以拼好一次后（``.pinned-lender.json``
    记号与 digest）以后不再连网。只拼清单里 ``root == gs`` 的条目（被借库自己的真源）；被借库自己借的（``borrow:``）不传递。
    刻例图与文本都按 sha 从 R2 取，sha 不符或取不到就报错，不留半个目录。"""
    from .._cv import BlobCache
    from .materialize import materialize
    root = borrowed_root(f"{name}@g{n}", branch)
    mark = root / PINNED_LENDER
    if mark.is_file() and (root / "output" / "glyph_store").is_dir():
        try:
            st = json.loads(mark.read_text(encoding="utf-8"))
            if st.get("name") == name and st.get("n") == n and st.get("digest"):
                return str(st["digest"])
        except (OSError, ValueError):
            pass
    cache = cache or BlobCache()
    tmp = root.parent / f".{name}@g{n}.pin.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    rel = _PACK_MAN.format(n=n)
    try:
        materialize(src, name, tmp / "man", (rel,), cache=cache, bucket=bucket, with_images=False)
        man = json.loads((tmp / "man" / rel).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 — MaterializeError、文件不在、坏 JSON 都是同一句人话
        raise SystemExit(f"借库 {name} 钉了字形库快照 g{n}，但中心库里没有这一版的清单（{rel}）：{e}；"
                         f"让 {name} 那边先 guji glyph-db snapshot 出这个号并 guji db push") from e
    digest = str(man.get("digest") or "")
    if not digest:
        raise SystemExit(f"借库 {name} 的 g{n} 清单没有 digest")
    items = [it for it in man.get("items", []) if it.get("root") == "gs"]
    if not items:
        raise SystemExit(f"借库 {name} 的 g{n} 清单里没有本书真源条目（root=gs）")
    store = tmp / "output" / "glyph_store"
    store.mkdir(parents=True)
    by_ext: dict[str, list[dict]] = {"txt": [], "png": []}
    for it in items:
        by_ext[it.get("type", "txt")].append(it)
    missing: list[str] = []
    for ext, its in by_ext.items():
        if not its:
            continue
        got = cache.ensure(src, [it["sha256"] for it in its], bucket=bucket, ext=ext)
        missing += got.get("missing", [])
        for it in its:
            if cache.has(it["sha256"]):
                out = store / it["path"]
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(cache.path(it["sha256"]), out)
    if missing:
        shutil.rmtree(tmp, ignore_errors=True)
        raise SystemExit(f"借库 {name} 的 g{n} 有 {len(missing)} 个条目 R2 里取不到（如 {missing[:3]}）；"
                         f"{name} 那边先 guji glyph-db snapshot-upload --pin {n} --execute")
    shutil.rmtree(tmp / "man", ignore_errors=True)
    (tmp / PINNED_LENDER).write_text(json.dumps({"name": name, "n": n, "digest": digest}) + "\n", encoding="utf-8")
    if root.exists():
        shutil.rmtree(root)
    root.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, root)
    return digest


def borrow_stores(src, ws_dir: Path, *, cache=None, bucket: str = "main") -> tuple[list[Path], list[str]]:
    """借来的字形库 → (目录列表, 签名)。签名变了才要重建 glyph.db。

    写中心库工作区名的条目：拉那个工作区的 ``output/glyph_store/`` 到 ``core.workspace.borrowed_root``
    （只读副本，见 ``readonly_copy``）。写路径的条目照旧当本地目录。

    条目写成对象时（``BorrowSpec``）：``scope: human`` 只借人裁，签名带 ``#human``；``pin: N`` 钉被借库的快照 g<N>
    （``pinned_lender_copy``，读那一版、不随被借库更新），签名是 ``名@gN:digest``。返回的目录是
    ``BorrowedStore``（带 scope、tag，给 ``rebuild_from_store``）；缺省借法时与旧版同样是普通路径、同样的签名。"""
    from .._cv import borrowed_store
    ws_dir = Path(ws_dir)
    m = central_marker(ws_dir) or {}
    own, branch = str(m.get("ws") or ""), str(m.get("branch") or "main")
    dirs: list[Path] = []
    sig: list[str] = []
    for b in borrow_specs(ws_dir):
        e = b.name
        d = borrow_dir(b, ws_dir)
        tag = ""
        if m and _CENTRAL_NAME.match(e) and not (ws_dir / e).exists():
            if e == own:
                raise SystemExit(f"workspace.yaml 的 glyph_lib.borrow 写了自己（{e}）")
            if b.pin:
                tag = pinned_lender_copy(src, e, b.pin, branch, cache=cache, bucket=bucket)
                sig.append(f"{b.dir_name}:{tag}")
            else:
                rev, _ = readonly_copy(src, e, branch, (GS,), cache=cache, bucket=bucket)
                sig.append(f"{e}@{rev}")
        else:
            if b.pin:
                raise SystemExit(f"glyph_lib.borrow {e}：钉号要被借库是中心库工作区（本工作区没迁到中心库，或 {e} 是本地路径）")
            if not d.is_dir():
                raise SystemExit(f"借库 {e} 不存在（{d}）；迁到中心库的工作区请写被借工作区的名字")
            sig.append(f"path:{d}")
        if b.scope != "all":
            sig[-1] += f"#{b.scope}"
        dirs.append(borrowed_store(d, b.scope, tag) if (b.scope != "all" or tag) else d)
    return dirs, sig


def uses_corpus_base(ws_dir: Path) -> bool:
    """这个工作区的书库清单有没有写 ``base:``（两级清单，共享方案 S2）。"""
    from .._cv import BASE_WS, manifest_path, versions
    ws_dir = Path(ws_dir)
    if (central_marker(ws_dir) or {}).get("ws") == BASE_WS:
        return False
    for v in versions(ws_dir):
        try:
            if json.loads(manifest_path(ws_dir, v).read_text(encoding="utf-8")).get("base") is not None:
                return True
        except (OSError, ValueError):
            continue
    return False


def refresh_corpus_base(src, ws_dir: Path, *, cache=None, bucket: str = "main", always: bool = False) -> int | None:
    """书库清单用到底库（或 ``always``）时，把 ``corpus-base`` 的底库清单拉成只读副本。返回 rev；用不到返回 None。"""
    from .._cv import BASE_DIR, BASE_WS
    from .materialize import MaterializeError
    m = central_marker(Path(ws_dir)) or {}
    if not m or m.get("ws") == BASE_WS or not (always or uses_corpus_base(ws_dir)):
        return None
    try:
        rev, _ = readonly_copy(src, BASE_WS, str(m.get("branch") or "main"), (BASE_DIR + "/",),
                               cache=cache, bucket=bucket)
    except MaterializeError as e:
        raise SystemExit(f"中心库里还没有底库清单（{BASE_WS}）：先 guji corpus build-base（{e}）") from e
    return rev


def refresh_pua_table(src, ws_dir: Path, *, cache=None, bucket: str = "main", always: bool = False) -> int | None:
    """有书（册 yaml／``book_defaults.yaml``）钉了 ``pua_table_pin``（或 ``always``）时，把共享层 ``pua-wyg`` 拉成只读副本。
    返回 rev；用不到返回 None。库里还没有共享层时报错（钉了版本却拉不到，不能悄悄读空表）。"""
    from ..ops.pua_table import PUA_DIR, PUA_WS, pins_in
    from .materialize import MaterializeError
    m = central_marker(Path(ws_dir)) or {}
    if not m or m.get("ws") == PUA_WS:
        return None
    if not always:
        try:
            if not pins_in(data_dir(Path(ws_dir))):
                return None
        except SystemExit:
            return None
    try:
        rev, _ = readonly_copy(src, PUA_WS, str(m.get("branch") or "main"), (PUA_DIR + "/",),
                               cache=cache, bucket=bucket)
    except MaterializeError as e:
        raise SystemExit(f"中心库里还没有 PUA 码表共享层（{PUA_WS}）：先 guji pua-table publish（{e}）") from e
    return rev


#: 按需拉取（2026-11-02）：``GUJI_PULL_EXCLUDE``（逗号分隔的路径前缀）或 ``guji db pull --exclude`` 给的前缀不拉。
#: 只跑 pipeline 的执行方（任务库 rerun_prep）用它跳过用不着、又大又常变的文件（殿本线上单 100 份 110 MB）。
#: 这样拉下来的数据目录是「部分副本」：状态文件记 ``exclude``，push／sync 一律拒绝，要写库先不带 exclude 整拉一次。
PULL_EXCLUDE_ENV = "GUJI_PULL_EXCLUDE"
#: 只跑 pipeline 用不着的前缀（rerun_prep 缺省用这一组）
RUN_EXCLUDE = ("feedback/lists/proofing/",)


def pull_exclude(extra=()) -> tuple[str, ...]:
    """环境变量与命令行合起来的排除前缀（去重、保序）；``-`` 或空表示不排除。"""
    raw = [x.strip() for x in (os.environ.get(PULL_EXCLUDE_ENV) or "").split(",")] + [str(x).strip() for x in extra]
    out: list[str] = []
    for x in raw:
        if not x or x == "-":
            continue
        if x == "run":                       # 简写：只跑 pipeline 的那一组
            out += [y for y in RUN_EXCLUDE if y not in out]
            continue
        if x == WS_YAML or ".." in x.split("/") or x.startswith("/"):
            raise SystemExit(f"--exclude 不能是 {x!r}")
        if x not in out:
            out.append(x)
    return tuple(out)


def _partial_guard(st: dict | None, what: str) -> None:
    ex = (st or {}).get("exclude") or []
    if ex:
        raise SystemExit(f"本机数据目录是按需拉的部分副本（没拉 {ex}），不能 {what}："
                         f"先不带 --exclude／{PULL_EXCLUDE_ENV} 整拉一次（guji db pull），再{what}")


def pull(src, ws_dir: Path, *, cache=None, bucket: str = "main", force: bool = False,
         glyph: GlyphHooks | None = None, exclude: tuple[str, ...] = (), repair_gaps: bool = False) -> dict:
    """中心库 → 数据目录。本地有未推的改动就拒绝（``force`` 丢掉）。

    ``exclude``（路径前缀）下的文件不拉、本机已有的删掉，状态里记下，之后 push／sync 拒绝（见 ``RUN_EXCLUDE``）。"""
    exclude = tuple(exclude)
    ws_dir = Path(ws_dir)
    m = central_marker(ws_dir) or {}
    data = data_dir(ws_dir)
    ws = str(m["ws"])
    data.mkdir(parents=True, exist_ok=True)
    st = read_state(data)
    if st is not None and not force:
        dirty = local_changes(ws_dir, glyph)
        if dirty:
            raise SystemExit(f"本地有 {len(dirty)} 个文件改了还没推（如 {dirty[:3]}）；"
                             f"先 guji db push，或加 --force 丢掉本地改动")
    old_base = (st or {}).get("base", {})
    tmp = data.parent / f".{data.name}.pull.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    reuse = _local(ws_dir, data)
    seed = data.parent / f".{data.name}.seed"
    seed_rev = _seed_from_snapshot(src, ws, seed) if st is None and _snapshots_on(src) else None
    if seed_rev is not None:                     # 新机器：先用快照里的文件，库里只要之后变了的
        here = reuse
        reuse = lambda rel: here(rel) or ((seed / rel) if (seed / rel).is_file() else None)  # noqa: E731
    delta = None
    if st is not None and not force and not exclude and not st.get("exclude") and not repair_gaps and seed_rev is None:
        # 本机和基准一致（上面查过没有未推改动）：只取库里改了的文件换上去（11-18）
        delta = _materialize_delta(src, ws, tmp, cache, bucket, old_base, int(st["rev"]), reuse=reuse)
    if delta is not None:
        rev, base, stats = delta
        written, removed = _install_delta(tmp, ws_dir, data, set(_diff(old_base, base)))
    else:
        try:
            rev, stats = _materialize(src, ws, tmp, cache, bucket, reuse=reuse, exclude=exclude,
                                      repair_gaps=repair_gaps)
        finally:
            shutil.rmtree(seed, ignore_errors=True)
        written, removed = _install(tmp, ws_dir, data)
        base = _db_manifest(src, ws)
        stats = {"scan": "full", **stats}
    if exclude:
        base = {k: v for k, v in base.items() if not any(k.startswith(x) for x in exclude)}
    store_changed = any(old_base.get(k) != base.get(k) for k in set(old_base) | set(base) if k.startswith(GS))
    out = {"ws": ws, "rev": rev, "data_dir": str(data), "written": written, "removed": removed,
           **{k: v for k, v in stats.items() if k != "ws"}}
    cb = refresh_corpus_base(src, ws_dir, cache=cache, bucket=bucket)
    if cb is not None:
        out["corpus_base"] = cb
    pt = refresh_pua_table(src, ws_dir, cache=cache, bucket=bucket)
    if pt is not None:
        out["pua_table"] = pt
    fp = (st or {}).get("glyph_db_fp")
    bsig = (st or {}).get("borrow", [])
    # 没重建就记下「库比账本旧」，重建了再清。新机器第一次拉（还没有状态）不记：那时本机多半还没有 glyph.db
    stale = bool((st or {}).get(GLYPH_DB_STALE)) or (store_changed and st is not None)
    if glyph is not None:
        extras, bsig = borrow_stores(src, ws_dir, cache=cache, bucket=bucket)
        if extras:
            out["borrow"] = bsig
        if store_changed or not Path(glyph.db_path).exists() or force or bsig != (st or {}).get("borrow", []):
            out["glyph_db"] = glyph.rebuild(ws_dir, data / GS.rstrip("/"), glyph.db_path, extras)
            fp = glyph.fingerprint(glyph.db_path)
            stale = False
    if stale:
        out[GLYPH_DB_STALE] = True
    write_state(data, ws=ws, branch=str(m.get("branch") or "main"), rev=rev, base=base, glyph_db_fp=fp,
                borrow=bsig, **({"exclude": list(exclude)} if exclude else {}),
                **({GLYPH_DB_STALE: True} if stale else {}))
    if seed_rev is not None:
        out["snapshot_rev"] = seed_rev
    if exclude:
        out["exclude"] = list(exclude)
    if stats.get("fetched") and _snapshots_on(src) and not exclude:   # 向库要过文件：存新快照给下一台新机器（部分副本不存）
        out["snapshot_bytes"] = _publish_snapshot(src, ws, rev, ws_dir, data, base)
    return out


#: 字形库快照清单（GUJI-727，``core/glyph_pin.py``）：``config/glyph-pack/g<N>/manifest.json``
GLYPH_PACK_DIR = "config/glyph-pack/"
_GLYPH_PACK_MAN = re.compile(r"^config/glyph-pack/g\d+/manifest\.json$")


def glyph_pack_blobs(ws_dir: Path, data: Path, base: dict[str, str], rows) -> dict[str, Path]:
    """这次 push 新带上的字形库快照清单（基准里没有的）→ 它登记的文本条目 ``{sha: 本机文件}``，随 push 传 R2。

    刻例图不用管：出快照要求数据目录已推干净，图早已按 sha 进桶；借来的库是从中心库拉的，图也在桶里。
    本机文件已与清单不同的拒推：那一版的文本谁都拼不出来了，删掉这个号重出快照。"""
    out: dict[str, Path] = {}
    for r in rows:
        if r.tbl != "files" or not _GLYPH_PACK_MAN.match(r.src_path) or r.src_path in base:
            continue
        man = json.loads((data / r.src_path).read_text(encoding="utf-8"))
        bad = []
        for it in man.get("items", []):
            if it.get("type") != "txt":
                continue
            root = str(it["root"])
            if root == "gs":
                p = data / GS / it["path"]
            elif root.startswith("borrow:"):
                p = borrow_dir_of_root(root[len("borrow:"):], ws_dir) / it["path"]
            else:
                bad.append(f"{root}:{it['path']}")
                continue
            if p.is_file() and sha256(p.read_bytes()) == it["sha256"]:
                out[it["sha256"]] = p
            else:
                bad.append(f"{root}:{it['path']}")
        if bad:
            raise SystemExit(f"字形库快照 {r.src_path} 登记的 {len(bad)} 个文本本机已经变了（如 {bad[:3]}），"
                             f"推上去也没人拼得出这一版；删掉这个号、guji glyph-db snapshot 重出")
    return out


#: push 核「库里已有哪些图」时，要推的图不超过这么多张就按 sha 问（``= ANY``），多了才按工作区整表读
KNOWN_BY_ID_MAX = 2000

def push(conn, ws_dir: Path, *, actor: str | None, dry_run: bool = False, allow_delete: bool = False,
         uploader=None, glyph: GlyphHooks | None = None, shared_writer: bool = False,
         skip_prefixes: tuple[str, ...] = ()) -> dict:
    """数据目录 → 中心库（直连 Postgres；云会话经 wsbridge）。``uploader(images[, ext=])`` 传新图与整理本。

    共享层的只读工作区（``is_shared_ws``）只有升级脚本能写（``shared_writer=True``），``glyphlib-*`` 还只能写一次。

    ``skip_prefixes``：这些前缀下的文件这次一概不推（库里的不动、基准里的记录也原样留着）。换单这类只改待审单的
    流程给 ``(GS,)``，字形库账本就绝不会被它写到（2026-11-04 字形账本被清空事故）。"""
    from .importer import import_scans
    ws_dir = Path(ws_dir)
    data = data_dir(ws_dir)
    st = read_state(data)
    creating = st is None and shared_writer and is_shared_ws(str((central_marker(ws_dir) or {}).get("ws") or ""))
    if creating:                                       # 升级脚本开新的共享层工作区（库里还没有它）
        m = central_marker(ws_dir) or {}
        st = {"ws": str(m["ws"]), "branch": str(m.get("branch") or "main"), "rev": 0, "base": {}}
    if st is None:
        raise SystemExit(f"数据目录 {data} 没有 {STATE}：先 guji db pull -w {ws_dir}")
    _partial_guard(st, "push")
    base = int(st["rev"])
    exported = _export_if_changed(glyph, data, st)
    cur_manifest = manifest(ws_dir, data)
    changed = set(_diff(st.get("base", {}), cur_manifest))
    if skip_prefixes:
        changed = {c for c in changed if not c.startswith(skip_prefixes)}
    incr = (not creating and not shared_writer and bool(changed) and incremental_ok(changed)
            and os.environ.get(FULL_SCAN_ENV) != "1")
    sc = scan(ws_dir, data, only=changed if incr else None)
    if sc.ws != st.get("ws"):
        raise SystemExit(f"数据目录记的工作区是 {st.get('ws')}，workspace.yaml 写的是 {sc.ws}")
    # 本地有哪些文件：增量时用清单（没扫的文件也算在），全量时同以前取扫出来的行
    local_paths = set(cur_manifest) | {r.src_path for r in sc.rows} if incr else {r.src_path for r in sc.rows}
    dup = dup_key_problems(sc.problems, set(_diff(st.get("base", {}), cur_manifest)))
    if dup and os.environ.get(ALLOW_DUP_KEYS_ENV) != "1":
        raise SystemExit(f"要推的文件里有同主键重复行（库里按主键存，「后者覆盖」会丢前面的行，登记的行数却是整个文件的，"
                         f"之后谁都拉不下来，史記 anchors/04.jsonl 2026-11-10）：{'；'.join(dup[:4])}。先去重再推；"
                         f"确要照推设 {ALLOW_DUP_KEYS_ENV}=1")
    # 换图源（GUJI-748 §六）：切过图源的册（册 yaml 有 source_rev），锚里页表 rev 不符的**新**事件拒收
    from .._cv import RevGate
    rgate = RevGate(books_dir=data / "books")
    stale_ev = {r.key[1]: r.src_path for r in sc.rows
                if r.tbl == "events" and not rgate.admits(r.cols.get("kind"), r.cols.get("target") or {})}
    from ..u_stamp import NO_U_ENV, no_u_message, no_u_rows
    no_u = {} if os.environ.get(NO_U_ENV) == "1" else no_u_rows(sc.rows, data)   # 册有账却没带 u 的新事件拒收
    if not creating and not shared_writer:
        from .._cv import push_problems
        problems = push_problems(ws_dir)
        if problems:
            raise SystemExit(problems[0])
    if is_shared_ws(sc.ws) and not shared_writer:
        raise SystemExit(f"{sc.ws} 是共享层的只读工作区（共享方案 3.2 节），普通 push／sync 不能写；"
                         f"由升级脚本出新版本")
    vpre = VERSIONED_SHARED.get(sc.ws)
    if shared_writer and vpre:                         # 按版本目录出的共享层：旧版本只读，只许加新版本
        frozen = sorted(c for c in changed if c.startswith(vpre) and c in st.get("base", {}))
        if frozen:
            raise SystemExit(f"{sc.ws} 的已发布版本不可改、不可删（{frozen[:3]}）；改表请出新版本")

    def guard(cur):
        if creating:
            cur.execute("SELECT 1 FROM changes WHERE ws = %s LIMIT 1", (sc.ws,))
            if cur.fetchone():
                raise StaleBase(f"中心库里已经有 {sc.ws}；先 guji db pull 再写")
        if shared_writer and sc.ws.startswith(SHARED_PREFIX):
            cur.execute("SELECT 1 FROM changes WHERE ws = %s LIMIT 1", (sc.ws,))
            if cur.fetchone():
                raise SystemExit(f"{sc.ws} 已经发布过，版本不可改；出新版本请开新的工作区")
        cur.execute("SELECT 1 FROM changes WHERE ws = %s AND rev > %s LIMIT 1", (sc.ws, base))
        if cur.fetchone():
            raise StaleBase(f"工作区 {sc.ws} 在 rev {base} 之后已有别人写入；先 guji db pull 再推")
        if no_u:                                               # 库里已有的照留（存量走 uid migrate-plan），只拦这次新推的
            cur.execute("SELECT id FROM events WHERE ws = %s AND id = ANY(%s)", (sc.ws, list(no_u)))
            new_nu = sorted(set(no_u) - {r[0] for r in cur.fetchall()})
            if new_nu:
                raise SystemExit(no_u_message(new_nu, no_u))
        if stale_ev:                                           # 库里已有的旧事件照留，只拦这次新推的
            cur.execute("SELECT id FROM events WHERE ws = %s AND id = ANY(%s)", (sc.ws, list(stale_ev)))
            new = sorted(set(stale_ev) - {r[0] for r in cur.fetchall()})
            if new:
                raise SystemExit(f"{len(new)} 条新事件指向已换图源的册，锚里页表 rev 与册 yaml 的 source_rev 不符，"
                                 f"中心库拒收（{rgate.note()}）。如 {new[:3]}（{stale_ev[new[0]]}）。"
                                 f"旧页号的裁决请用 `guji cellvotes migrate` 按格级对照表迁移后再推，"
                                 f"或从本地事件文件里删掉这几条")
        if not creating and not shared_writer:                 # 已发布的语料库、字形库版本不可改（用户 10-20；GUJI-727）
            # 区间查询走主键 (ws, src_path)；LIKE＋OR 会扫该 ws 的全部 files 行
            db_sha = {}
            for lo, hi, pat in (("config/corpus-pack/v", "config/corpus-pack/w", "config/corpus-pack/v%%/manifest.json"),
                                ("config/glyph-pack/g", "config/glyph-pack/h", "config/glyph-pack/g%%/manifest.json")):
                cur.execute("SELECT src_path, sha256 FROM files WHERE ws = %s AND src_path >= %s AND src_path < %s "
                            "AND src_path LIKE %s", (sc.ws, lo, hi, pat))
                db_sha.update(cur.fetchall())
            changed = sorted(r.src_path for r in sc.rows if r.tbl == "files" and r.src_path in db_sha
                             and r.cols.get("sha256", db_sha[r.src_path]) != db_sha[r.src_path])
            if changed:
                what = "字形库" if changed[0].startswith(GLYPH_PACK_DIR) else "语料库"
                raise SystemExit(f"{what}清单 {changed[:3]} 已发布，版本不可改；出新版本"
                                 f"（{'guji glyph-db snapshot' if what == '字形库' else 'guji corpus build'}）")
        cur.execute("SELECT src_path FROM source_files WHERE ws = %s"
                    + "".join(f" UNION ALL SELECT src_path FROM {t} WHERE ws = %s" for t in BLOB_TABLES),
                    (sc.ws,) * (1 + len(BLOB_TABLES)))
        gone = sorted({r[0] for r in cur.fetchall()} - local_paths)   # 锚图也算：v0.4.0 及更早 pull 不还原锚图
        if gone and not allow_delete:
            raise FileDeleteRefused(f"本地少了 {len(gone)} 个库里有的文件（如 {gone[:3]}）；"
                                    f"确认要删再加 --allow-delete")

    # 要进 R2 的文件，按 R2 键后缀分组：刻例图、锚图是 png，整理本是 txt（scope.BLOB_TABLES）
    images: dict[str, dict[str, Path]] = {}
    patch_dir = data / GS / "patches"
    for r in sc.rows:
        if r.tbl == "glyph_instances" and r.cols.get("patch_sha"):
            images.setdefault("png", {})[r.cols["patch_sha"]] = patch_dir / f"{r.key[0].replace(':', '_')}.png"
        elif r.tbl in BLOB_TABLES:
            images.setdefault(BLOB_TABLES[r.tbl], {})[r.cols["sha256"]] = data / r.src_path
    lost = sorted(str(p) for g in images.values() for p in g.values() if not p.exists())
    if lost:
        raise SystemExit(f"实例引用的 {len(lost)} 张图本地没有（如 {lost[:3]}）")
    pack_txt = glyph_pack_blobs(ws_dir, data, st.get("base", {}), sc.rows)
    if pack_txt:                                       # 新出的字形库快照：登记的文本随这次 push 进 R2
        images.setdefault("txt", {}).update(pack_txt)
    if images and uploader is not None and not dry_run:
        # 库里已有的图（导入或之前推过时已进桶）不再逐张签名核对：每次推都核两万张要十几分钟，
        # 连接闲置被断，事务一开就死（10-19 D 推 vol01 裁决两次失败）
        # 要推的图不多（增量推通常几张到几百张）就只问这几张在不在，不再按工作区整表读 patch_sha
        # （殿本 18 万行，中心库读量大户；GM2 11-23）；全量扫描、图多时照旧整表读一次
        known: dict[str, set[str]] = {}
        with conn.cursor() as cur:
            png = sorted(images.get("png", {}))
            if png and len(png) <= KNOWN_BY_ID_MAX:
                cur.execute("SELECT patch_sha FROM glyph_instances WHERE ws = %s AND patch_sha = ANY(%s)", (sc.ws, png))
            else:
                cur.execute("SELECT patch_sha FROM glyph_instances WHERE ws = %s AND patch_sha IS NOT NULL",
                            (sc.ws,))
            known["png"] = {r[0] for r in cur.fetchall()}
            for t, ext in BLOB_TABLES.items():
                cur.execute("SELECT to_regclass(%s)", (t,))
                if cur.fetchone()[0] is None:          # 新表还没建（导入时 apply_schema 才建）
                    continue
                want = sorted(images.get(ext, {}))
                if want and len(want) <= KNOWN_BY_ID_MAX:
                    cur.execute(f"SELECT sha256 FROM {t} WHERE ws = %s AND sha256 = ANY(%s)", (sc.ws, want))
                else:
                    cur.execute(f"SELECT sha256 FROM {t} WHERE ws = %s", (sc.ws,))
                known.setdefault(ext, set()).update(r[0] for r in cur.fetchall())
        conn.commit()
        images = {ext: {sha: p for sha, p in g.items() if sha not in known.get(ext, ())}
                  for ext, g in images.items()}
        images = {ext: g for ext, g in images.items() if g}
    up = None
    if uploader is not None and not dry_run and images:
        res = {ext: (uploader(g) if ext == "png" else uploader(g, ext=ext))   # 只收图的 uploader 照旧能用
               for ext, g in sorted(images.items())}
        up = res["png"] if list(res) == ["png"] else res
    only = {r.src_path for r in sc.rows if not r.src_path.startswith(skip_prefixes)} if skip_prefixes else None
    if incr:                                           # 只比这些文件的行；本地删掉的文件也在里面（库里那几行跟着删，受删除闸管）
        only = set(changed)
    rep = import_scans(conn, [sc], label=f"push:{sc.ws}@{base}", actor=actor, dry_run=dry_run,
                       source="push", guard=guard, allow_delete=allow_delete, only_paths=only)
    out = rep.as_dict()
    out.update(base_rev=base, images=up, glyph_exported=exported, data_dir=str(data),
               scan="incremental" if incr else "full", scanned_files=len(changed) if incr else None)
    if not dry_run:
        fp = glyph.fingerprint(glyph.db_path) if glyph is not None and Path(glyph.db_path).exists() else st.get("glyph_db_fp")
        new_base = manifest(ws_dir, data)
        if skip_prefixes:                                  # 没推的文件，基准里仍记原来的（下次 sync 才还看得出它们是本地改动）
            old = st.get("base", {})
            for rel in set(new_base) | set(old):
                if rel.startswith(skip_prefixes):
                    if rel in old:
                        new_base[rel] = old[rel]
                    else:
                        new_base.pop(rel, None)
        write_state(data, ws=sc.ws, branch=st.get("branch", "main"), rev=rep.rev_to,
                    base=new_base, glyph_db_fp=fp, borrow=st.get("borrow", []),
                    **({GLYPH_DB_STALE: True} if st.get(GLYPH_DB_STALE) else {}))
    return out


def migrate(src, ws_dir: Path, *, cache=None, bucket: str = "main", keep_local: bool = False,
            dry_run: bool = False, glyph: GlyphHooks | None = None) -> dict:
    """一次性：工作区里的数据核对后挪进数据目录，工作区里删掉，写标记。

    工作区里的文件与库里不一致就停下列出来（多半是检出旧了，或有没进库的改动）；确认本地的才对，
    加 ``keep_local``：数据目录先按库还原，再用工作区里的这些文件盖上去，成为待推改动。
    glyph.db 不动（它是本地派生物，重建会让库指纹变）。"""
    from .pull import workspace_id
    ws_dir = Path(ws_dir)
    if central_marker(ws_dir):
        rep = adopt(ws_dir, dry_run=dry_run)
        if rep is None:
            raise SystemExit(f"{ws_dir} 已经迁过（有 {CENTRAL_MARKER}）；要更新用 guji db pull")
        return rep
    ws = workspace_id(ws_dir)
    branch = getattr(src, "branch", "main")
    db = _db_manifest(src, ws)
    if not db:
        raise SystemExit(f"中心库里没有工作区 {ws}（分支 {branch}）")
    local = {rel: sha256(p.read_bytes()) for rel, p in _walk(ws_dir, patches=False)}
    differ = sorted(rel for rel in local if db.get(rel) != local[rel])
    report = {"ws": ws, "branch": branch, "data_dir": str(central_data_dir(ws, branch)),
              "local_files": len(local), "db_files": len(db), "differ": differ[:50], "n_differ": len(differ),
              "dry_run": dry_run}
    if differ and not keep_local:
        raise SystemExit(f"工作区里有 {len(differ)} 个文件与中心库不一致（如 {differ[:5]}）：检出旧了就先 git pull，"
                         f"确认本地的才对就加 --keep-local（迁完它们是待推改动，再 guji db push）")
    if dry_run:
        return report
    data = central_data_dir(ws, branch)
    data.mkdir(parents=True, exist_ok=True)
    tmp = data.parent / f".{data.name}.pull.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    rev, stats = _materialize(src, ws, tmp, cache, bucket)
    (tmp / WS_YAML).unlink(missing_ok=True)            # 工作区自己的 workspace.yaml 不动
    written, _ = _install(tmp, ws_dir, data)
    fp = glyph.fingerprint(glyph.db_path) if glyph is not None and Path(glyph.db_path).exists() else None
    write_state(data, ws=ws, branch=branch, rev=rev, base=_db_manifest(src, ws), glyph_db_fp=fp)
    for rel in differ:
        dst = data / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ws_dir / rel, dst)
    (ws_dir / CENTRAL_MARKER).write_text(json.dumps({"ws": ws, "branch": branch}, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
    adopted = adopt(ws_dir)                            # 工作区根的 corpus-pack/ 挪进数据目录 config/
    removed = 0
    for rel, p in list(_walk(ws_dir)):
        p.unlink()
        removed += 1
    for pre in SCOPE:                                  # 删空目录（备份等不归库管的文件留着）
        d = ws_dir / pre.rstrip("/")
        if d.is_dir():
            for sub in sorted((x for x in d.rglob("*") if x.is_dir()), key=lambda x: -len(x.parts)):
                if not any(sub.iterdir()):
                    sub.rmdir()
            if not any(d.iterdir()):
                d.rmdir()
    report.update(rev=rev, written=written, removed_from_workspace=removed,
                  pending=len(differ) + (adopted or {}).get("adopt", 0),
                  **{k: v for k, v in stats.items() if k != "ws"})
    return report


def init(src, ws_dir: Path, *, dry_run: bool = False) -> dict:
    """新开一部书：中心库里还没有这个工作区时，把工作区里的数据（册 yaml、config 等）挪进数据目录、写标记，
    基准记成 rev 0、空清单——之后 ``guji db push`` 把它们整批推上去，库里就有了这个工作区（``workspaces`` 一行、
    ``books`` 各册）。

    和 ``migrate`` 的分别：migrate 要库里已有这个工作区（从 git 灌过），逐文件核对；init 只给库里没有的工作区用，
    库里已有（哪怕只有一次写入）就拒绝，让用 pull。共享层工作区（``corpus-base``、``glyphlib-*``）由升级脚本开，不走这里。"""
    from .._cv import central_marker
    from .pull import workspace_id
    ws_dir = Path(ws_dir)
    if central_marker(ws_dir):
        raise SystemExit(f"{ws_dir} 已经在中心库（有 {CENTRAL_MARKER}）；要更新用 guji db pull／push")
    ws = workspace_id(ws_dir)
    if is_shared_ws(ws):
        raise SystemExit(f"{ws} 是共享层工作区，由升级脚本开，不用 db init")
    branch = getattr(src, "branch", "main")
    if _db_manifest(src, ws) or src.changes_since(ws, 0):
        raise SystemExit(f"中心库（分支 {branch}）里已经有工作区 {ws}：用 guji db pull -w {ws_dir}")
    if not (ws_dir / "books").is_dir() or not any((ws_dir / "books").glob("*.yaml")):
        raise SystemExit(f"{ws_dir}/books/ 下没有册 yaml：先写好 books/<册>.yaml（控制台只认有册的工作区）")
    data = central_data_dir(ws, branch)
    if data.exists() and any(data.iterdir()):
        raise SystemExit(f"数据目录 {data} 已有东西；先弄清是哪来的")
    files = [rel for rel, _ in _walk(ws_dir)]
    report = {"ws": ws, "branch": branch, "data_dir": str(data), "files": files, "dry_run": dry_run}
    if dry_run:
        return report
    data.mkdir(parents=True, exist_ok=True)
    for rel, p in list(_walk(ws_dir)):
        dst = data / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), dst)
    for pre in SCOPE:                                  # 删空目录
        d = ws_dir / pre.rstrip("/")
        if d.is_dir():
            for sub in sorted((x for x in d.rglob("*") if x.is_dir()), key=lambda x: -len(x.parts)):
                if not any(sub.iterdir()):
                    sub.rmdir()
            if not any(d.iterdir()):
                d.rmdir()
    write_state(data, ws=ws, branch=branch, rev=0, base={}, glyph_db_fp=None)
    (ws_dir / CENTRAL_MARKER).write_text(json.dumps({"ws": ws, "branch": branch}, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
    report["pending"] = len(files) + 1                 # 加 workspace.yaml
    return report


#: 收录范围后来才扩进来的工作区根目录 → 数据目录里的落点（2026-10-19 共享方案 2.2 节：整理本、语料库清单）
ADOPT = {"corpus": "corpus", "corpus-pack": "config/corpus-pack"}


def adopt(ws_dir: Path, *, dry_run: bool = False) -> dict | None:
    """补迁：已迁过的工作区，根上还留着后来才纳入中心库的目录（``ADOPT``），挪进数据目录成为待推改动。

    数据目录里已有同路径同内容的文件直接删掉工作区里的；内容不同就整次停下，什么都不动。
    没有可补迁的返回 None。挪完要 ``guji db push``（或 sync）才进库。"""
    ws_dir = Path(ws_dir)
    data = data_dir(ws_dir)
    moves: list[tuple[Path, Path, str]] = []
    for src_name, dst_rel in ADOPT.items():
        root = ws_dir / src_name
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            rel = f"{dst_rel}/{p.relative_to(root).as_posix()}"
            if classify(rel) is None:
                continue
            moves.append((p, data / rel, rel))
    if not moves:
        return None
    clash = [rel for p, q, rel in moves if q.exists() and sha256(q.read_bytes()) != sha256(p.read_bytes())]
    if clash:
        raise SystemExit(f"补迁：数据目录里已有 {len(clash)} 个同路径但内容不同的文件（如 {clash[:3]}）；"
                         f"先弄清哪份对，再手工处理")
    same = sum(1 for _, q, _ in moves if q.exists())
    report = {"ws_dir": str(ws_dir), "data_dir": str(data), "adopt": len(moves) - same, "already": same,
              "files": [rel for *_, rel in moves][:50], "dry_run": dry_run}
    if dry_run:
        return report
    for p, q, _ in moves:
        if q.exists():
            p.unlink()
        else:
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), q)
    for src_name in ADOPT:                              # 删空目录（不归库管的文件留着）
        d = ws_dir / src_name
        if d.is_dir():
            for sub in sorted((x for x in d.rglob("*") if x.is_dir()), key=lambda x: -len(x.parts)):
                if not any(sub.iterdir()):
                    sub.rmdir()
            if not any(d.iterdir()):
                d.rmdir()
    report["next"] = f"guji db push -w {ws_dir}"
    return report


# ---- 同步：拉库里的新改动、与本地改动合并、再推（GUJI-608 B 块）----

class SyncConflict(RuntimeError):
    pass


APPEND_ONLY = {t for t, spec in TABLES.items() if spec.append_only}


def _split_append(local: bytes, remote: bytes) -> tuple[list[str], list[str], list[str]]:
    """共同前缀、库里在前缀后的新行、本地在前缀后的新行（与库里相同的行不重复）。"""
    lo, re_ = local.decode("utf-8").splitlines(), remote.decode("utf-8").splitlines()
    n = 0
    while n < min(len(lo), len(re_)) and lo[n] == re_[n]:
        n += 1
    tail_r = re_[n:]
    seen = set(tail_r)
    return lo[:n], tail_r, [x for x in lo[n:] if x not in seen]


def _join(lines: list[str]) -> bytes:
    return ("\n".join(lines) + "\n").encode("utf-8") if lines else b""


def _merge_append(local: bytes, remote: bytes) -> bytes | None:
    """两边都只在共同前缀后面追加了行 → 前缀＋库里的新行＋本地的新行（本地与库里相同的行不重复）。

    不知道基准内容，共同前缀就当基准：若有一边其实改了前缀里的行，合出来的文件会少那一边的旧行，
    推的时候只追加台账少行会被导入器拒掉（``DeleteRefused``），不会悄悄丢数据。"""
    head, tail_r, tail_l = _split_append(local, remote)
    return _join(head + tail_r + tail_l)


def _merge_events(local: bytes, remote: bytes) -> tuple[bytes, dict[str, str]]:
    """人裁事件文件的合并（规范 §9 F-6）：同 ``_merge_append``，再给本地新行里与库里撞号的重新编号。

    两台机器往同一批次追加时各自从同一个 ``seq`` 往后编，合出来同一 ``id`` 两行内容不同：记账互相遮挡、
    库主键 ``(ws, src_path, id)`` 冲突。库里的行已经推出去了、别的机器可能已消费，所以只动本地的：
    顺延到该批次合并后的下一个空 ``seq``，与 ``EventLog.append`` 撞号顺延同一语义。
    返回（合并后的字节，旧 id → 新 id）。"""
    head, tail_r, tail_l = _split_append(local, remote)
    rows = [json.loads(x) for x in head + tail_r if x.strip()]
    taken = {r.get("id") for r in rows}
    top: dict[str, int] = {}
    for r in rows:
        if isinstance(r.get("seq"), int):
            top[r.get("batch")] = max(top.get(r.get("batch"), 0), r["seq"])
    renamed: dict[str, str] = {}
    out_l = []
    for x in tail_l:
        if not x.strip():
            continue
        d = json.loads(x)
        b = d.get("batch")
        if d.get("id") in taken and isinstance(d.get("seq"), int):
            s = top.get(b, 0) + 1
            new = f"evt_{b}_{s:06d}"
            renamed[d["id"]] = new
            d["id"], d["seq"] = new, s
            x = json.dumps(d, ensure_ascii=False, sort_keys=True)
        if isinstance(d.get("seq"), int):
            top[b] = max(top.get(b, 0), d["seq"])
        taken.add(d.get("id"))
        out_l.append(x)
    return _join(head + tail_r + out_l), renamed


def _rename_ids(text: str, renamed: dict[str, str]) -> str:
    for old, new in renamed.items():
        text = text.replace(f'"{old}"', f'"{new}"')
    return text


def _apply_renames(renamed: dict[str, str], *, merged: dict[str, bytes], local_only: dict[str, Path],
                   remote: dict[str, bytes]) -> list[str]:
    """本地事件改了 id → 本地写的记账、补锚、金标里引用它的地方跟着改（只改本地新写的行）。

    ``merged``：两边都改了的只追加台账，按库里的字节切出本地新行再改；``local_only``：只有本地改了的文件，
    基准之后的新 id 只可能是本地写的，整文件改。"""
    if not renamed:
        return []
    touched = []
    for rel, b in list(merged.items()):
        if classify(rel) == "events" or rel not in remote:
            continue
        head, tail_r, tail_l = _split_append(b, remote[rel])
        nl = [_rename_ids(x, renamed) for x in tail_l]
        if nl != tail_l:
            merged[rel] = _join(head + tail_r + nl)
            touched.append(rel)
    for rel, path in local_only.items():
        if classify(rel) == "events" or not path.exists() or path.suffix not in (".jsonl", ".json"):
            continue
        t = path.read_text(encoding="utf-8")
        nt = _rename_ids(t, renamed)
        if nt != t:
            path.write_text(nt, encoding="utf-8")
            touched.append(rel)
    return sorted(touched)


def _event_ids(b: bytes) -> set[str]:
    out = set()
    for x in b.decode("utf-8").splitlines():
        if x.strip():
            try:
                out.add(json.loads(x).get("id"))
            except ValueError:
                continue
    return out - {None}


def _local_new_event_ids(data: Path, tmp: Path, merged: dict[str, bytes], mine: set[str]) -> set[str]:
    """本地有、库里没有的人裁事件 id（合并后的本地文件对库里那份）。"""
    ids: set[str] = set()
    for rel in sorted(mine):
        if classify(rel) != "events":
            continue
        b = merged.get(rel)
        if b is None:
            p = data / rel
            if not p.exists():
                continue
            b = p.read_bytes()
        r = tmp / rel
        ids |= _event_ids(b) - (_event_ids(r.read_bytes()) if r.exists() else set())
    return ids


def _drop_glyph_consumed(data: Path, ids: set[str]) -> int:
    """字形库消费者（``consumed/glyph*.jsonl``）里这些事件的记账删掉，好让它们在库里的字形库上重新消费。返回删的行数。"""
    n = 0
    for f in sorted((data / "feedback" / "consumed").glob("glyph*.jsonl")):
        lines = f.read_text(encoding="utf-8").splitlines()
        keep = []
        for x in lines:
            try:
                drop = bool(x.strip()) and json.loads(x).get("event") in ids
            except ValueError:
                drop = False
            n += drop
            if not drop:
                keep.append(x)
        if len(keep) != len(lines):
            f.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
    return n


def sync(src, conn, ws_dir: Path, *, actor: str | None, cache=None, bucket: str = "main",
         uploader=None, glyph: GlyphHooks | None = None, dry_run: bool = False,
         replay: Callable[[set[str]], dict] | None = None, skip_prefixes: tuple[str, ...] = ()) -> dict:
    """拉 → 合并 → 推，一步做完（控制台写完、定时任务都用它）。

    库里在基准 rev 之后没人写过：直接推。有人写过：库里改了、本地没改的文件取库里的；本地改了、库里没改的
    留本地的；两边都改了的只追加台账（events、consumed、anchors）按「共同前缀＋库里新行＋本地新行」合，
    别的文件两边都改了就整次停下（``SyncConflict``），什么都不动。

    字形库（``output/glyph_store/``）两边都改了、又给了 ``replay`` 时不停：字形库是消费者从人裁事件算出来的，
    本地那份改动就是本地新事件过消费者的结果。取库里的字形库、重建 glyph.db，删掉这些事件在字形库消费者
    （``consumed/glyph*.jsonl``）里的记账，再用 ``replay(新事件 id)`` 让它们在库里的字形库上重新消费一遍，
    然后照常推（册 005 10-23 两次手工 ``pull --force`` 重写重推，就是这一步）。"""
    ws_dir = Path(ws_dir)
    data = data_dir(ws_dir)
    st = read_state(data)
    if st is None:
        raise SystemExit(f"数据目录 {data} 没有 {STATE}：先 guji db pull -w {ws_dir}")
    _partial_guard(st, "sync")
    ws = str(st["ws"])
    st = _refresh_stale_db(glyph, ws_dir, data, st, src=src, cache=cache, bucket=bucket)
    exported = _export_if_changed(glyph, data, st)
    base = st["base"]
    local = manifest(ws_dir, data)
    mine = set(_diff(base, local))
    if skip_prefixes:                                  # 不推的前缀（字形库）：本地怎么改都不算待推改动
        mine = {m for m in mine if not m.startswith(skip_prefixes)}
    out: dict = {"ws": ws, "local_changes": sorted(mine), "glyph_exported": exported}
    if glyph is not None and borrow_entries(ws_dir):    # 借来的库有新版：只重建 glyph.db，不算本地改动
        extras, bsig = borrow_stores(src, ws_dir, cache=cache, bucket=bucket)
        if bsig != st.get("borrow", []) and not dry_run and Path(glyph.db_path).exists():
            out["glyph_db"] = glyph.rebuild(ws_dir, data / GS.rstrip("/"), glyph.db_path, extras)
            st = {**st, "borrow": bsig, "glyph_db_fp": glyph.fingerprint(glyph.db_path)}
            write_state(data, **{k: v for k, v in st.items() if k != "at"})
            out["borrow"] = bsig
    if not dry_run:                                    # 底库清单有新版：只更新只读副本
        cb = refresh_corpus_base(src, ws_dir, cache=cache, bucket=bucket)
        if cb is not None:
            out["corpus_base"] = cb
        pt = refresh_pua_table(src, ws_dir, cache=cache, bucket=bucket)
        if pt is not None:
            out["pua_table"] = pt
    if not src.changes_since(ws, int(st["rev"]), limit=1):
        if not mine:
            return {**out, "action": "nothing"}
        return {**out, "action": "push", "push": push(conn, ws_dir, actor=actor, dry_run=dry_run,
                                                       uploader=uploader, glyph=glyph,
                                                       skip_prefixes=skip_prefixes)}
    # 库里有新改动：拉到旁边，逐文件合
    tmp = data.parent / f".{data.name}.sync.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    # 只取库里改了的文件（加本地改了的那些在库里的版本，合并要用）；拿不准就整拉（11-18：殿本 sync 读整库 81 s）
    delta = _materialize_delta(src, ws, tmp, cache, bucket, base, int(st["rev"]), reuse=_local(ws_dir, data),
                               extra=mine, want_patch=lambda n: not (data / GS / "patches" / n).exists())
    if delta is not None:
        rev, remote, pstats = delta
    else:
        rev, pstats = _materialize(src, ws, tmp, cache, bucket, reuse=_local(ws_dir, data))
        remote = _db_manifest(src, ws)
        pstats = {"scan": "full", **{k: v for k, v in pstats.items() if k in ("files", "reused", "fetched")}}
    out["pull"] = pstats
    theirs = set(_diff(base, remote))
    both = sorted(mine & theirs)
    merged: dict[str, bytes] = {}
    renamed: dict[str, str] = {}
    conflicts = []
    glyph_taken: list[str] = []
    for rel in both:
        lp = (ws_dir if rel == WS_YAML else data) / rel
        rp = tmp / rel
        if local.get(rel) == remote.get(rel):
            continue                                       # 两边改成一样
        if classify(rel) == "events" and lp.exists() and rp.exists():
            merged[rel], ren = _merge_events(lp.read_bytes(), rp.read_bytes())
            renamed.update(ren)
            continue
        if (classify(rel) in APPEND_ONLY or rel.endswith(".items.jsonl")) and lp.exists() and rp.exists():
            # 待审条目（feedback/lists/pending/…/<章>.items.jsonl）也只追加：两边各自追加的版本都留，当前状态取每条最后一行
            m = _merge_append(lp.read_bytes(), rp.read_bytes())
            if m is not None:
                merged[rel] = m
                continue
        if replay is not None and glyph is not None and rel.startswith(GS) and rp.exists():
            merged[rel] = rp.read_bytes()                  # 字形库取库里的，本地新事件之后重新消费
            glyph_taken.append(rel)
            continue
        conflicts.append(rel)
    replay_ids: set[str] = set()
    if glyph_taken:
        replay_ids = _local_new_event_ids(data, tmp, merged, mine)
        if not replay_ids:                                 # 本地字形库改了却没有新事件：不是消费者算的，不敢丢
            conflicts += glyph_taken
            glyph_taken = []
        else:                                              # 本地只改了的字形库文件也回到库里那份，免得同一事件算两遍
            for rel in sorted(mine - theirs):
                if rel.startswith(GS) and not rel.startswith(GS + "patches/"):
                    merged[rel] = (tmp / rel).read_bytes() if (tmp / rel).exists() else None
                    glyph_taken.append(rel)
    if conflicts:
        shutil.rmtree(tmp, ignore_errors=True)
        raise SyncConflict(f"这些文件本地和库里都改了，合不了（如 {conflicts[:5]}）；"
                           f"要库里的：guji db pull --force；要本地的：手工合进去再推")
    out.update(remote_changes=sorted(theirs), merged=sorted(merged), rev_remote=rev)
    if glyph_taken:
        out["glyph_taken_remote"] = glyph_taken
    if renamed:
        out["renumbered"] = renamed
    if dry_run:
        shutil.rmtree(tmp, ignore_errors=True)
        return {**out, "action": "merge (dry-run)"}
    # 库里改了、本地没改的 → 用库里的；本地删了而库里没动的保持删除
    store_changed = False
    for rel in sorted(theirs - mine):
        dst = (ws_dir if rel == WS_YAML else data) / rel
        if (tmp / rel).exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp / rel, dst)
        elif dst.exists():
            dst.unlink()
        store_changed |= rel.startswith(GS)
    patches = tmp / GS / "patches"                         # 库里新实例的刻例图
    if patches.is_dir():
        for p in patches.iterdir():
            q = data / GS / "patches" / p.name
            if not q.exists():
                q.parent.mkdir(parents=True, exist_ok=True)
                os.replace(p, q)
    if renamed:                                            # 撞号重编：本地引用跟着改（规范 §9 F-6）
        out["renamed_refs"] = _apply_renames(
            renamed, merged=merged, remote={r: (tmp / r).read_bytes() for r in merged if (tmp / r).exists()},
            local_only={r: data / r for r in sorted(mine - theirs) if r != WS_YAML})
    for rel, b in merged.items():
        if b is None:
            (data / rel).unlink(missing_ok=True)
        else:
            (data / rel).write_bytes(b)
    shutil.rmtree(tmp, ignore_errors=True)
    if glyph_taken:
        store_changed = True
        out["replay_unconsumed"] = _drop_glyph_consumed(data, replay_ids)
    fp = st.get("glyph_db_fp")
    stale = bool(st.get(GLYPH_DB_STALE)) or store_changed
    if glyph is not None and store_changed and Path(glyph.db_path).exists():
        extras, _ = borrow_stores(src, ws_dir, cache=cache, bucket=bucket)
        out["glyph_db"] = glyph.rebuild(ws_dir, data / GS.rstrip("/"), glyph.db_path, extras)
        fp = glyph.fingerprint(glyph.db_path)
        stale = False
    write_state(data, ws=ws, branch=st.get("branch", "main"), rev=rev, base=remote, glyph_db_fp=fp,
                borrow=st.get("borrow", []), **({GLYPH_DB_STALE: True} if stale else {}))
    if replay_ids:
        out["replay"] = replay(replay_ids)
        _export_if_changed(glyph, data, read_state(data))  # 重新消费写的是 glyph.db，导出成字形库再比对、推
    if not _diff(remote, manifest(ws_dir, data)):
        if _snapshots_on(src):
            out["snapshot_bytes"] = _publish_snapshot(src, ws, rev, ws_dir, data, remote)
        return {**out, "action": "pulled"}
    return {**out, "action": "merged+push", "push": push(conn, ws_dir, actor=actor, uploader=uploader, glyph=glyph,
                                                 skip_prefixes=skip_prefixes)}
