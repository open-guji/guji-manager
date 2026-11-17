# -*- coding: utf-8 -*-
"""整理本占位符 〓（私用码未定字）与 ▣（以图代字）：判定语义一致，成因 detail 可区分（A23 2026-11-16）。"""
from __future__ import annotations

import pytest

from guji_manager.review.causes import cause_of
from guji_manager.review.reasons import ref_missing
from guji_manager.taxonomy import _MISSING_REF


def _ch(char="甲"):
    return {"id": "v:1:1:1", "admit": False, "char": char, "doubts": [], "evidence": {}}


@pytest.mark.parametrize("g", ["〓", "▣"])
def test_ref_missing_accepts_both_gaps(g):
    assert ref_missing(g)
    assert g in _MISSING_REF


def test_cause_detail_marks_image():
    assert cause_of(_ch(), {"align_char": "〓"}, None, None) == ("A2", "")
    assert cause_of(_ch(), {"align_char": "▣"}, None, None) == ("A2", "image")


def test_ordinary_char_is_not_missing():
    assert not ref_missing("字")
