"""`guji-manager` 命令行。M4 前只有 `check`；`guji` 命令的接管见设计第七节 M4/M5。"""

from __future__ import annotations

import argparse
import json

from . import __version__
from .pipeline import IncompatiblePipeline, check_compatible, pipeline_version


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="guji-manager")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("version", help="manager 版本")
    c = sub.add_parser("check", help="核对装着的 pipeline 与本 manager 兼容")
    c.add_argument("--json", action="store_true")
    sub.add_parser("pending-stats", help="全部待审格分类统计（查中心库）；参数见 guji_manager.pending_stats", add_help=False)
    sub.add_parser("central-gc", help="中心库定期清理（产物包按保留规则清）；见 guji_manager.central_gc", add_help=False)
    sub.add_parser("triage", help="参校字快审分流（skip/pass/withdraw/review）；见 guji_manager.review_triage", add_help=False)
    sub.add_parser("review-pages", help="人审页模板库（预选、一字一卡、版本、台账）；见 guji_manager.review_pages", add_help=False)
    sub.add_parser("iterate", help="降人审迭代的轮报告、金标、抽检台账、杠杆排序、冻结日历；见 guji_manager.iterate", add_help=False)
    a, rest = ap.parse_known_args(argv)
    if a.cmd == "review-pages":
        from .review_pages.__main__ import main as rp_main
        return rp_main(rest)
    if a.cmd == "iterate":
        from .iterate.__main__ import main as iterate_main
        return iterate_main(rest)
    if a.cmd == "triage":
        from .review_triage.__main__ import main as triage_main
        return triage_main(rest)
    if a.cmd == "central-gc":
        from .central_gc import main as gc_main
        return gc_main(rest)
    if a.cmd == "pending-stats":
        from .pending_stats import main as stats_main
        return stats_main(rest)
    if rest:
        ap.error(f"不认识的参数：{' '.join(rest)}")
    if a.cmd == "check":
        info = pipeline_version()
        try:
            check_compatible(info)
            ok, why = True, ""
        except IncompatiblePipeline as e:
            ok, why = False, str(e)
        if a.json:
            print(json.dumps({"manager": __version__, "pipeline": info, "ok": ok, "why": why}, ensure_ascii=False))
        else:
            print(("✓ 兼容" if ok else f"✗ {why}") + f"（pipeline {info.get('cv_version')}，契约 v{info.get('contract_version')}）")
        return 0 if ok else 1
    print(f"guji-manager {__version__}")
    return 0
