"""任务库搬家：美国机 Postgres（jobs schema）→ D1 guji-jobs（2026-11-22 用户定）。

    python scripts/jobs_pg_to_d1.py sync [--full]   # 增量同步：上次同步以来 Postgres 里变了的行 upsert 进 D1（经 Worker）
    python scripts/jobs_pg_to_d1.py check           # 两边逐表核行数与最大号（D1 ≥ Postgres 即过）
    python scripts/jobs_pg_to_d1.py seed-seq        # D1 自增号预留到 Postgres 最大号之后
    python scripts/jobs_pg_to_d1.py dump --out f.sql [--full]   # 同 sync，但写成文件（可用 wrangler d1 execute 导）

交接期（用户 11-22：不等队列空，先复制、交接期多同步几次、随时切）：
1. ``sync --full`` 首次全量；之后反复 ``sync``（水位记在 D1 ``meta.pg_sync_at``，每次回看 2 分钟）。
2. 切换：``seed-seq`` → 合改缺省的版本（执行方空闲时自更新改连 D1）→ 继续 ``sync``，直到老会话手上的单都在
   Postgres 收完尾（同步过来）→ Postgres 设只读。
upsert 只让「更新的」覆盖：job 按 ``updated_at``（``notified_at`` 取两边有值的）、attempt 按 ``heartbeat_at``／已收尾、
worker 按 ``seen_at``；切换后 D1 这边改过的行时间更新，不会被 Postgres 的旧值盖回去。Postgres 里还没收尾的领单，
D1 里租约至少延到同步后 60 分钟，免得 D1 的执行方在交接期把别处正跑着的单当失联收回。
连 Postgres 用 databases.toml 的 pg-tunnel 连法（``[jobs]`` 或切换后的 ``[jobs_pg]``）；连 D1 用 ``--d1-url``（缺省
https://data.open-guji.com），令牌同 JOBSDB_TOKEN。时间统一成 UTC 毫秒 Z 串（同 store_d1 的 NOW）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
from importlib import resources

TABLES = ["job", "attempt", "event", "result", "worker", "perf_run", "perf_step"]   # 外键先后
ORDER = {"perf_run": "run_id", "perf_step": "run_id, step", "worker": "name"}
MAX_STMT = 90_000          # D1 单条 SQL 上限 100 KB


def d1_columns() -> dict[str, list[str]]:
    db = sqlite3.connect(":memory:")
    db.executescript(resources.files("guji_manager.jobs").joinpath("schema_d1.sql").read_text(encoding="utf-8"))
    return {t: [r[1] for r in db.execute(f"PRAGMA table_info({t})") if r[1] != "mark"] for t in TABLES}


def lit(v) -> str:
    from guji_manager.jobs.d1 import iso_z
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    if hasattr(v, "is_finite"):                    # Decimal
        return str(v)
    if isinstance(v, dt.datetime):
        v = iso_z(v)
    elif isinstance(v, (dict, list, tuple)):
        v = json.dumps(v, ensure_ascii=False)
    return "'" + str(v).replace("'", "''") + "'"


def pg(snapshot: bool = False):
    from guji_manager.jobs import jobsdb
    c = jobsdb.connect()
    if snapshot:      # 一个只读快照事务里导完，各表口径一致
        import psycopg
        c.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        c.read_only = True
    else:
        c.autocommit = True
    return c


SINCE = {     # 增量：上次水位之后变了的行
    "job": "updated_at >= %(s)s OR created_at >= %(s)s OR notified_at >= %(s)s",
    "attempt": "started_at >= %(s)s OR heartbeat_at >= %(s)s OR finished_at >= %(s)s OR finished_at IS NULL",
    "event": "at >= %(s)s",
    "result": "at >= %(s)s",
    "worker": "seen_at >= %(s)s",
    "perf_run": "pushed_at >= %(s)s",
    "perf_step": "run_id IN (SELECT run_id FROM jobs.perf_run WHERE pushed_at >= %(s)s)",
}
LEASE_HOLD_MIN = 60


def _upsert(t: str, cs: list[str]) -> str:
    """ON CONFLICT 子句：只让更新的覆盖。"""
    key = {"worker": "(name)", "perf_run": "(run_id)", "perf_step": "(run_id, step)"}.get(t, "(id)")
    upd = lambda skip=(): ", ".join(f"{c} = excluded.{c}" for c in cs if c not in skip)  # noqa: E731
    if t == "job":
        return (f" ON CONFLICT {key} DO UPDATE SET {upd(('id', 'notified_at'))},"
                " notified_at = coalesce(excluded.notified_at, job.notified_at)"
                " WHERE excluded.updated_at >= job.updated_at OR (job.notified_at IS NULL AND excluded.notified_at IS NOT NULL)")
    if t == "attempt":
        return (f" ON CONFLICT {key} DO UPDATE SET {upd(('id',))}"
                " WHERE attempt.finished_at IS NULL AND (excluded.finished_at IS NOT NULL"
                " OR excluded.heartbeat_at >= attempt.heartbeat_at)")
    if t == "worker":
        return f" ON CONFLICT {key} DO UPDATE SET {upd(('name',))} WHERE excluded.seen_at > worker.seen_at"
    if t in ("perf_run", "perf_step"):
        return f" ON CONFLICT {key} DO UPDATE SET {upd()}"
    return " ON CONFLICT DO NOTHING"           # event、result 只追加


def statements(c, since):
    """Postgres 一个只读快照里取变了的行，生成 D1 能执行的 upsert 语句（每条 ≤ MAX_STMT）。返回 (语句, 统计, 新水位)。"""
    cols = d1_columns()
    now = c.execute("SELECT now()").fetchone()[0]
    hold = now + dt.timedelta(minutes=LEASE_HOLD_MIN)
    out: list[str] = ["PRAGMA defer_foreign_keys = true"]
    stats: dict[str, int] = {}
    for t in TABLES:
        cs = cols[t]
        where = f" WHERE {SINCE[t]}" if since is not None else ""
        cur = c.cursor(name=f"dump_{t}")       # 服务器端游标，别一次拉进内存
        cur.itersize = 2000
        cur.execute(f"SELECT {', '.join(cs)} FROM jobs.{t}{where} ORDER BY {ORDER.get(t, 'id')}",
                    {"s": since} if since is not None else None)
        head = f"INSERT INTO {t} ({', '.join(cs)}) VALUES\n"
        tail = _upsert(t, cs)
        li = cs.index("lease_until") if t == "attempt" else -1
        fi = cs.index("finished_at") if t == "attempt" else -1
        buf: list[str] = []
        size = n = 0
        for row in cur:
            row = list(row)
            if li >= 0 and row[fi] is None and row[li] is not None and row[li] < hold:
                row[li] = hold                 # 交接期：别处正跑着的单，D1 里别当失联收回
            v = "(" + ", ".join(lit(x) for x in row) + ")"
            if buf and size + len(v.encode()) > MAX_STMT:
                out.append(head + ",\n".join(buf) + tail)
                buf, size = [], 0
            buf.append(v)
            size += len(v.encode()) + 2
            n += 1
        if buf:
            out.append(head + ",\n".join(buf) + tail)
        cur.close()
        stats[t] = n
    if since is None:
        for k, v in c.execute("SELECT key, value FROM jobs.meta WHERE key <> 'schema_version'").fetchall():
            out.append(f"INSERT INTO meta (key, value) VALUES ({lit(k)}, {lit(v)}) ON CONFLICT (key) DO UPDATE SET"
                       " value = excluded.value")
    mark = now - dt.timedelta(minutes=2)       # 回看 2 分钟：快照开始前后的提交不漏
    out.append(f"INSERT INTO meta (key, value) VALUES ('pg_sync_at', {lit(mark)})"
               " ON CONFLICT (key) DO UPDATE SET value = excluded.value")
    return out, stats, mark


def _d1(d1_url):
    from guji_manager.jobs import d1
    return d1.connect({"driver": "d1-worker", "url": d1_url or "https://data.open-guji.com"})


def _since(j, full: bool):
    if full:
        return None
    r = j.q("SELECT value FROM meta WHERE key = 'pg_sync_at'")
    if not r:
        return None
    return dt.datetime.fromisoformat(r[0]["value"].replace("Z", "+00:00"))


def dump(out: str, d1_url=None, full: bool = True) -> None:
    since = None if full else _since(_d1(d1_url), False)
    c = pg(snapshot=True)
    stmts, stats, _ = statements(c, since)
    c.close()
    with open(out, "w", encoding="utf-8") as f:
        for s in stmts:
            f.write(s + ";\n")
    print(f"{stats} → {out}", file=sys.stderr)


MAX_REQ = 4_000_000        # Worker 任务库接口请求体上限 5 MB


def sync(d1_url=None, full: bool = False) -> None:
    j = _d1(d1_url)
    since = _since(j, full)
    c = pg(snapshot=True)
    stmts, stats, mark = statements(c, since)
    c.close()
    body = stmts[1:]                           # Worker 每批一个事务；外键按表先后，不用 defer
    meta = body.pop()                          # 水位最后写：中途失败下次从旧水位重来（upsert 幂等）
    sent = 0
    chunk: list[str] = []
    size = 0
    for s in body:
        if chunk and size + len(s.encode()) > MAX_REQ:
            j.batch([(x, []) for x in chunk])
            sent += len(chunk)
            chunk, size = [], 0
        chunk.append(s)
        size += len(s.encode()) + 64
    if chunk:
        j.batch([(x, []) for x in chunk])
        sent += len(chunk)
    j.batch([(meta, [])])
    print(f"{'全量' if since is None else '自 ' + since.isoformat()} → 水位 {mark.isoformat()}："
          + "、".join(f"{t} {n}" for t, n in stats.items()) + f"（{sent} 条语句）", file=sys.stderr)


SEQ_TABLES = ["job", "attempt", "event", "result"]
SEQ_MARGIN = {"job": 10_000, "attempt": 10_000, "event": 200_000, "result": 10_000}   # 交接期 Postgres 还会长


def seed_seq(d1_url: str | None) -> None:
    """D1 的 AUTOINCREMENT 号预留到 Postgres 最大号＋SEQ_MARGIN：切换后 D1 新写的行从这之后编，交接期 Postgres 新增的行
    同步过来用原号，不撞。"""
    j = _d1(d1_url)
    c = pg()
    stmts = []
    for t in SEQ_TABLES:
        n = (c.execute(f"SELECT coalesce(max(id), 0) FROM jobs.{t}").fetchone()[0] or 0) + SEQ_MARGIN[t]
        stmts += [("DELETE FROM sqlite_sequence WHERE name = ?", [t]),
                  ("INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)", [t, n])]
        print(f"{t}: 从 {n + 1} 起编", file=sys.stderr)
    j.batch(stmts)
    c.close()
    j.close()


def check(d1_url: str | None) -> int:
    j = _d1(d1_url)
    c = pg()
    bad = 0
    for t in TABLES:
        key = "count(*)" + (", max(id)" if t not in ORDER else "")
        a = c.execute(f"SELECT {key} FROM jobs.{t}").fetchone()
        b = j.execute(f"SELECT {key} FROM {t}").fetchone()
        ok = b[0] >= a[0] and (len(a) == 1 or (b[1] or 0) >= (a[1] or 0))   # 切换后 D1 只会更多
        bad += not ok
        print(f"{'✓' if ok else '✗'} {t}: Postgres {tuple(a)}  D1 {tuple(b)}")
    c.close()
    j.close()
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--d1-url")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump")
    d.add_argument("--out", required=True)
    d.add_argument("--incremental", action="store_true", help="只导上次同步以来变的（缺省全量）")
    y = sub.add_parser("sync")
    y.add_argument("--full", action="store_true")
    sub.add_parser("check")
    sub.add_parser("seed-seq")
    a = ap.parse_args()
    if a.cmd == "dump":
        dump(a.out, a.d1_url, full=not a.incremental)
    elif a.cmd == "sync":
        sync(a.d1_url, a.full)
    elif a.cmd == "seed-seq":
        seed_seq(a.d1_url)
    else:
        return check(a.d1_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
