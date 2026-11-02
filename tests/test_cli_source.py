"""`guji source` 命令层（拆分 P2 第二批从 open-guji-cv 搬来）。"""

from __future__ import annotations

import argparse


def test_source_actions_survive_commands_table():
    """`guji source pull` 等动作还在（cv 拆分 P1a 曾让插件表 COMMANDS 盖掉同名的动作表，choices 只剩 source）。"""
    from guji_manager import cli_source
    sub = argparse.ArgumentParser().add_subparsers(dest="command")
    cli_source.add_parser(sub)
    acts = next(a for a in sub.choices["source"]._actions if a.dest == "action").choices
    assert {"pull", "show", "list", "check"} <= set(acts)
