"""`guji seg`：切分的人定与检查（A22，2026-11-12）。

- `guji seg pin <册:页:列> [编辑…]`：整列写定（manual-cells），见 `seg_pin.py` 模块头与 cv `doc/2-切字/切分覆盖.md` 第四节。
- `guji seg check <册…>`：切分核查（并了 SJ 史記快筛、cv seg_screen、待审原因码），见 `seg_check.py` 模块头。
- `guji seg ruler`：人修过的列（召回尺子），给 `seg check --recall`。
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

    p = sub.add_parser("seg", help="切分的人定与检查：pin（整列写定 manual-cells）、check（切分核查）、ruler（召回尺子）、gate（标 main 前不回退闸）")
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

    ck = ss.add_parser("check", help="切分核查：按列出 类／处置（格号不符、版式不符、需钉子…）、需看图缩略图、报告；退出码 3＝有要看图的列")
    ck.add_argument("books", nargs="+", help="册 id")
    ck.add_argument("-w", "--workspace", default=None)
    ck.add_argument("--pages", default="", help="只查这些页：1,5,10-20（各册通用）")
    ck.add_argument("--skip", default="", help="点名跳过的页，册:页 或 册:起-止，逗号分隔；与 workspace.yaml 的 seg_check.skip 合并")
    ck.add_argument("--head-pages", type=int, default=None, help="每册前几页当卷首页单列（缺省读 workspace.yaml，再缺省 0）")
    ck.add_argument("--no-cell", action="store_true", help="不跑格级 flags（要读字块，慢）")
    ck.add_argument("--no-defect", action="store_true", help="不跑同字对照切坏检测（并格／切笔／带框，要读全册字块）")
    ck.add_argument("--no-causes", action="store_true", help="不读待审原因码（产物没有 seed_admit 时自动跳过）")
    ck.add_argument("--montage", type=int, default=60, help="缩略图最多几列")
    ck.add_argument("--recall", default="", help="召回尺子 TSV（guji seg ruler 出的），量各检查的查全")
    ck.add_argument("--out", default="", help="报告目录（缺省 ./seg-check）")
    ck.add_argument("--job", action="store_true",
                    help="任务单用：要看的列在前、计数与结论压最后（任务库只留输出尾巴），有要处理的列也退出 0")

    rl = ss.add_parser("ruler", help="中心库人修过的列（manual-cells、column-slots、抬头、拖线、solo-notes）＋第一次写的时间")
    rl.add_argument("books", nargs="*", help="只要这些册（缺省全部）")
    rl.add_argument("-w", "--workspace", default=None)
    rl.add_argument("--out", default="seg-ruler.tsv")

    ps = ss.add_parser("pins-stale", help="钉子（manual-cells）的上游列图变了没有：stale＝列窗口变了、坐标必须重核（退出 3）；maybe＝只是 column_warp 指纹变了")
    ps.add_argument("books", nargs="*", help="只查这些册（缺省全部 active 钉子）")
    ps.add_argument("-w", "--workspace", default=None)
    ps.add_argument("--products", default="", help="产物根（缺省工作区 products；候选包 pack fetch --to 的目录）")

    pb = ss.add_parser("pins-backfill-geom", help="一次性：给没记几何底的老钉子补 geom（只补列窗与钉子当时的底一致的；缺省只列，--write 才写）")
    pb.add_argument("books", nargs="*", help="只补这些册（缺省全部 active 钉子）")
    pb.add_argument("-w", "--workspace", default=None)
    pb.add_argument("--products", default="", help="产物根（缺省工作区 products）")
    pb.add_argument("--write", action="store_true", help="写回 manual-cells 分片（之后 guji db sync）")

    pm = ss.add_parser("premain", help="标 main 前的硬检查（绝对、不比旧 main）：格高≥1.6倍、格数少于整理本字数、判空却有墨；命中退出 3，不许标 main")
    pm.add_argument("books", nargs="+", help="册 id")
    pm.add_argument("--products", default="", help="产物根（缺省取 GUJI 的 products 根；候选包先 guji products pack fetch --to <根>）")
    pm.add_argument("--allow", default="", help="放行清单 TSV：册\t页\t列[\t原因]（页、列可写 *），看过图确认无害的列")
    pm.add_argument("--pages", default="", help="只查这些页")
    pm.add_argument("--out", default="", help="命中清单 TSV 输出（缺省不写）")

    gt = ss.add_parser("gate", help="标 main 前的切分不回退闸：比新旧两份 seg check，回退或新页级错退出 3，出切分未定清单")
    gt.add_argument("new", help="候选包的 guji seg check 输出目录（或其 列清单.tsv）")
    gt.add_argument("--base", required=True, help="现役 main 的 guji seg check 输出目录（同样页范围、同样开关）")
    gt.add_argument("--ledger", default="", help="切分根因台账 TSV（ai-team domain/CV/A22/切分根因台账.tsv）")
    gt.add_argument("--book", default="", help="台账里的书名（殿本／史記／全唐文…），给了 --ledger 必给")
    gt.add_argument("--page-cols", type=int, default=4, help="一页几列结构列且过半算页级错（缺省 4）")
    gt.add_argument("--new-label", default="", help="候选包标签，写进报告")
    gt.add_argument("--base-label", default="", help="现役 main 包标签，写进报告")
    gt.add_argument("--out", default="seg-gate", help="输出目录（gate.md、gate.json、切分未定.tsv）")


def cmd_seg(args) -> None:
    if args.seg_cmd == "pin":
        _cmd_pin(args)
    elif args.seg_cmd == "check":
        _cmd_check(args)
    elif args.seg_cmd == "ruler":
        _cmd_ruler(args)
    elif args.seg_cmd == "gate":
        _cmd_gate(args)
    elif args.seg_cmd == "premain":
        _cmd_premain(args)
    elif args.seg_cmd == "pins-stale":
        _cmd_pins_stale(args)
    elif args.seg_cmd == "pins-backfill-geom":
        _cmd_pins_backfill(args)


def _cmd_pins_backfill(args) -> None:
    from . import seg_pin as sp
    _use_ws(args)
    store = None
    if args.products:
        from ._cv import ProductStore
        store = ProductStore(Path(args.products))
    path = sp.items_path()
    items = [r for r in sp.read_items(path) if r.get("status") == "active"
             and (not args.books or (r.get("anchor") or {}).get("book") in args.books)]
    done = 0
    print("钉子\t结果")
    for r in items:
        new, why = sp.backfill_geom(r, store)
        if new is None:
            print(f"{r.get('id')}\t不补：{why}")
            continue
        done += 1
        print(f"{r.get('id')}\t补 geom")
        if args.write:
            sp.write_item(path, new)
    print(f"共 {len(items)} 条，可补 {done} 条" + ("，已写回（记得 guji db sync）" if args.write and done else
                                              ("；加 --write 写回" if done else "")), file=sys.stderr)


def _cmd_pins_stale(args) -> None:
    from . import seg_pin as sp
    _use_ws(args)
    store = None
    if args.products:
        from ._cv import ProductStore
        store = ProductStore(Path(args.products))
    items = [r for r in sp.read_items(sp.items_path()) if r.get("status") == "active"
             and (not args.books or (r.get("anchor") or {}).get("book") in args.books)]
    n = {"ok": 0, "stale": 0, "maybe": 0, "unknown": 0}
    print("钉子\t状态\t说明")
    for r in items:
        st, why = sp.basis_status(r, store)
        n[st] += 1
        if st != "ok":
            print(f"{r.get('id')}\t{st}\t{why}")
    print(f"共 {len(items)} 条：" + "、".join(f"{k} {v}" for k, v in n.items() if v), file=sys.stderr)
    if n["stale"]:
        print("stale 的钉子坐标对不上现在的列图：guji seg pin <册:页:列> 重起稿看叠框图、重写（--write 会记新底）", file=sys.stderr)
        raise SystemExit(3)


def _cmd_premain(args) -> None:
    from . import seg_check, seg_premain
    from ._cv import products_root
    root = Path(args.products) if args.products else Path(products_root())
    rows = seg_premain.run(args.books, root, seg_premain.load_allow(args.allow or None),
                           seg_check.parse_pages(args.pages) if args.pages else None)
    if args.out:
        Path(args.out).write_text("册\t页\t列\t类\t说明\n" + "".join("\t".join(map(str, r)) + "\n" for r in rows), encoding="utf-8")
    for r in rows:
        print(f"{r[0]}:{r[1]}:{r[2]}\t{r[3]}\t{r[4]}")
    n = len({(r[0], r[1], r[2]) for r in rows})
    print(f"seg premain：{'、'.join(args.books)} 命中 {len(rows)} 条（{n} 列）" + ("，不许标 main；看图确认无害的列写进 --allow 清单" if rows else "，通过"))
    raise SystemExit(3 if rows else 0)


def _cmd_gate(args) -> None:
    from . import seg_gate
    text, code = seg_gate.run(Path(args.new), Path(args.base), Path(args.out),
                              ledger_path=Path(args.ledger) if args.ledger else None, page_cols=args.page_cols,
                              new_label=args.new_label, base_label=args.base_label, book=args.book)
    print(text)
    raise SystemExit(code)


def _use_ws(args) -> Path | None:
    import os
    if args.workspace:
        os.environ["GUJI_WORKSPACE"] = str(Path(args.workspace).resolve())
    w = os.environ.get("GUJI_WORKSPACE")
    return Path(w) if w else None


def _cmd_check(args) -> None:
    from . import seg_check as sc
    ws = _use_ws(args)
    cfg = sc.book_config(ws)
    try:
        skip = sc.parse_skip(",".join(f"{v}:{p}" for v, ps in (cfg.get("skip") or {}).items()
                                      for p in str(ps).split(",") if p.strip()))
        for v, ps in sc.parse_skip(args.skip).items():
            skip.setdefault(v, set()).update(ps)
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        raise SystemExit(2)
    head = args.head_pages if args.head_pages is not None else int(cfg.get("head_pages") or 0)
    text, code = sc.run(args.books, Path(args.out or "seg-check"), pages=sc.parse_pages(args.pages) or None,
                        skip=skip, head_pages=head, cell_checks=not args.no_cell, causes=not args.no_causes,
                        montage_limit=args.montage, ruler_tsv=Path(args.recall) if args.recall else None,
                        defect=not args.no_defect, ws=ws)
    if args.job:
        print(sc.job_text(text))
        raise SystemExit(0)
    print(text)
    raise SystemExit(code)


def _cmd_ruler(args) -> None:
    import csv

    from . import seg_check as sc
    _use_ws(args)
    rows = sc.ruler_rows(args.books or None)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["book", "page", "col", "source", "status", "ts"], delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    import collections
    cnt = collections.Counter(r["source"] for r in rows)
    print(f"{args.out}：{len(rows)} 列（" + "，".join(f"{k} {v}" for k, v in cnt.most_common()) + "）")


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
