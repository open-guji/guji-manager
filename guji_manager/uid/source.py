"""一页「这份切分」从哪来：cv 产物（切字后入账）或 book-text 的 char＋cord（从现行文本重建账）。

两边的框都折成 cord 空间（左上原点 ``[x, y, w, h]``），口径同 book-text 导出（``formats/guji_page_cv``）：
字框（Step4 ``cell_shrink`` 的 ``bbox_page``）优先，没有字框（空格）再用格四角的外接框 ``quad_bounds(quad_page)``。
所以从 book-text 建的账与之后从产物入账的行可以直接按框对照（11-25 试点实测：只用格框时 vol31 有 4,518 格 IoU 不够、
靠中心距才配上）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .match import Cell, xywh_to_box


@dataclass
class PageCut:
    page: int
    cells_sha: str | None
    cells: list[Cell]            # 读序
    boxes: dict[str, list]       # 格号 → [x, y, w, h]（cord 空间）


# ───────────────────────── cv 产物 ─────────────────────────

def product_pages(store, book: str) -> list[int]:
    """有 Step3 切分产物的页（升序）。"""
    from .._cv import cells_step
    return sorted(int(k[1:]) for k in store.keys(book, cells_step(book)) if k[1:].isdigit())


def cells_sha(store, book: str, page: int) -> str | None:
    return page_cells_sha(book, page, store)


def page_cells_sha(book: str, page: int, store) -> str | None:
    """本页产物戳，口径同 cv ``feedback.rulings.page_cells_sha``（cv ≥0.7.103）：``bindings.page_state`` 的两份 sha 用「+」连。
    旧 cv（如史記 0.7.98 线）没有这个函数时按同口径自算，标 main 入账不挑执行机的 cv 版本（11-25 史記 42 册首次实测挂在这）。"""
    try:
        from .._cv import page_cells_sha as f
    except (ImportError, AttributeError):
        f = None
    if f is not None:
        return f(book, page, store)
    from .._cv import page_state
    cells, patch = page_state(book, page, store)
    return f"{cells}+{patch or ''}" if cells else None


def chars_fresh(store, book: str, key: str) -> bool:
    """这一页的 seed_admit 是不是在现行字块（cell_shrink）上跑的：manifest 里记的上游 char_index sha＝现行 cell_shrink 文件 sha。
    只重切到 cell_shrink、没再跑识字时，seed_admit 是旧切分的结果，按格号取字会整列错位（11-25 试点 vol28 p3：「業」格拆半，
    旧字把沿用 u 判给了后半小块），这时不取字、只按框对照。"""
    try:
        from ..products_io import DECIDE_STEPS
        e = next((x for x in (store.manifest(book, st).get(key) for st in DECIDE_STEPS) if x), None)   # char_decide 先，seed_admit 后
        return bool(e) and e.upstream.get("char_index") == store.sha(book, "cell_shrink", key)
    except Exception:  # noqa: BLE001 —— 拿不到 manifest：当它不新鲜
        return False


def from_products(store, book: str, page: int, *, with_chars: bool = True) -> PageCut | None:
    """读现行产物里这一页的切分；没有 Step3 产物 → None。"""
    from .._cv import Borders, cells_step, page_key, read_view
    from ..formats.guji_page import quad_bounds, tr_bbox_to_xywh
    key = page_key(page)
    cells = read_view(store, book, cells_step(book), key, "cells")
    if cells is None:
        return None
    sha = cells_sha(store, book, page)
    bd = store.read_raw(book, "border_detect", key)
    W = Borders.model_validate(bd["borders"]).width if bd else None
    chars: dict[str, str | None] = {}
    if with_chars and chars_fresh(store, book, key):
        try:
            from .._cv import page_slots
            chars = {s.id: s.char for s in page_slots(store, book, page, [])}
        except Exception:  # noqa: BLE001 —— 没跑到 seed_admit：不带字，只按框对照
            chars = {}
    # 框口径同 book-text cord（formats/guji_page_cv）：字框（cell_shrink 的 bbox_page）优先，没有再用格的四角外接框
    ink: dict[str, list] = {}
    inked: set[str] = set()
    chars_idx = read_view(store, book, "cell_shrink", key, "char_index") if W else None
    if chars_idx is not None:
        for col in chars_idx.columns:
            for ch in col.chars:
                if ch.cell_type != "empty":
                    inked.add(ch.id)
                if ch.bbox_page is not None and ch.cell_type != "empty":
                    ink[ch.id] = tr_bbox_to_xywh(ch.bbox_page, W)
    # 空格（c=""）：字块里没墨的格；只在识字新鲜（chars 有）时标，免得 cell_shrink 与切分不同步时误判（uid.match 第 0 条）
    blank = chars_idx is not None and bool(chars)
    out: list[Cell] = []
    boxes: dict[str, list] = {}
    for col in sorted(cells.columns, key=lambda c: c.col):
        for c in sorted(col.cells, key=lambda c: c.order):
            cid = f"{book}:{page}:{col.col}:{c.slot}{c.sub or ''}"
            b = ink.get(cid) or (tr_bbox_to_xywh(quad_bounds(c.quad_page), W) if (c.quad_page and W) else None)
            if b:
                boxes[cid] = b
            out.append(Cell(cid, xywh_to_box(b), "" if blank and cid not in inked and not chars.get(cid) else chars.get(cid)))
    return PageCut(page, sha, out, boxes)


# ───────────────────────── book-text ─────────────────────────

def load_json(p: Path | str) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def from_book_text(book: str, char: dict, cord: dict | None) -> tuple[list[PageCut], dict[str, int]]:
    """char＋cord → 每页一份切分（cells_sha 为 null），以及 char 里已有的 u（v0.6；没有就是空表）。
    格号＝``册:`` + char 的 ``a``（book-text 的 a 是 CV 格 id 去册前缀）。"""
    box_of: dict[str, list] = {}
    for pg in (cord or {}).get("pages") or []:
        for x in pg.get("cells") or []:
            if x.get("box"):
                box_of[x["a"]] = list(x["box"])
    pages: list[PageCut] = []
    have_u: dict[str, int] = {}
    for pg in char.get("pages") or []:
        cells: list[Cell] = []
        boxes: dict[str, list] = {}
        for col in pg.get("columns") or []:
            for x in col.get("cells") or []:
                cid = f"{book}:{x['a']}"
                b = box_of.get(x["a"])
                if b:
                    boxes[cid] = b
                cells.append(Cell(cid, xywh_to_box(b), x.get("c")))
                if isinstance(x.get("u"), int):
                    have_u[cid] = x["u"]
        pages.append(PageCut(int(pg["page"]), None, cells, boxes))
    return pages, have_u
