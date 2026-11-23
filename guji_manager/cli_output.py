"""第五步「排版输出」的命令：`guji output export …`、`guji output collation-report …`（cv 原 Step9，2026-11-23 搬来）。

- `export md <册>`：逐列文本 → `reports/<册>/<册>.md`（`output/markdown.py`）。
- `export format <册>`：lines.md／pages.json／norm.json（`output/guji_format_export.py`；章号、meta、拆页表按约定自动填）。
- `export wikisource <书> -w <工作区>`：维基文库 wikitext（`output/wikisource_export.py`，书名用它自己的表，如 bxgb）。
- `export reflow <md>`：分行 md 重排成段落（`output/reflow.py`）。
- `collation-report`：整册与整理本对勘的 HTML 报告（`output/collation_report.py`）。

全部只读产物。原来 cv 起子进程跑 `scripts/` 下的脚本，现在同进程调本包模块，口径不变。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _export_pages(book: str, pipeline: str, spec: str) -> tuple[str, list[int]]:
    """有 Step7（seed_admit）产物的页：目录、空白页等没跑到的跳过，免得整条命令因缺产物退出。"""
    from ._cv import _engine, products_root
    eng = _engine(book, pipeline, quiet=True)
    pages = eng.book.resolve_pages(spec)
    have = {int(f.stem[1:]) for f in (products_root() / eng.book.id / "seed_admit").glob("p*.json")}
    skipped = [p for p in pages if p not in have]
    if skipped:
        print(f"（跳过 {len(skipped)} 页：没有 seed_admit 产物 {skipped[:10]}{'…' if len(skipped) > 10 else ''}）",
              file=sys.stderr)
    pages = [p for p in pages if p in have]
    if not pages:
        print("✗ 没有可导出的页（seed_admit 产物为空）", file=sys.stderr)
        sys.exit(1)
    return eng.book.id, pages


def cmd_export(args) -> None:
    from ._cv import reports_root
    if args.action in ("reflow", "wikisource"):     # 自带参数：reflow 输入是 md 文件，wikisource 用自己的书名表与页范围
        if args.action == "reflow":
            from .output.reflow import main
        else:
            from .output.wikisource_export import main
        argv = [args.book, *args.rest]
        if args.out:
            argv += ["--out", args.out]
        if args.action == "wikisource" and args.pages != "all":
            argv += ["--pages", args.pages]
        sys.exit(main(argv) or 0)
    book, pages = _export_pages(args.book, args.pipeline, args.pages)
    out_dir = Path(args.out) if args.out else reports_root() / book
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.action == "md":
        from .output.markdown import main
        argv = [book, *map(str, pages), "--out", str(out_dir / f"{book}.md"), *args.rest]
    else:
        from ._cv import chapter_of, cv_repo, products_root
        from .output.guji_format_export import main
        chapter = chapter_of(book, args.chapter)
        if not chapter:
            print(f"✗ 册号 {book} 推不出章号：册 yaml 写上 volume，或给 --chapter NNN", file=sys.stderr)
            sys.exit(2)
        samples = cv_repo() / "doc" / "formats" / "samples"
        meta = Path(args.meta) if args.meta else samples / "guji_format_v0.1" / f"meta_{book}.json"
        if not meta.exists():
            print(f"✗ 没有 meta：{meta}。照同目录 meta_vol03.json 改 volume 两项另存，或用 --meta 指定", file=sys.stderr)
            sys.exit(2)
        split = Path(args.split_table) if args.split_table else samples / "guji_page_v0.2" / "split_table_siku.json"
        argv = ["--products", str(products_root()), "--book", book, "--chapter", chapter, "--meta", str(meta),
                "--out", str(out_dir), "--pages", ",".join(map(str, pages)), *args.rest]
        if split.exists():
            argv += ["--split-table", str(split)]
    print("→ " + " ".join(argv), file=sys.stderr)
    sys.exit(main(argv) or 0)


def cmd_collation_report(args) -> None:
    from .output.collation_report import main
    sys.exit(main(list(args.rest)) or 0)


def add_parser(sub: argparse._SubParsersAction) -> None:
    from ._cv import DEFAULT_PIPELINE
    p = sub.add_parser("export", help="排版输出（第五步 output）：md 逐列文本／format lines.md、pages.json、norm.json／"
                                      "wikisource 维基文库文本／reflow 分行 md 重排成段（只读产物）")
    p.add_argument("action", choices=["md", "format", "wikisource", "reflow"])
    p.add_argument("book", help="册 id（reflow：输入 md 文件；wikisource：书名，如 bxgb）")
    p.add_argument("--pipeline", default=DEFAULT_PIPELINE)
    p.add_argument("--pages", default="all")
    p.add_argument("--out", default=None, help="输出目录；缺省 reports/<册>/")
    p.add_argument("--chapter", default=None, help="format：章号 NNN，缺省按册号推")
    p.add_argument("--meta", default=None, help="format：缺省 cv doc/formats/samples/guji_format_v0.1/meta_<册>.json")
    p.add_argument("--split-table", default=None, help="format：合扫拆页裁剪表，缺省四庫的 split_table_siku.json")
    p.add_argument("rest", nargs=argparse.REMAINDER, help="其余参数原样交给导出模块（写在册 id 之后）")


def add_collation_parser(sub: argparse._SubParsersAction) -> None:
    # 与 export 分开登记：cv 还有同名 export 时插件加载会跳过整个 add_parser，别把这条连带丢了
    p = sub.add_parser("collation-report", help="整册与整理本对勘的 HTML 报告（只读产物；参数见 -h）",
                       add_help=False, prefix_chars="\x01")
    p.add_argument("rest", nargs="*")


COMMANDS = {
    "export": (add_parser, cmd_export),
    "collation-report": (add_collation_parser, cmd_collation_report),
}
