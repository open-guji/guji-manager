# -*- coding: utf-8 -*-
"""字位流 · 排除名单按理由分两路（2026-09-20 bxgb 对勘查出来的）。

`not_a_char`（非字）才是「这一格本不存在」；`seg_defect`/`damaged` 是「字确实在这儿、
图块不能进库」——字位必须占住，文本层出阙文，否则整列字数对不上、对勘把它们报成
「整理本有刻本无」（bxgb 155 条名单里 131 条 seg_defect，80 条正落在漏字位上）。
"""

from __future__ import annotations

from open_guji_cv.products.kinds.cells import CellRec
from open_guji_cv.products.kinds.recog import AdmitRec
from guji_manager.render.guji_markdown import render_column
from open_guji_cv.report.slots import _to_slot


def _cell(slot: int) -> CellRec:
    return CellRec(slot=slot, pos=slot, y0=0, y1=0, x0=0, x1=0, kind="char", sub=None, order=slot)


def _excluded(slot: int, note: str | None, char: str | None = None) -> AdmitRec:
    return AdmitRec(id="", slot=slot, sub=None, admit=False, char=char, reading=None,
                    channel=None, doubts=["excluded"],
                    evidence=({"excluded": note} if note is not None else {}))


def _slot(rec: AdmitRec):
    return _to_slot("bxgb", 6, 7, rec, _cell(rec.slot))


def test_damaged_with_guess_renders_bracketed_guess():
    """p27c8s6：原刻缺了一块，人裁「最像 塊」→ 文本层 □ 占位并括注 guess（用户 2026-09-20）。"""
    rec = AdmitRec(id="", slot=6, sub=None, admit=False, char="□", reading=None, channel=None,
                   doubts=["excluded"],
                   evidence={"excluded": "human:damaged", "damaged": True, "guess": "塊"})
    s = _to_slot("bxgb", 27, 8, rec, _cell(6))
    assert s.guess == "塊"
    assert render_column([s], n_raised=0, n_lead_blank=0) == "□{guess=塊}"


def test_render_column_keeps_defect_slot_in_place():
    """「舉手一揖」：手 的图块切坏进了名单，文本里要留一个阙文位，不能变成「舉一」。"""
    recs = [AdmitRec(id="", slot=19, sub=None, admit=True, char="舉", reading=None, doubts=[]),
            _excluded(20, "human:seg_defect"),
            AdmitRec(id="", slot=21, sub=None, admit=True, char="一", reading=None, doubts=[])]
    slots = [_to_slot("bxgb", 6, 7, r, _cell(r.slot)) for r in recs]
    assert render_column(slots, n_raised=0, n_lead_blank=0) == "舉[[]]一"
    slots[1] = _slot(_excluded(20, "human:not_a_char"))
    assert render_column(slots, n_raised=0, n_lead_blank=0) == "舉一"


def _excluded_with_char(slot: int, note: str, hc: str) -> AdmitRec:
    return AdmitRec(id="", slot=slot, sub=None, admit=False, char=None, reading=None,
                    channel=None, doubts=["excluded"],
                    evidence={"excluded": note, "human_char": hc})


def test_excluded_with_human_char_renders_the_char():
    """overview#403 缺口 B：名单上切坏／裁坏的格，人已给字 → 文本出人给的字，defect 照记。"""
    for note in ("human:seg_defect", "gate:crop_defect", "pipeline:crop_defect", "human:crop_defect"):
        s = _slot(_excluded_with_char(20, note, "手"))
        assert s.defect and not s.excluded and s.is_text and not s.unreadable and s.human
        assert s.char == "手"
        recs = [AdmitRec(id="", slot=19, sub=None, admit=True, char="舉", reading=None, doubts=[]),
                _excluded_with_char(20, note, "手"),
                AdmitRec(id="", slot=21, sub=None, admit=True, char="一", reading=None, doubts=[])]
        slots = [_to_slot("bxgb", 6, 7, r, _cell(r.slot)) for r in recs]
        assert render_column(slots, n_raised=0, n_lead_blank=0) == "舉手一"


import pytest  # noqa: E402
pytestmark = pytest.mark.usefixtures("seed_admit_switches_off")   # 老测试按「放行开关缺省全关」造的数据，见 conftest
