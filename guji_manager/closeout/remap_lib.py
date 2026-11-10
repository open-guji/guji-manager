"""把 book-text 的 `remap_anchors.remap_data` 当库调用（A33 11-09：入参为已读入 dict，就地修改，不读写文件）。"""
from __future__ import annotations

import copy
import sys
from pathlib import Path


def load_ra(book_text: str | Path):
    """导入 `<book-text>/scripts/book-text/remap_anchors.py`；它 import original_version，要 scripts 在 sys.path。"""
    root = Path(book_text) / "scripts"
    for d in (root, root / "book-text"):
        if str(d) not in sys.path:
            sys.path.insert(0, str(d))
    import remap_anchors
    if not hasattr(remap_anchors, "remap_data"):
        raise SystemExit("book-text 的 remap_anchors 没有 remap_data：请拉最新 dev（db6ae098a 之后）")
    return remap_anchors


def run(ra, chapter: str, char: dict, punct: dict | None, entity: dict | None, rows, *,
        refresh: bool = True, iou_min: float | None = None):
    """跑一次，**不动入参**（深拷贝后算）。返回 dict：res、report、moves、punct、entity（改后的副本）、
    moved（锚点改动数）、left（分流数）。"""
    p, e = copy.deepcopy(punct), copy.deepcopy(entity)
    kw = {} if iou_min is None else {"iou_min": iou_min}
    res, report, moves = ra.remap_data(chapter, char, p, e, rows, refresh=refresh, **kw)
    moved = sum(res[k][0] for k in ("punct", "entity"))
    left = sum(res[k][1] for k in ("punct", "entity"))
    return {"res": res, "report": report, "moves": moves, "punct": p, "entity": e, "moved": moved, "left": left}
