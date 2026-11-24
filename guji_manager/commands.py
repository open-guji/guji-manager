"""并进 `guji` 的子命令（入口点组 `guji.commands`，见 open-guji-cv `cli_v2.load_plugin_commands`）。

每批搬迁当天 manager 新增、cv 删除同时合（cv `doc/design/拆分-pipeline与manager.md`，2026-11-02 计划）；
cv 删除时在 `cli_v2.MOVED_TO_MANAGER` 登记，没装本包的机器上 `guji <命令>` 会给出装法。
"""

from __future__ import annotations

import argparse

from . import cli_close, cli_db, cli_eval, cli_exp, cli_feedback, cli_glyph, cli_glyph_db, cli_model, cli_ops
from . import cli_closeout, cli_code, cli_output, steps, cli_pending, cli_perf, cli_products, cli_runs, cli_seg, collect, ctx_ruling, human_conflicts, round_check, ruling_hits, swap
from .cli_cellvotes import add_parser as _add_cellvotes
from .jobs import cli as _jobs_cli
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
    # P2 第三批（2026-11-04），原 cv 同名模块；一个模块几条命令共用一个 add_parser
    **cli_exp.COMMANDS,        # exp
    **cli_ops.COMMANDS,        # snap、archive
    **cli_feedback.COMMANDS,   # events、gold
    **cli_eval.COMMANDS,       # eval、check、groups、progress、collate
    # P2 第四批（2026-11-04），原 cv 同名模块
    **cli_close.COMMANDS,      # close-check、exit-check、audit、char-diff
    **cli_db.COMMANDS,         # db
    **cli_glyph.COMMANDS,      # recheck、glyphlib、pua-table、rekey-cells、promote、corpus
    **cli_glyph_db.COMMANDS,   # glyph-db
    **cli_model.COMMANDS,      # model、font
    **cli_code.COMMANDS,       # code（书级代码，2026-11-09，cv v0.7.0）
    # P3 jobs（2026-11-04），原 cv jobs/cli.py
    **_jobs_cli.COMMANDS,      # job
    **cli_products.COMMANDS,   # products（拆分 P4）
    **cli_perf.COMMANDS,       # perf（拆分 P4）
    **cli_runs.COMMANDS,       # rerun、pagekinds、cache、product（拆分 P4）
    **cli_closeout.COMMANDS,   # closeout（标 main 后收尾，A32 11-09）
    **swap.COMMANDS,           # swap（换单 driver，A32 11-05）
    **cli_pending.COMMANDS,    # pending（待审条目，一格一条，A31 11-10）
    **cli_seg.COMMANDS,        # seg pin（整列写定 manual-cells，A22 11-12）
    **collect.COMMANDS,        # collect（收单快路：人裁直接落 book-text，不重放，A31 11-19）
    **ctx_ruling.COMMANDS,     # ctx-ruling（按格号＋字写终审文意裁定，原 ZM 会话脚本，A31 11-21）
    **human_conflicts.COMMANDS,  # human-conflicts（推库前跨批次人裁冲突，SJ 11-21）
    **ruling_hits.COMMANDS,    # rulings-hits（AI 文意裁定命中核对，A31 11-20）
    **round_check.COMMANDS,    # round-check（收轮检查：seg check×2→gate→premain→待审归层，A31 11-20）
    # 按步骤分组（start／auto／text／feedback／output）与并进 guji 的模块入口（2026-11-22，见 steps.py）
    **cli_output.COMMANDS,     # export、collation-report（第五步 排版输出，cv 原 Step9 搬来，11-23）
    **steps.COMMANDS,
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
