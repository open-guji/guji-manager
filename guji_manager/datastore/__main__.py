"""``python -m guji_manager.datastore``：中心库导入 / 核对 / R2 上传计划。

连库（2026-11-18 起中心库是 Cloudflare D1）：经 guji-data Worker（``GUJI_DATA_URL``、``GUJI_DATA_TOKEN``），
``--dsn`` 给分支名（缺省 main）；``GUJI_DATA_SQLITE=<文件>`` 改连本机 SQLite（核对用）。

    python -m guji_manager.datastore import  --repo <guji-workspace> --commit <sha>
    python -m guji_manager.datastore verify  --repo <guji-workspace> --commit <sha>
    python -m guji_manager.datastore r2-plan --repo <guji-workspace> --commit <sha> --manifest plan.jsonl
    python -m guji_manager.datastore backup                       # 每周备份（GUJI-611；D1 另有 30 天 Time Travel）
    python -m guji_manager.datastore restore-check --endpoint <exp/…>   # 恢复演练（恢复到实验分支）
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _connect(args):
    """2026-11-18 中心库迁 D1：``--dsn`` 改为分支名（缺省 main），经 Worker 连；``GUJI_DATA_SQLITE`` 可改连本机 SQLite。"""
    from .connect import connect
    if args.dsn and ("://" in args.dsn or "=" in args.dsn):
        raise SystemExit("中心库已迁到 D1，不再收 Postgres 连接串；--dsn 给分支名（如 exp/GUJI-9-x）或不给（main）")
    return connect(branch=args.dsn or None)


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m guji_manager.datastore",
                                 description="中心库：导入 guji-workspace、核对、R2 上传")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, db=True):
        p.add_argument("--repo", required=True, help="guji-workspace 的本地克隆")
        p.add_argument("--commit", default="HEAD", help="钉住的提交（默认 HEAD）")
        if db:
            p.add_argument("--dsn", help="分支名（缺省 main）")

    p = sub.add_parser("schema", help="只建表（可重复执行）")
    p.add_argument("--dsn")
    p = sub.add_parser("import", help="把某个提交灌进库（幂等）")
    common(p)
    p.add_argument("--ws", action="append", help="只导这个工作区（id 或目录名，可重复）")
    p.add_argument("--allow-delete", action="store_true",
                   help="允许删只追加台账（events/consumed/anchors）里的行")
    p.add_argument("--actor", default=os.environ.get("USER"), help="记进 imports.actor")
    p.add_argument("--dry-run", action="store_true", help="只算差别，不写库")
    p = sub.add_parser("verify", help="库与提交逐行、逐文件核对")
    common(p)
    p.add_argument("--quiet", action="store_true", help="只打印汇总")
    p = sub.add_parser("r2-plan", help="列出要上 R2 的图（默认不上传）")
    common(p, db=False)
    p.add_argument("--dsn", help="给了就和库里的 sha 对一遍")
    p.add_argument("--manifest", help="把对象清单写到这个 jsonl")
    p.add_argument("--execute", action="store_true", help="真上传（要 R2_* 环境变量）")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--via", choices=["s3", "worker"], default="s3",
                   help="s3：R2 S3 接口（要 R2_*）；worker：经 guji-data Worker 签名上传（要 GUJI_DATA_TOKEN）")
    p.add_argument("--bucket", choices=["exp", "main"], default="exp", help="--via worker 时传哪个桶")
    p.add_argument("--limit", type=int, help="--via worker 时只传前 N 个（按 sha 排序，分批用）")

    p = sub.add_parser("backup", help="全部表导出存进 R2 backup/<日期>/（GUJI-611），清掉过保留期的")
    p.add_argument("--keep-days", type=int, default=30)
    p.add_argument("--date", default=None, help="存成哪天（缺省今天，UTC）")
    p = sub.add_parser("restore-check", help="把某天的备份恢复到 main 以外的端点并逐表核对")
    p.add_argument("--endpoint", required=True, help="恢复到哪个分支（实验分支名，D1 上是独立库），不许是 main")
    p.add_argument("--date", default=None, help="哪天的备份（缺省最新一份完整的）")

    args = ap.parse_args(argv)

    if args.cmd in ("backup", "restore-check"):
        from datetime import datetime, timezone
        from . import backup as B
        from .._cv import WorkerSource
        from .._cv import connect, main_endpoint
        src = WorkerSource()
        if args.cmd == "backup":
            day = args.date or datetime.now(timezone.utc).date().isoformat()
            with connect() as conn:
                files, man = B.dump(conn)
            out = B.upload(src, day, files, man)
            out.update(rev=man["rev"], tables=len(man["tables"]),
                       rows=sum(t["rows"] for t in man["tables"].values()),
                       pruned=B.prune(src, args.keep_days))
            _print(out)
            return 0
        if args.endpoint == main_endpoint():
            raise SystemExit("拒绝：--endpoint 是正式库 main 的端点，恢复演练只许打到别的分支（如 ci）")
        dates = B.complete_dates(src)
        day = args.date or (dates[-1] if dates else None)
        if day not in dates:
            raise SystemExit(f"没有完整的备份 {day}（有：{dates[-5:]}）")
        files, man = B.fetch(src, day)
        with connect(endpoint=args.endpoint) as conn:
            B.restore(conn, files, man)
            res = B.check(conn, man)
        res.update(date=day, rev=man["rev"], endpoint=args.endpoint)
        if not res["ok"]:
            _print(res)
            return 1
        res["tables"] = {t: v["rows"] for t, v in res["tables"].items()}
        _print(res)
        return 0

    if args.cmd == "schema":
        from .._cv import apply_schema
        with _connect(args) as conn:
            apply_schema(conn)
        print("ok")
        return 0

    if args.cmd == "import":
        from .._cv import DeleteRefused, import_commit
        with _connect(args) as conn:
            try:
                rep = import_commit(conn, args.repo, args.commit,
                                    only_ws=set(args.ws) if args.ws else None,
                                    allow_delete=args.allow_delete, actor=args.actor,
                                    dry_run=args.dry_run)
            except DeleteRefused as e:
                print(str(e), file=sys.stderr)
                return 2
        _print(rep.as_dict())
        return 0

    if args.cmd == "verify":
        from .verify import verify_commit
        with _connect(args) as conn:
            rep = verify_commit(conn, args.repo, args.commit)
        if args.quiet:
            for w in rep["workspaces"].values():
                w["mismatches"] = w["mismatches"][:20] + (
                    [f"…共 {len(w['mismatches'])} 条"] if len(w["mismatches"]) > 20 else [])
        _print(rep)
        return 0 if rep["ok"] else 1

    if args.cmd == "r2-plan":
        from .._cv import datastore_r2 as r2
        commit, objs, stats = r2.plan_commit(args.repo, args.commit)
        out = {"commit": commit, "stats": stats, "dry_run": not args.execute}
        if args.manifest:
            r2.write_manifest(objs, args.manifest)
            out["manifest"] = args.manifest
        if args.dsn or os.environ.get("GUJI_DATA_TOKEN"):
            with _connect(args) as conn:
                out["db_check"] = r2.check_against_db(conn, objs)
        if args.execute:
            if args.via == "worker":
                out["upload"] = r2.upload_via_worker(args.repo, objs, bucket=args.bucket,
                                                     workers=args.workers, limit=args.limit)
            else:
                out["upload"] = r2.upload(args.repo, objs, workers=args.workers)
        _print(out)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
