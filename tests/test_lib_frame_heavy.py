# -*- coding: utf-8 -*-
"""人裁进字形库前的带框闸 `seg_defect.lib_frame_heavy`（Sheldon 2026-11-08：带框重的字块不进字库）。数据现造。"""
from __future__ import annotations

import numpy as np

from guji_manager.review.seg_defect import lib_frame_heavy


def _char(w: int = 40, h: int = 50, pad: int = 10) -> np.ndarray:
    """白底黑字的「口」形字块：外框 w×h、笔画 4 像素，四周留 pad。"""
    img = np.full((h + 2 * pad, w + 2 * pad), 255, np.uint8)
    y0, x0 = pad, pad
    img[y0:y0 + 4, x0:x0 + w] = 0
    img[y0 + h - 4:y0 + h, x0:x0 + w] = 0
    img[y0:y0 + h, x0:x0 + 4] = 0
    img[y0:y0 + h, x0 + w - 4:x0 + w] = 0
    return img


def _framed(line_w: int = 70, gap: int = 6) -> np.ndarray:
    """同一个字（墨宽 40），字头上方隔 gap 行挂一条 3 像素粗、宽 line_w 的版框线（居中）。"""
    c = _char()
    h, w = c.shape
    W = max(w, line_w)
    img = np.full((h + gap + 3, W), 255, np.uint8)
    img[gap + 3:, (W - w) // 2:(W - w) // 2 + w] = c
    img[0:3, (W - line_w) // 2:(W - line_w) // 2 + line_w] = 0
    return img


def test_heavy_frame_blocked():
    refs = [_char() for _ in range(6)]
    f = lib_frame_heavy(_framed(), refs)
    assert f and f.startswith("列首端区")


def test_clean_char_passes():
    assert lib_frame_heavy(_char(), [_char() for _ in range(6)]) is None


def test_few_refs_admit_anyway():
    """库里同字不到 5 个：不判、照收（本书仅此一例的字不因带框缺样本）。"""
    assert lib_frame_heavy(_framed(), [_char() for _ in range(3)]) is None


def test_light_frame_not_blocked():
    """宽出不到两成（轻档）不拦。"""
    assert lib_frame_heavy(_framed(line_w=44), [_char() for _ in range(6)]) is None


def test_bottom_frame_blocked():
    f = lib_frame_heavy(_framed()[::-1].copy(), [_char() for _ in range(6)])
    assert f and f.startswith("列尾端区")


def test_consumer_gate_off_for_other_books():
    """没开带框判据的书（`_frame_on` 假）不查库、不拦。"""
    from guji_manager.feedback.consumers import _frame_heavy
    assert _frame_heavy(None, "口", _framed(), False) is None
