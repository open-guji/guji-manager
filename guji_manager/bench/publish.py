"""`guji bench run|ab|guard --publish`：一次结果写进中心库 `bench_runs` 表（Sheldon 11-28 定：建表、只有 --publish 才写）。

`--baseline` 标基线：同一 bench＋书只留最新标的那一条（旧的自动取消）。一次 run 一行，主键 `run_id`（`<bench>/<书>/<时间目录名>-<result.json 短 sha>`），`ran_at` 是 UTC，重复发布同一次不重写。存 `result.json` 原样（`result` 列）
与常用列，不存逐样本（items 留在本机结果目录，翻转清单要它就带上结果目录）。不挂 workspaces 外键、不进 files 同步、
不按分支（只写 main）；建表语句随本模块，首次发布时 `CREATE TABLE IF NOT EXISTS`。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

TABLE = "bench_runs"
DDL = (
    f"""CREATE TABLE IF NOT EXISTS {TABLE} (
  "run_id" TEXT PRIMARY KEY,
  "bench" TEXT NOT NULL,
  "book" TEXT NOT NULL,
  "vols" TEXT,
  "status" TEXT NOT NULL,
  "primary_name" TEXT,
  "primary_value" REAL,
  "n" INTEGER,
  "cv" TEXT,
  "cv_git" TEXT,
  "manager" TEXT,
  "dataset" TEXT,
  "central" TEXT,
  "params" TEXT,
  "seconds" REAL,
  "baseline" INTEGER NOT NULL DEFAULT 0,
  "note" TEXT,
  "by" TEXT,
  "ran_at" TEXT NOT NULL,
  "published_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "result" TEXT NOT NULL
)""",
    f'CREATE INDEX IF NOT EXISTS {TABLE}_bench_book ON {TABLE} ("bench", "book", "ran_at")',
)
COLS = ("run_id", "bench", "book", "vols", "status", "primary_name", "primary_value", "n", "cv", "cv_git", "manager",
        "dataset", "central", "params", "seconds", "baseline", "note", "by", "ran_at", "result")


def _ran_at_utc(out: Path) -> str:
    """跑的时间（UTC ISO）：结果目录名是本机时区、还可能带 -A/-B，跨机器排序不准；取 result.json 落盘时刻换成 UTC。"""
    import datetime as dt
    t = (out / "result.json").stat().st_mtime
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def row_of(out: Path, *, baseline: bool = False, note: str = "", by: str | None = None) -> dict:
    import hashlib
    out = Path(out)
    raw = (out / "result.json").read_bytes()
    d = json.loads(raw.decode("utf-8"))
    e = d.get("env") or {}
    pv = d["primary"]["value"]
    # run_id 带结果内容的短 sha：两台机器同一秒跑同一 bench 不撞号；同一次重发 sha 不变，仍是幂等（GM2 审 #1269）
    rid = f"{d['bench']}/{d['book']}/{out.name}-{hashlib.sha256(raw).hexdigest()[:8]}"
    return {"run_id": rid, "bench": d["bench"], "book": d["book"],
            "vols": ",".join(d.get("vols") or []), "status": d["status"], "primary_name": d["primary"]["name"],
            "primary_value": float(pv) if isinstance(pv, (int, float)) else None, "n": d.get("n"),
            "cv": e.get("cv"), "cv_git": e.get("cv_git"), "manager": e.get("manager"), "dataset": e.get("dataset"),
            "central": e.get("central"), "params": e.get("params"), "seconds": d.get("seconds"),
            "baseline": 1 if baseline else 0, "note": note or None,
            "by": by or os.environ.get("GUJI_ACTOR") or None, "ran_at": _ran_at_utc(out),
            "result": json.dumps(d, ensure_ascii=False, sort_keys=True, default=str)}


def publish(out: Path, conn=None, **kw) -> str:
    """写一行；返回 run_id。同一 run_id 已有就不动（`ON CONFLICT DO NOTHING`）。"""
    r = row_of(out, **kw)
    if r["status"] == "failed":
        raise ValueError("跑崩的结果不发布")
    if conn is None:
        from ..datastore import d1conn
        conn = d1conn.connect()
    for s in DDL:
        conn.execute(s)
    cols = ", ".join(f'"{c}"' for c in COLS)
    ph = ", ".join(["%s"] * len(COLS))
    conn.execute(f'INSERT INTO {TABLE} ({cols}) VALUES ({ph}) ON CONFLICT ("run_id") DO NOTHING',
                 [r[c] for c in COLS])
    if r["baseline"]:                                      # 同一 bench＋书只留最新标的一条基线
        conn.execute(f'UPDATE {TABLE} SET baseline = 1 WHERE run_id = %s', [r["run_id"]])
        conn.execute(f'UPDATE {TABLE} SET baseline = 0 WHERE bench = %s AND book = %s AND run_id <> %s AND baseline = 1',
                     [r["bench"], r["book"], r["run_id"]])
    conn.commit()
    return r["run_id"]


def history(bench: str, book: str, conn=None, limit: int = 20, all_status: bool = False) -> list[dict]:
    """历次结果，新的在前。缺省只看有结论的（ok／regressed）；`all_status` 连 skipped／no_gold 一起。"""
    if conn is None:
        from ..datastore import d1conn
        conn = d1conn.connect()
    cur = conn.cursor()
    only = "" if all_status else " AND status IN ('ok', 'regressed')"
    cur.execute(f'SELECT run_id, status, primary_name, primary_value, n, cv, baseline, "by", ran_at FROM {TABLE} '
                f'WHERE bench = %s AND book = %s{only} ORDER BY ran_at DESC LIMIT %s', (bench, book, limit))
    keys = ("run_id", "status", "primary_name", "primary_value", "n", "cv", "baseline", "by", "ran_at")
    return [dict(zip(keys, row)) for row in cur.fetchall()]
