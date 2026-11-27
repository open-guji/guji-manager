"""`guji pending-settle`：待审条目对账——格已落定就把还开着的条目标 resolved，记裁定事件 id（清理计划 v2 步骤 2.2）。

    guji pending-settle -w <工作区> [--pull] [--apply] [--sync] [--json] [--rows <文件.tsv>]
    guji pending-settle --roots <目录> [--pull] [--apply] [--sync]      # 目录下各个中心库工作区都对一遍（执行方定时用）

缺省只算不写（列出要标的条目）。``--pull`` 先 ``guji db pull --only feedback/lists/pending/`` 拿到最新条目文件；
``--apply`` 才追加 resolved 版本到数据目录的 ``*.items.jsonl``；``--sync`` 再 ``db sync --only`` 推回中心库。
口径与细节见 ``review/settle_sync.py``：按 `(书, 册, u)` 配、复审格要「裁定晚于复审开出」才关、落定口径只认 `feedback/levels.py`。
执行方定时跑：``GUJI_PENDING_SETTLE_S``（秒；缺省 0＝不跑，只在一台机器上开）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PEND = "feedback/lists/pending/"


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("pending-settle", help="待审条目对账：格已落定的开着条目标 resolved（按 书/册/u 配，复审格晚于复审开出才关）")
    p.add_argument("-w", "--workspace", default=None, help="工作区（含 workspace.yaml）；不给读 GUJI_WORKSPACE")
    p.add_argument("--roots", default=None, help="目录：其下各层一级子目录里的中心库工作区都对一遍（和 -w 二选一）")
    p.add_argument("--pull", action="store_true", help="先 db pull --only 条目目录")
    p.add_argument("--apply", action="store_true", help="真写（缺省只算不写）")
    p.add_argument("--sync", action="store_true", help="写完 db sync --only 条目目录（要 --apply）")
    p.add_argument("--json", action="store_true")
    p.add_argument("--rows", default=None, help="把明细写成 TSV")
    p.add_argument("--by", default=None, help="记在条目上的操作者（缺省 settle-sync）")


def _one(ws_dir: Path, a, conn) -> dict:
    from .datastore.workcopy import data_dir
    from .land import db_only
    from .review import settle_sync as S
    from ._cv import central_marker
    ws = str((central_marker(ws_dir) or {}).get("ws") or "")
    if not ws:
        raise SystemExit(f"✗ {ws_dir} 不是中心库工作区（没有中心库标记）")
    if a.pull and db_only(ws_dir, "pull", [PEND]):
        raise SystemExit(f"✗ {ws_dir}：db pull --only {PEND} 失败")
    res = S.sync_workspace(conn, ws, data_dir(ws_dir), apply=a.apply, by=a.by or S.BY)
    res["ws"] = ws
    if a.apply and a.sync and res["resolved"] and db_only(ws_dir, "sync", [PEND]):
        raise SystemExit(f"✗ {ws_dir}：db sync --only {PEND} 失败（条目已写到本机，重跑 --sync 即可）")
    return res


def cmd_pending_settle(a) -> int:
    from .datastore.connect import connect
    from . import dbconfig
    if a.sync and not a.apply:
        sys.exit("✗ --sync 要和 --apply 一起")
    dbconfig.apply_env()
    if a.roots:
        from .uid.checku_report import find_workspaces
        dirs = list(sorted(find_workspaces([a.roots]).items()))
    else:
        w = a.workspace or os.environ.get("GUJI_WORKSPACE")
        if not w:
            sys.exit("✗ 要 -w <工作区> 或 --roots <目录>")
        dirs = [("", Path(w).expanduser().resolve())]
    conn = connect()
    allrows, out = [], []
    for _, d in dirs:
        r = _one(d, a, conn)
        out.append(r)
        allrows += r["rows"]
        if not a.json:
            print(f"{r['ws']}：条目文件 {r['files']}，开着 {r['open']}，"
                  f"{'已标' if a.apply else '待标'} resolved {r['resolved']}（其中复审格 {r['recheck_resolved']}），"
                  f"复审格有裁定、但裁定不晚于复审开出，保持开着 {r['recheck_kept']}")
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    if a.rows:
        cols = ["book", "vol", "cell", "u", "item", "event", "recheck"]
        Path(a.rows).write_text("\t".join(cols) + "\n" + "".join(
            "\t".join(str(r[c]) for c in cols) + "\n" for r in allrows), encoding="utf-8")
    if not a.apply and not a.json and allrows:
        print("（只算不写；--apply 才标）")
    return 0


COMMANDS = {"pending-settle": (add_parser, cmd_pending_settle)}
