"""并进 `guji` 的子命令（入口点组 `guji.commands`，见 open-guji-cv `cli_v2.load_plugin_commands`）。

每批搬迁当天 manager 新增、cv 删除同时合（cv `doc/design/拆分-pipeline与manager.md`，2026-11-02 计划）；
cv 删除时在 `cli_v2.MOVED_TO_MANAGER` 登记，没装本包的机器上 `guji <命令>` 会给出装法。
"""

from __future__ import annotations

import argparse

from .cli_cellvotes import add_parser as _add_cellvotes
from .cli_cellvotes import cmd_cellvotes
from .cli_freeze import add_parser as _add_freeze
from .cli_freeze import cmd_freeze
from .cli_opinions import add_parser as _add_opinions
from .cli_opinions import cmd_opinions
from .cli_source import add_parser as _add_source
from .cli_source import cmd_source

COMMANDS: dict = {
    "opinions": (_add_opinions, cmd_opinions),       # P2 第一批，原 cv cli_opinions + opinions/
    "source": (_add_source, cmd_source),             # P2 第二批，原 cv cli_source（原图：R2 源件、页表）
    "cellvotes": (_add_cellvotes, cmd_cellvotes),    # P2 第二批，原 cv cli_cellvotes（网站格级投票落事件）
    "freeze": (_add_freeze, cmd_freeze),             # P2 第二批，原 cv cli_freeze（冻结登记）
}


def run(argv: list[str]) -> None:
    """不经 cv 的 `guji`，直接跑本包的子命令（测试与 `guji-manager <命令>` 用）。"""
    ap = argparse.ArgumentParser(prog="guji")
    sub = ap.add_subparsers(dest="command")
    seen = set()
    for add_parser, _ in COMMANDS.values():
        if add_parser not in seen:
            add_parser(sub)
            seen.add(add_parser)
    args = ap.parse_args(argv)
    COMMANDS[args.command][1](args)
