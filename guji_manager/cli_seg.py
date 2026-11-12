"""`guji seg`：切分的人定与检查（A22，2026-11-12）。

- `guji seg pin <册:页:列> [编辑…]`：整列写定（manual-cells），见 `seg_pin.py` 模块头与 cv `doc/切分覆盖.md` 第四节。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_EDITS = ("split", "merge", "move", "insert-after", "delete", "ys")


def add_parser(sub) -> None:
    import argparse

    class Collect(argparse.Action):
        def __call__(self, parser, ns, values, option_string=None):
            ns.edits = (ns.edits or []) + [(option_string.lstrip("-"), values)]

    p = sub.add_parser("seg", help="切分的人定与检查：pin（整列写定 manual-cells）")
    ss = p.add_subparsers(dest="seg_cmd", required=True)
    pin = ss.add_parser("pin", help="整列写定：从现行产物（或已有钉子）起稿、按编辑改、出草稿／叠框图／格号对照，--write 才写数据目录")
    pin.add_argument("target", help="册:页:列，如 vol01:88:4")
    pin.add_argument("-w", "--workspace", default=None, help="书的工作区（同 guji 其他命令）")
    for op in _EDITS:
        pin.add_argument(f"--{op}", action=Collect, dest="edits", metavar="ARG",
                         help={"split": "格@y：在 y 处拆", "merge": "a-b：并", "move": "格.y0|y1|x0|x1=值",
                               "insert-after": "格@y0:y1：在该格后插一格（0 插最前）", "delete": "格：删",
                               "ys": "y0,y1,…：整列按格线重排"}[op])
    pin.add_argument("--why", default="", help="写进 history 的理由（--write 时必给）")
    pin.add_argument("--out", default="", help="草稿、叠框图、对照表的输出目录（缺省 ./seg-pin/<册>-<页>-<列>）")
    pin.add_argument("--write", action="store_true", help="写进本机数据目录的 manual-cells 分片（同 id 原地替换）")
    pin.set_defaults(edits=[])


def cmd_seg(args) -> None:
    if args.seg_cmd == "pin":
        _cmd_pin(args)


def _cmd_pin(args) -> None:
    import os

    from . import seg_pin as sp
    if args.workspace:
        os.environ["GUJI_WORKSPACE"] = str(Path(args.workspace).resolve())
    try:
        book, page, col = sp.parse_target(args.target)
        try:
            d, prev = sp.draft_from_data(book, page, col)
        except sp.PinError:
            if not args.edits or args.edits[0][0] != "ys":
                raise
            raise sp.PinError("没有现行产物时 --ys 也要本列内容宽：先 products pack fetch 本册")
        before = [dict(c) for c in d.cells]
        cells = d.cells
        for e in args.edits:
            cells = sp.apply_edit(cells, e, d.content_x)
        d.cells = cells
        if args.write and not args.why.strip():
            raise sp.PinError("--write 要给 --why（写进 history）")
        item = sp.make_item(d, args.why or "（草稿）", prev)
    except sp.PinError as e:
        print(f"❌ {e}", file=sys.stderr)
        raise SystemExit(2)

    out = Path(args.out or f"seg-pin/{book}-{page}-{col}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "item.json").write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")
    rows = sp.slot_map(before, d.cells)
    (out / "格号对照.tsv").write_text("旧格号\t新格号\t变化\n" + "".join(
        f"{'' if a is None else a}\t{'' if b is None else b}\t{k}\n" for a, b, k in rows), encoding="utf-8")
    png = sp.overlay(d, before, out / "overlay.png")

    # 格式检查（cv 的 check_manual_cells，对单行临时文件）
    from ._cv import check_manual_cells
    tmp = out / "_check.jsonl"
    tmp.write_text(json.dumps(item, ensure_ascii=False) + "\n", encoding="utf-8")
    problems = check_manual_cells(tmp)
    tmp.unlink()

    changed = [r for r in rows if r[2] != "同"]
    print(f"{d.item_id}：起稿自 {d.source}（{len(before)} 格）→ {len(d.cells)} 格；格号有变 {len(changed)} 处")
    print(f"  草稿 {out / 'item.json'}；对照 {out / '格号对照.tsv'}" + (f"；叠框图 {png}" if png else "（没有列图缓存，未出叠框图）"))
    if problems:
        print("❌ 格式不对：\n  " + "\n  ".join(problems), file=sys.stderr)
        raise SystemExit(2)
    if not args.write:
        print("  只出草稿；看过叠框图没问题加 --write --why \"…\" 写进数据目录。")
        return
    path = sp.items_path()
    sp.write_item(path, item)
    print(f"✓ 已写 {path}（{'替换' if prev else '新增'} {d.item_id}）。下一步：")
    print(f"  1. python <cv>/scripts/seg_pins_check.py --book {book} --items {path}   # 沙箱核：静默丢字、人裁失锚、补锚草稿")
    print("  2. guji db pull --force 后 GUJI_ACTOR=<你> guji db sync -w <工作区>          # 推中心库（别人也在写，先拉）")
    print(f"  3. 交单 steps.from=row_segment、pages=\"{page}\"；出包后格号有变按 {out / '格号对照.tsv'} 走 guji swap")


COMMANDS = {"seg": (add_parser, cmd_seg)}
