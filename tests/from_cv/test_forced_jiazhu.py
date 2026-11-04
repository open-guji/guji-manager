# -*- coding: utf-8 -*-
"""人裁「小注当正文」→ Step3 强制按雙行小注从中间拆（2026-09-30）。

提要末尾 2~3 行的短版本小注，判据（`jiazhu_split.gap_center`）常落空：缝只有 2px、缝偏出窗口、
搭档量不出缝凑不成段。人指认的格不看判据直接拆。"""
from __future__ import annotations

import numpy as np

from open_guji_cv.books.siku_zongmu import jiazhu_split as jz
from open_guji_cv.books.siku_zongmu import row_boundaries as fit_mod

COL_W, SLOT_H, N_SLOTS, GRID_Y0, RULE_W = 185, 110, 21, 10, 4


def _column(thin_seam_slots=(), seam_x=98, seam_w=2, tail_slots=()):
    """正文列；`thin_seam_slots` 里的格画成两个小字、中缝只有 `seam_w`px（< GAP_MIN，判据认不出）。"""
    h = GRID_Y0 + N_SLOTS * SLOT_H + 20
    img = np.full((h, COL_W), 255, dtype=np.uint8)
    img[:, :RULE_W] = 0
    img[:, -RULE_W:] = 0
    img[0:4, :] = 0
    img[h - 4:, :] = 0
    for k in range(N_SLOTS):
        y0 = GRID_Y0 + k * SLOT_H + 10
        y1 = y0 + 90
        if (k + 1) in tail_slots:                      # 奇数字末行：只有右半一个小字
            img[y0:y1, 110:COL_W - 15] = 0
        elif (k + 1) in thin_seam_slots:
            img[y0:y1, 15:seam_x] = 0
            img[y0:y1, seam_x + seam_w:COL_W - 15] = 0
        else:
            img[y0:y1, 37:148] = 0
    return img


def _cells(r):
    out = {}
    for c in r.cells:
        out.setdefault(c.slot, {})[c.sub or ""] = c
    return out


# ── 数据源：事件日志里最新一条定字裁决是 seg_defect+reason=jiazhu_as_main ──

def _ev(batch, seq, key, payload, ts):
    from open_guji_cv.feedback.events import EventTarget, make_event
    _, pg, col, slot = key.split(":")
    e = make_event(batch, seq, "confirm",
                   EventTarget(step="seed_admit", unit="cell", key=key, book="vol01",
                               page=int(pg), col=int(col), slot=0), payload, source_format="server")
    e.ts = ts
    return e


def test_route_invalidates_row_segment_for_jiazhu_marks():
    from guji_manager.feedback.routes import RouteTable
    table = RouteTable.load(None)
    jzp = {"v": "seg_defect", "quality": "truncated", "reason": "jiazhu_as_main"}
    steps = lambda p: sorted((d.extra or {}).get("step") or d.consumer
                             for d in table.destinations(_ev("b", 1, "vol01:12:7:9", p, "2026-10-01T00:00:01Z")))
    assert "row_segment" in steps(jzp)
    assert "row_segment" not in steps({"v": "seg_defect", "quality": "truncated"})


