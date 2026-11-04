# -*- coding: utf-8 -*-
"""`border_class` 打回路由（2026-09-27）：核实过前端全部卡片 id 形态后接上——

`border_class` 只有两种真实/代码列级形态（`colborder:`、无前缀 `book:page:col`），
`headcol:`/`outer:` 两种前缀核实后**不是** `border_class`（分别是 `head_raise`/
`verdict`），见 `feedback/border_class_route.py` 模块头的表。路由只标记过期
（`product_invalidate`），不起跑批，同 `cutline`/`n_body_slots` 已有的做法。
"""
from __future__ import annotations

from guji_manager.feedback.border_class_route import is_defect_answer, parse_border_class_key
from open_guji_cv.feedback.events import EventTarget, make_event
from guji_manager.feedback.routes import RouteTable


# ── parse_border_class_key：覆盖每种 id 形态 ─────────────────────────────

def test_parse_colborder_id_with_end_suffix():
    u = parse_border_class_key("colborder:vol01:47:2:top")
    assert (u.book, u.page, u.col, u.end) == ("vol01", 47, 2, "top")
    u = parse_border_class_key("colborder:vol01:47:2:bot")
    assert u.end == "bot"


def test_parse_plain_column_id_with_no_end():
    u = parse_border_class_key("bxgb:38:14")
    assert (u.book, u.page, u.col, u.end) == ("bxgb", 38, 14, None)


def test_headcol_and_outer_ids_are_not_border_class_forms():
    """`headcol:`/`outer:` 前缀核实后不是 `border_class` 的 id（分别是
    `head_raise`/`verdict`），解析函数故意不认，混进来会把打回挂错列/页。"""
    assert parse_border_class_key("headcol:vol02:11:4") is None
    assert parse_border_class_key("outer:vol01:47:top") is None


def test_unparseable_id_returns_none():
    assert parse_border_class_key("not-a-valid-id") is None
    assert parse_border_class_key("cols:vol02:171") is None


# ── is_defect_answer：两种 payload 形状都要认 ────────────────────────────

def test_is_defect_answer_column_review_panel_shape():
    assert is_defect_answer({"top_class": "glued", "bot_class": "clean",
                             "border_class": "top=glued,bot=clean"})
    assert is_defect_answer({"top_class": "clean", "bot_class": "none",
                             "border_class": "top=clean,bot=none"})
    assert not is_defect_answer({"top_class": "clean", "bot_class": "clean",
                                 "border_class": "top=clean,bot=clean"})
    assert not is_defect_answer({"top_class": "idk", "bot_class": "clean",
                                 "border_class": "top=idk,bot=clean"})


def test_is_defect_answer_colborder_shape():
    assert is_defect_answer({"border_class": "glued", "question": "column_warp.page.border_class"})
    assert is_defect_answer({"border_class": "none"})
    assert not is_defect_answer({"border_class": "clean"})
    assert not is_defect_answer({"border_class": "idk"})


# ── 路由：只在 glued/none 时标记过期，clean/idk 不触发 ───────────────────

def _colreview_event(book, page, col, top_class, bot_class, seq=1):
    key = f"{book}:{page}:{col}"
    return make_event(f"{book}-column", seq, "border_class",
                      EventTarget(step="column_warp", unit="column", key=key,
                                  book=book, page=page, col=col),
                      {"top_class": top_class, "bot_class": bot_class,
                       "border_class": f"top={top_class},bot={bot_class}"})


def _colborder_event(book, page, col, end, answer, seq=1):
    key = f"colborder:{book}:{page}:{col}:{end}"
    return make_event(f"{book}-colborder-review", seq, "border_class",
                      EventTarget(step="column_warp", unit="column", key=key,
                                  book=book, page=page, col=col),
                      {"border_class": answer, "question": "column_warp.page.border_class"})


