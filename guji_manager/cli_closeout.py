"""`guji closeout`：标 main 后收尾（A32，方案 8.8）。不连库、不推送，只读写你给的文件。

    guji closeout stats <待审单.json…> [--json]            # 现算：按册、原因码汇总锚点类待审格
    guji closeout list <待审单.json> [--reason anchor_miss] # 锚点类待审格清单（旧新锚、说明）
    guji closeout derive <待审单.json> --repo <book-text 检出> --vdir <版本目录> --chapter NNN
                         [--cells <旧→新 对照表.tsv[.gz]>] [--drift-base origin/dev] [--out 新单.json]
                                                           # A01–A03 按当前 book-text 现算并写进待审单（先清上次的，幂等；方案 8.9）
    guji closeout stamp <待审单.json> --report <分流项.json> [--out 新单.json]
                                                           # 同上，但分流项来自 auto_remap 的 report 文件
    guji closeout lib-disagree <产物包目录> [--out recheck.tsv] [--min-cov 0.97] [--declared 字对.tsv]   # 出单前复核（缺省不跑）
    guji closeout redline <册> --human-total N --human-lost N --anchors-moved N --anchors-left N [--error …] [--glyph-verify-fail]
    guji closeout fix-misplaced --repo <book-text 检出> --vdir <版本目录> --chapter NNN (--cells <dev当前→正确 对照表.tsv[.gz]> | --replay <A33回放不一致明细.tsv>)
                                [--apply] [--audit 审计.tsv] [--sample 30]
                                                           # dev 上机器错位锚点的自动写回（三条件，缺省只出计划）

分流项文件是 JSON 数组，每项 [层, 条目, 旧锚, 新锚, 内容, "原因码｜说明"]（即 `remap_data` 的 report）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .closeout import anchors as A
from .closeout import redlines, stats, writeback


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("closeout", help="标 main 后收尾：锚点待审格、红线、dev 错位自动写回")
    p.add_argument("action", choices=["stats", "list", "stamp", "derive", "redline", "fix-misplaced", "lib-disagree"])
    p.add_argument("target", nargs="*", help="stats／list／stamp：待审单 json；redline：册号")
    p.add_argument("--json", action="store_true")
    p.add_argument("--reason", default=None, help="list：只列这个主因（add_del／anchor_miss／anchor_drift）")
    p.add_argument("--report", default=None, help="stamp：分流项 json")
    p.add_argument("--out", default=None, help="stamp：写到这里（缺省改写原文件）")
    p.add_argument("--human-total", type=int, default=0)
    p.add_argument("--human-lost", type=int, default=0)
    p.add_argument("--anchors-moved", type=int, default=0)
    p.add_argument("--anchors-left", type=int, default=0)
    p.add_argument("--error", action="append", default=[])
    p.add_argument("--glyph-verify-fail", action="store_true")
    p.add_argument("--repo", default=None, help="fix-misplaced：book-text 检出（取 remap_anchors）")
    p.add_argument("--vdir", default=None, help="fix-misplaced：版本目录（NNN.char.json、NNN.punct.json）")
    p.add_argument("--chapter", default=None)
    p.add_argument("--cells", default=None, help="derive：旧→新格级对照表（给了才有 A02）；fix-misplaced：dev 当前→正确 的对照表")
    p.add_argument("--drift-base", default="origin/dev", help="derive：漂移检查的基准版")
    p.add_argument("--replay", default=None, help="fix-misplaced：A33 回放不一致明细 tsv（取标点行，自动得 dev 当前→正确 对照表和旧 pre_char；与 --cells 二选一）")
    p.add_argument("--apply", action="store_true", help="fix-misplaced：真写 punct.json（缺省只出计划）")
    p.add_argument("--audit", default=None, help="fix-misplaced：审计 tsv")
    p.add_argument("--sample", type=int, default=30, help="fix-misplaced：抽审条数（固定种子）")
    p.add_argument("--min-cov", type=float, default=0.97, help="lib-disagree：库首位覆盖率下限")
    p.add_argument("--declared", default=None, help="lib-disagree：补充的已声明字对 tsv（每行 字<TAB>字）")


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _plan_book(path: str) -> str:
    return Path(path).stem


def cmd_closeout(a) -> int:
    act = a.action
    if act == "stats":
        out = {_plan_book(t): stats.plan_stats(_load(t)) for t in a.target}
        if a.json:
            print(json.dumps(out, ensure_ascii=False, indent=1))
        else:
            for b, s in out.items():
                print(f"{b}\t待审 {s['cells']}\t锚点主因 {s['anchor_main']}\t带锚点信息 {s['anchor_any']}\t原因码 {s['by_code']}")
        return 0
    if act == "list":
        plan = _load(a.target[0])
        for x in A.anchor_cells(plan):
            if a.reason and x.get("pending_reason") != a.reason:
                continue
            for e in A.decode(x.get("pending_reason_detail")) or [{}]:
                print("\t".join([x["cell"], x.get("pending_reason", ""), e.get("l", ""), e.get("i", ""), e.get("o", ""),
                                 e.get("n", ""), e.get("c", ""), e.get("w", "")]))
        return 0
    if act == "stamp":
        if not a.target or not a.report:
            sys.exit("stamp 要 <待审单.json> 和 --report <分流项.json>")
        plan = _load(a.target[0])
        items = [tuple(i) for i in _load(a.report)]
        n = A.stamp(plan, items)
        Path(a.out or a.target[0]).write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"清掉上次 {n['purged']} 处；并进已有待审格 {n['appended']}，新增待审格 {n['new']}：" +
              "、".join(f"{r.value} {n[r.value]}" for r in A.ANCHOR_REASONS if n[r.value]))
        return 0
    if act == "derive":
        return _derive(a)
    if act == "lib-disagree":
        return _lib_disagree(a)
    if act == "redline":
        r = redlines.check(a.target[0] if a.target else "?", human_total=a.human_total, human_lost=a.human_lost,
                           anchors_moved=a.anchors_moved, anchors_left=a.anchors_left, errors=a.error,
                           glyph_verify_ok=not a.glyph_verify_fail)
        print(r.line())
        return 0 if r.ok else 1
    return _fix_misplaced(a)


def _derive(a) -> int:
    for k in ("repo", "vdir", "chapter"):
        if not getattr(a, k):
            sys.exit(f"derive 要 --{k}")
    if not a.target:
        sys.exit("derive 要 <待审单.json>")
    from .closeout import derive, remap_lib
    ra = remap_lib.load_ra(a.repo)
    vdir = Path(a.vdir)
    char = _load(str(vdir / f"{a.chapter}.char.json"))
    pf, ef = vdir / f"{a.chapter}.punct.json", vdir / f"{a.chapter}.entity.json"
    punct = _load(str(pf)) if pf.is_file() else None
    entity = _load(str(ef)) if ef.is_file() else None
    rows = ra.load_cells(a.cells) if a.cells else None
    rel = (vdir.resolve() / f"{a.chapter}.char.json").relative_to(Path(a.repo).resolve()).as_posix()
    items = derive.derive(char, punct, entity, rows, derive.drift_items(a.repo, rel, a.drift_base))
    plan = _load(a.target[0])
    n = A.stamp(plan, items, char_of={c["a"]: c["c"] for c in (
        {"a": x, "c": y} for x, y in writeback.slots_of(char))})
    Path(a.out or a.target[0]).write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{a.chapter}：A01–A03 现算 {len(items)} 条；清掉上次 {n['purged']} 处；并进已有待审格 {n['appended']}，新增 {n['new']}")
    return 0


def _lib_disagree(a) -> int:
    """出单前复核（缺省关）：放行字＝整理本字、库首位覆盖率高且是另一个字、非人裁、不在已声明里的格 → recheck 清单。"""
    if not a.target:
        sys.exit("lib-disagree 要 <产物包目录>（含 glyph_match／seed_admit／align_ref）")
    from .closeout import lib_disagree as LD
    rows = LD.scan_pack(a.target[0], declared=LD.load_declared(a.declared), min_cov=a.min_cov)
    lines = LD.recheck_lines(rows)
    if a.out:
        Path(a.out).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    else:
        print("\n".join(lines))
    print(f"{a.target[0]}：{len(rows)} 格（库首位 cov≥{a.min_cov}）" + (f"，清单 → {a.out}" if a.out else ""), file=sys.stderr)
    return 0


def _fix_misplaced(a) -> int:
    for k in ("repo", "vdir", "chapter"):
        if not getattr(a, k):
            sys.exit(f"fix-misplaced 要 --{k}")
    if not (a.cells or a.replay):
        sys.exit("fix-misplaced 要 --cells 或 --replay")
    from .closeout import remap_lib
    ra = remap_lib.load_ra(a.repo)
    vdir = Path(a.vdir)
    char = _load(str(vdir / f"{a.chapter}.char.json"))
    pf = vdir / f"{a.chapter}.punct.json"
    punct = _load(str(pf))
    old_pre = None
    if a.replay:
        import csv
        with open(a.replay, encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f, delimiter="\t"))[1:]
        cellmap, old_pre, notes = writeback.from_replay(rows, a.chapter)
        for n in notes:
            print(f"  冲突，不处理：{n}", file=sys.stderr)
    else:
        cellmap, _st = ra.build_map(ra.load_cells(a.cells))
    ok, skip = writeback.plan_fixes(punct, char, cellmap, old_pre)
    print(f"{a.chapter}：可自动写 {len(ok)} 条，不满足三条件留待审 {len(skip)} 条")
    for s in skip:
        print(f"  跳过 #{s['idx']} {s['old']}→{s['new']}：{s['why']}", file=sys.stderr)
    lines = writeback.audit_lines(a.chapter, ok)
    if a.audit:
        Path(a.audit).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    smp = writeback.sample(ok, a.sample)
    print(f"抽审 {len(smp)} 条（审阅页复核，有错回退并关自动）：" + "、".join(f"#{f['idx']}" for f in smp))
    if a.apply and ok:
        writeback.apply_fixes(punct, char, ok)
        ra.OV.dump_json(str(pf), punct)       # 用 book-text 自己的写法，免得整文件格式变动
        print(f"已写回 {pf}（提交号请记进 commit 信息和轮报告）")
    elif ok:
        print("（计划，未写；加 --apply 才写）")
    return 0


COMMANDS = {"closeout": (add_parser, cmd_closeout)}
