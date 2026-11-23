"""任务库搬家：美国机 Postgres（jobs schema）→ D1 guji-jobs（2026-11-22 用户定）。

    python scripts/jobs_pg_to_d1.py dump  --out jobs.sql   # 从 Postgres 导出成 D1 能执行的 INSERT（建表另跑 schema_d1.sql）
    npx wrangler d1 execute guji-jobs --remote --file guji_manager/jobs/schema_d1.sql
    npx wrangler d1 execute guji-jobs --remote --file jobs.sql
    python scripts/jobs_pg_to_d1.py check                  # 两边逐表核行数与最大号

dump 连 Postgres 用 databases.toml ``[jobs]`` 的 pg-tunnel 连法（JOBSDB_TOKEN＋JOBSDB_PASSWORD），check 另连 D1
（``--d1-url``，缺省 https://data.open-guji.com，令牌同 JOBSDB_TOKEN）。只读 Postgres，导出前请先让 Ops 把它设只读，
免得导出期间又有新写入。列以 schema_d1.sql 为准；Postgres 少列就报错。时间统一成 UTC 毫秒 Z 串（同 store_d1 的 NOW）。
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


def dump(out: str) -> None:
    cols = d1_columns()
    c = pg(snapshot=True)
    n_all = 0
    with open(out, "w", encoding="utf-8") as f:
        f.write("PRAGMA defer_foreign_keys = true;\n")
        for t in TABLES:
            cs = cols[t]
            order = ORDER.get(t, "id")
            cur = c.cursor(name=f"dump_{t}")       # 服务器端游标，别一次拉进内存
            cur.itersize = 2000
            cur.execute(f"SELECT {', '.join(cs)} FROM jobs.{t} ORDER BY {order}")
            head = f"INSERT INTO {t} ({', '.join(cs)}) VALUES\n"
            buf: list[str] = []
            size = 0
            n = 0
            for row in cur:
                v = "(" + ", ".join(lit(x) for x in row) + ")"
                if buf and size + len(v.encode()) > MAX_STMT:
                    f.write(head + ",\n".join(buf) + ";\n")
                    buf, size = [], 0
                buf.append(v)
                size += len(v.encode()) + 2
                n += 1
            if buf:
                f.write(head + ",\n".join(buf) + ";\n")
            cur.close()
            print(f"{t}: {n} 行", file=sys.stderr)
            n_all += n
        for k, v in c.execute("SELECT key, value FROM jobs.meta WHERE key <> 'schema_version'").fetchall():
            f.write(f"INSERT INTO meta (key, value) VALUES ({lit(k)}, {lit(v)}) ON CONFLICT (key) DO UPDATE SET"
                    " value = excluded.value;\n")
        f.write(f"INSERT INTO meta (key, value) VALUES ('migrated_from_pg', {lit(dt.datetime.now(dt.timezone.utc))})"
                " ON CONFLICT (key) DO UPDATE SET value = excluded.value;\n")
    c.close()
    print(f"共 {n_all} 行 → {out}", file=sys.stderr)


def check(d1_url: str | None) -> int:
    from guji_manager.jobs import d1
    spec = {"driver": "d1-worker", "url": d1_url or "https://data.open-guji.com"}
    j = d1.connect(spec)
    c = pg()
    bad = 0
    for t in TABLES:
        key = "count(*)" + (", max(id)" if t not in ORDER else "")
        a = c.execute(f"SELECT {key} FROM jobs.{t}").fetchone()
        b = j.execute(f"SELECT {key} FROM {t}").fetchone()
        ok = tuple(a) == tuple(b)
        bad += not ok
        print(f"{'✓' if ok else '✗'} {t}: Postgres {tuple(a)}  D1 {tuple(b)}")
    c.close()
    j.close()
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump")
    d.add_argument("--out", required=True)
    k = sub.add_parser("check")
    k.add_argument("--d1-url")
    a = ap.parse_args()
    if a.cmd == "dump":
        dump(a.out)
        return 0
    return check(a.d1_url)


if __name__ == "__main__":
    raise SystemExit(main())
