"""标 main 前的硬检查（ZM 11-16，用户「格高异常以后一定要强制检查」）。

`guji seg premain <册…> [--products <根>] [--allow <tsv>]`：对候选包的产物做三条**绝对**检查（不比旧 main，
老错也要报），任何一条命中且不在放行清单里，退出码 3，**不许标 main**：

1. TALL    正文格高 ≥ 1.6 × 本列正文格高中位数（一格含多字／并了邻格；vol14 32:7:14、题名列「法書要」）。
2. FEWER   align_ref 回退原因「格数少于整理本字数」（该列格数不够，整页对不齐、整列进待审；vol16 113:1）。
3. INK_BLANK 判空的正文格墨比 ≥ 0.10（有墨被判空：贴框的「二」、叠连字被并进邻格后留的空格）。

放行清单 TSV：每行 `册<TAB>页<TAB>列[<TAB>原因]`（页或列写 * 通配），已看图确认无害的列放这里。
为什么是绝对检查：`guji seg gate` 只拦回退，main 里已有的老错、新增而不更坏的错它都不报，格高异常因此一直漏。
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

TALL_RATIO = 1.6
INK_BLANK = 0.10
SLIVER_RATIO = 0.4   # INK_BLANK 只查高度够得上一个字的空格；框线残片（vol01 157–203 列尾 11px 的格）不报
MIN_CELLS = 4


def load_allow(path: str | Path | None) -> set[tuple[str, str, str]]:
    out: set[tuple[str, str, str]] = set()
    if not path:
        return out
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        p = ln.split("\t")
        if len(p) >= 3 and not ln.startswith("#"):
            out.add((p[0], p[1], p[2]))
    return out


def _allowed(allow, book: str, page: int, col: int) -> bool:
    return any(a[0] == book and a[1] in ("*", str(page)) and a[2] in ("*", str(col)) for a in allow)


def _body(y: dict) -> bool:
    return y.get("slot", 0) > 0 and not y.get("sub") and y.get("step3_kind") != "jiazhu"


def scan_page(cell_shrink: dict, align_ref: dict | None) -> list[tuple[int, str, str]]:
    """返回 [(列, 类, 说明)]。"""
    hits: list[tuple[int, str, str]] = []
    for c in (cell_shrink.get("char_index") or {}).get("columns", []):
        ch = [y for y in c.get("chars", []) if _body(y)]
        if len(ch) < MIN_CELLS:
            continue
        hs = [y["height"] for y in ch if y.get("cell_type") != "empty" and y.get("height")]
        if not hs:
            continue
        med = statistics.median(hs)
        for y in ch:
            if y.get("height", 0) >= TALL_RATIO * med and y.get("cell_type") != "empty":
                hits.append((c["col"], "TALL", f"格{y['slot']} 高 {y['height']:.0f}＝{y['height'] / med:.2f}×中位 {med:.0f}"))
            elif (y.get("cell_type") == "empty" and (y.get("ink_ratio") or 0) >= INK_BLANK
                  and y.get("height", 0) >= SLIVER_RATIO * med):   # 矮于正文格 0.4 倍的是框线残片（列尾 tail_junk），不是字
                hits.append((c["col"], "INK_BLANK", f"格{y['slot']} 判空但墨比 {y['ink_ratio']:.2f}"))
    fb = ((align_ref or {}).get("align_ref") or {}).get("coord_fallback") or {}
    for k, v in fb.items():
        if "格数少于" in str(v):
            hits.append((int(k), "FEWER", str(v)))
    return hits


def run(books: list[str], products: Path, allow: set, pages: set[int] | None = None) -> list[tuple]:
    rows = []
    for b in books:
        d = products / b / "cell_shrink"
        for f in sorted(d.glob("p*.json")):
            pg = int(f.stem[1:])
            if pages and pg not in pages:
                continue
            ar = products / b / "align_ref" / f.name
            hits = scan_page(json.loads(f.read_text(encoding="utf-8")),
                             json.loads(ar.read_text(encoding="utf-8")) if ar.exists() else None)
            for col, kind, why in hits:
                if not _allowed(allow, b, pg, col):
                    rows.append((b, pg, col, kind, why))
    return rows
