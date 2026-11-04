# -*- coding: utf-8 -*-
"""切线金标的页面坐标（eval/colgeom.py）：换了列窗几何也能换算到当前列图。"""
from __future__ import annotations

import pytest

from open_guji_cv.eval.colgeom import ColumnGeom, gold_rows_now, stamp
from guji_manager.gold.atomic import CUTLINE_KEYS, merge_expected


def _rec(x_left=1200.0, x_right=1020.0, slope=0.01, top=330.0, bottom=2750.0, segments=1):
    line = lambda x: {"x_at_top": x, "slope": slope, "segments": segments,
                      "k2": None, "k3": None, "y1": None, "y2": None}
    return {"left_line": line(x_left), "right_line": line(x_right), "top_y": top, "bottom_y": bottom}


def test_stamp_keys_are_replaced_as_one_group():
    """新裁决没带页面坐标（取不到几何）时，旧的 page_y 不能残留下来配新的 y。"""
    for k in ("geom_sig", "page_x", "page_y", "page_polyline"):
        assert k in CUTLINE_KEYS
    old = {"y": 100.0, "page_y": 999.0, "page_x": 1.0, "geom_sig": "abc"}
    merged = merge_expected("char-segmentation/touching-cuts", old, {"y": 120.0, "verdict": "moved"})
    assert "page_y" not in merged and merged["y"] == 120.0
