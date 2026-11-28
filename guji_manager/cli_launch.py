"""`guji launch prepare <册> --label <main 包> -w <工作区> …`：新书首发的 prepare 段（无外部写，可交任务库 command 单并行）。

= 原 tools/开书/出v01.py：判停 → 交接单 → 第五步产物 → 导出 → book-text 本地加章 → local_check。
其余参数原样交给 v01.main（--book-text --title --juan --gate-only --force --promote --chapter --no-fetch）。
设计：ai-team domain/GM/GM4/新书首发一条命令-设计-2026-11-28.md。ship 段（推 book-text、land、web 登记）后续加。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("launch", help="新书首发：prepare 段（uid sync 之外的出 v0.1、book-text 本地加章）")
    p.add_argument("action", choices=["prepare"])
    p.add_argument("book", help="册名")
    p.add_argument("rest", nargs=argparse.REMAINDER, help="其余参数交 出v0.1（-w、--label、--book-text、--title …）")


def cmd_launch(a) -> int:
    from .launch import v01
    rest = list(a.rest)
    ws = None
    for i, x in enumerate(rest):
        if x in ("-w", "--workspace") and i + 1 < len(rest):
            ws = rest[i + 1]
    ws = ws or os.environ.get("GUJI_WORKSPACE")
    if not ws:
        sys.exit("✗ 要 -w <工作区> 或 GUJI_WORKSPACE")
    if "-w" not in rest and "--workspace" not in rest:
        rest += ["-w", ws]
    landed = Path(ws) / "reports" / a.book / "_land" / "landed.json"
    if landed.exists():
        sys.exit(f"✗ {a.book} 已上过站（{landed}）：不是首发，换包走 guji land")
    os.environ.setdefault("GUJI_PRODUCTS_DIR", str(Path(ws) / "_launch_products"))
    return v01.main(["--book", a.book, *rest])


COMMANDS = {"launch": (add_parser, cmd_launch)}
