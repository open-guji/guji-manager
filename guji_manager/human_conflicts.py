"""`guji human-conflicts`：推库前查跨批次人裁冲突——同一个现格被几批人裁定成不同的字，谁生效。

SJ 11-21：本线 r1–r4 与取消归一批本地累计 63 格待推，几批之间同格互相覆盖，推之前要看清。
口径不另写一套：
- 现格：每条人裁先过绑定表（cv `feedback.bindings.book_bindings` ＋ `usable`，同 `human_chars`／`collect.batch_cells`），
  绑不上的单列；
- 生效字：cv `feedback.lookup.human_chars`（seed_admit 人裁通道同一口径：按 (ts, 批次, seq) 后到覆盖、撤库作废、看图不算人裁）。
本命令只把同一现格上「不同批次、不同字」的人裁列出来，并标出 human_chars 认的是哪一条。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _bare(cell: str) -> str:
    return cell.split(":", 1)[1] if cell.count(":") == 3 else cell


def collect_events(book: str, log) -> list:
    """本册格级定字人裁（confirm／seg_defect 带字，counts_as_pin：人裁＋AI 钉，AI 后写盖过人裁的也报），按 (ts, batch, seq) 排。"""
    from .feedback.levels import counts_as_pin
    out = []
    for e in log.iter_all():
        if e.kind != "confirm" or e.target.unit != "cell" or not e.target.key.startswith(f"{book}:"):
            continue
        p = e.payload or {}
        if p.get("v") not in ("confirm", "seg_defect") or not p.get("shape") or not counts_as_pin(e):
            continue
        out.append(e)
    return sorted(out, key=lambda e: (e.ts, e.batch, e.seq))


def find_conflicts(evs: list, bound: dict, effective: dict[str, str], usable, batches: set[str] | None = None) -> tuple[list[dict], list[dict]]:
    """→ (冲突行, 绑不上的行)。`bound`：{event_id: 绑定行}；`effective`：human_chars 的 {现格: 字}。
    `batches` 给了就只报牵涉到这些批次的格。"""
    by: dict[str, list] = {}
    lost = []
    for e in evs:
        key = usable(bound.get(e.id), e.ts) if e.id in bound else e.target.key
        if key is None:
            if not batches or e.batch in batches:
                lost.append({"cell": e.target.key, "char": e.payload["shape"], "batch": e.batch, "ts": e.ts,
                             "status": (bound.get(e.id) or {}).get("status")})
            continue
        by.setdefault(key, []).append(e)
    rows = []
    for key, lst in by.items():
        chars = {str(e.payload["shape"]) for e in lst}
        if len(chars) < 2 or len({e.batch for e in lst}) < 2:
            continue
        if batches and not any(e.batch in batches for e in lst):
            continue
        win = effective.get(key)
        hist = "；".join(f"{e.batch}@{e.ts[:16]}:{e.payload['shape']}" + ("" if e.target.key == key else f"（原 {_bare(e.target.key)}）")
                        for e in lst)
        last = lst[-1]
        rows.append({"cell": key, "生效字": win or "（不采信）", "生效批次": next((e.batch for e in reversed(lst) if str(e.payload["shape"]) == win), ""),
                     "最后一条": f"{last.batch}:{last.payload['shape']}", "历次": hist,
                     "注意": "" if win == str(last.payload["shape"]) else "生效字不是最后一条（撤库作废／看图等口径），按 human_chars 为准"})
    rows.sort(key=lambda r: r["cell"])
    return rows, lost


def cmd(a) -> int:
    if a.workspace:
        os.environ["GUJI_WORKSPACE"] = str(Path(a.workspace).resolve())
    if a.products:
        os.environ["GUJI_PRODUCTS_DIR"] = str(Path(a.products).resolve())
    from ._cv import EventLog, book_bindings, bindings_usable, feedback_root, human_chars
    log = EventLog(feedback_root())
    want = {x.strip() for x in (a.batches or "").split(",") if x.strip()} or None
    out_rows, out_lost = [], []
    for book in [b.strip() for b in a.books.split(",") if b.strip()]:
        evs = collect_events(book, log)
        if want:
            miss = want - {e.batch for e in evs}
            if miss:
                print(f"{book}：这些批次里没有本册格级人裁：{','.join(sorted(miss))}", file=sys.stderr)
        bound = book_bindings(book)
        eff = human_chars(book)
        rows, lost = find_conflicts(evs, bound, eff, bindings_usable, want)
        print(f"{book}：人裁 {len(evs)} 条；跨批次同格不同字 {len(rows)} 格；绑不上 {len(lost)} 条", file=sys.stderr)
        out_rows += rows
        out_lost += lost
    cols = ["cell", "生效字", "生效批次", "最后一条", "历次", "注意"]
    text = "\t".join(cols) + "\n" + "".join("\t".join(str(r[c]) for c in cols) + "\n" for r in out_rows)
    if out_lost:
        text += "\n# 绑不上现格（推了也不采信）\ncell\t字\t批次\tts\t绑定状态\n" + "".join(
            f"{x['cell']}\t{x['char']}\t{x['batch']}\t{x['ts']}\t{x['status']}\n" for x in out_lost)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"清单：{a.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 3 if out_rows else 0


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("human-conflicts", help="推库前查跨批次人裁冲突：同一现格几批定成不同字、谁生效（口径同 human_chars）")
    p.add_argument("--books", required=True, help="册，逗号分隔")
    p.add_argument("--batches", default=None, help="只报牵涉这些批次的格（如本地待推的 r1,r2,r3,r4），逗号分隔；缺省全部")
    p.add_argument("--products", default=None, help="产物根（绑定表按它算；缺省本机产物根）")
    p.add_argument("-w", "--workspace", default=None, help="工作区（缺省 GUJI_WORKSPACE）")
    p.add_argument("--out", default=None, help="清单 tsv（缺省打到标准输出）。有冲突时退出码 3")


def _cmd(a) -> None:
    sys.exit(cmd(a))


COMMANDS = {"human-conflicts": (add_parser, _cmd)}
