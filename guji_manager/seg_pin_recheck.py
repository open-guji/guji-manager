"""无几何底老钉子的批量重核（CV0 11-26 批，CV1）。

老钉子（manager v0.6.35 之前写的）没记列图几何底 `geom`，列图变了也没法换算。这里拿**现行列图**逐条核：

1. 生效：现行 row_segment 那一列带 `manual_cells` 旗、格框与钉子一致（没用上＝该页没重跑，先重跑再核）；
2. 在图内：钉子框不出现行列图；
3. 不压墨、不一格跨两字（cv `eval.seg_screen.pin_geometry`，同 `scripts/seg_pins_check.py` 第 1b 节；
   没有 U-Net 裁判时压墨只当提示）；
4. 格外没有成段的墨（cv `feedback.pins_check.uncovered_ink`，同第 1c 节②；压着印章的只当提示）；
5. 有 cell_shrink 产物时，钉子每格都出同号字格（同第 1 节）。

全过 → 认定钉子对现行列图有效，补 `column_basis`（含 geom），history 记「重核补底」；不过 → 列进清单，人用
`guji pipeline seg pin` 重钉。只读产物和列图缓存，`--write` 才写 manual-cells 分片。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import seg_pin as sp

#: 钉子格框与产物格框比对的容差（px）：产物里的框就是钉子原样抄进去的，只差浮点取整。
SAME_TOL = 0.6
#: 钉子框出列图边界多少 px 算「不在图内」。
EDGE_TOL = 2.0


@dataclass
class Recheck:
    id: str
    status: str                      # ok／fail／skip
    problems: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)
    item: dict | None = None         # status=ok 时补好底的新条目


def _key(c) -> tuple:
    g = c.get if isinstance(c, dict) else (lambda k, d=None: getattr(c, k, d))
    return (int(g("slot")), str(g("sub") or ""))


def effective(pin: list[dict], col_cells) -> tuple[bool, str]:
    """现行 row_segment 这一列是不是用了这条钉子（钉子改了而页没重跑＝没生效）。

    看列旗 `manual_cells` 与格框；cv v0.9.6 起列图几何变了会把钉子换算到新列图（列旗 `manual_cells_remapped`），
    那样框不再逐位相同，只比格号。"""
    if col_cells is None:
        return False, "现行 row_segment 没有这一列"
    if "manual_cells" not in (col_cells.flags or []):
        return False, "现行 row_segment 这一列不是按钉子切的（钉子写在产物之后，该页还没重跑）"
    got = {_key(c): c for c in col_cells.cells}
    want = {_key(c): c for c in pin}
    if set(got) != set(want):
        return False, "现行 row_segment 这一列的格号与钉子不同（钉子改过，该页还没重跑）"
    if "manual_cells_remapped" in (col_cells.flags or []):
        return True, ""
    for k, c in want.items():
        o = got[k]
        if any(abs(float(c[a]) - float(getattr(o, a))) > SAME_TOL for a in ("y0", "y1", "x0", "x1")):
            return False, f"现行 row_segment 第 {k[0]}{k[1]} 格的框与钉子不同（钉子改过，该页还没重跑）"
    return True, ""


def recheck_item(item: dict, store, cache, judge=None) -> Recheck:
    from ._cv import (check_pin_vs_chars, column_key, imread, page_key, page_pitch, pin_geometry,
                      seal_spans_col, uncovered_ink)
    from ._cv import steps as _s  # noqa: F401 —— 注册产物种类
    import cv2

    a = item.get("anchor") or {}
    book, page, col = str(a.get("book")), int(a.get("page")), int(a.get("col"))
    rid = item.get("id") or f"{book}:{page}:{col}"
    pin = (item.get("expected") or {}).get("cells") or []
    r = Recheck(rid, "fail")
    if not pin:
        r.status, r.problems = "skip", ["钉子没有格"]
        return r
    key = page_key(page)
    pcells = store.read(book, "row_segment", key, "cells")
    cc = None if pcells is None else next((c for c in pcells.columns if c.col == col), None)
    if pcells is None:
        r.status, r.problems = "skip", ["本机没有该页 row_segment 产物（先 products pack fetch）"]
        return r
    ok, why = effective(pin, cc)
    if not ok:
        r.problems.append("未生效：" + why + "，先重跑该页再核")
        return r
    p = cache.get(book, "column_image", column_key(page, col)) if cache is not None else None
    gray = imread(str(p), cv2.IMREAD_GRAYSCALE) if p is not None else None
    if gray is None:
        r.status, r.problems = "skip", ["本机没有这一列的列图缓存"]
        return r
    h, w = gray.shape[:2]
    out = [c for c in pin if float(c["y1"]) > h + EDGE_TOL or float(c["x1"]) > w + EDGE_TOL
           or float(c["y0"]) < -EDGE_TOL or float(c["x0"]) < -EDGE_TOL]
    if out:
        r.problems.append(f"{len(out)} 格的框出了现行列图（{w}×{h}），坐标是旧列图的")
    for t in pin_geometry(gray, cc, page_pitch(pcells), judge=judge):
        (r.problems if t["block"] else r.hints).append(t["note"])
    if judge is None:
        r.hints.append("没有 U-Net 归属裁判，压墨只当提示")
    seals = store.read(book, "seal_detect", key, "seals")
    spans = seal_spans_col(cc, seals.seals) if seals is not None else ()
    for u in uncovered_ink(gray, cc, page_pitch(pcells) or cc.period, seal_spans=spans):
        msg = f"格外成段的墨：列图 y {u['y0']}–{u['y1']}（高 {u['h']}px），不在任何格里"
        (r.hints if u["seal"] else r.problems).append(msg + ("，压着印章" if u["seal"] else ""))
    chars = store.read(book, "cell_shrink", key, "char_index")
    if chars is not None:
        col_chars = next((c for c in chars.columns if c.col == col), None)
        r.problems += check_pin_vs_chars(pin, col_chars)
    if r.problems:
        return r
    basis = sp.column_basis(book, page, col, store)
    if not basis or not basis.get("geom"):
        r.status, r.problems = "skip", ["本机 column_warp 产物取不出几何底"]
        return r
    new = copy.deepcopy(item)
    new.setdefault("input", {})["column_basis"] = basis
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new["history"] = [*(item.get("history") or []),
                      {"ts": ts, "change": "updated", "why": "重核补底：钉子在现行列图上全项检查通过，补列图几何底 geom"}]
    r.status, r.item = "ok", new
    return r


def needs_recheck(item: dict) -> bool:
    """active 且没有 geom 的钉子。"""
    b = (item.get("input") or {}).get("column_basis") or {}
    return item.get("status") == "active" and not b.get("geom")
