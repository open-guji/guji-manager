# -*- coding: utf-8 -*-
"""夹注段尾：Step3 与 Step4 格位口径统一（overview#436）。

1. Step4 extractor 拿到 `jiazhu_authority=step3` 时，**拆哪几格、每格发哪几半**一律照 Step3：
   Step3 没拆的格不拆（#434：v1 段端收编在清理后图块上又把整格拆成 a/b），Step3 只发 a 半的格不发 b。
2. 反向人裁「正文当小注」（`forced_main`）：人指认的格从夹注段里摘掉、按整格出（#415 vol02 p100c4「此」），
   数据源 `lookup.resolved_forced_main`（收 `…a`/`…b` 子格 key），路由让该页 Step3 失效。

合成列图，几何按四库：列宽 180、字距 115。"""

from __future__ import annotations

import numpy as np

from open_guji_cv.clustering.extractor import CharExtractor
from open_guji_cv.books.siku_zongmu import row_boundaries as fit_mod

W, P = 180, 115.0
SEAM = 90


def _small_pair(img, y, seam=SEAM, left=True, right=True):
    """一行雙行小注：缝左右各一个小字（横 + 竖 + 横），缝宽 12px。"""
    for on, (x0, x1) in ((left, (8, seam - 6)), (right, (seam + 6, W - 8))):
        if not on:
            continue
        img[y + 20:y + 27, x0:x1] = 0
        img[y + 15:y + 98, (x0 + x1) // 2 - 3:(x0 + x1) // 2 + 3] = 0
        img[y + 60:y + 67, x0 + 4:x1 - 4] = 0


def _ext_column():
    """5 格：0 正文；1–3 雙行小注（缝对齐）；4 是段尾一行两个小字（v1 段端收编会拆成 a/b）。"""
    img = np.full((6 * int(P) + 40, W), 255, np.uint8)
    y = 20
    img[y + 20:y + 28, 36:144] = 0
    img[y + 10:y + 100, 86:94] = 0
    for k in (1, 2, 3, 4):
        _small_pair(img, 20 + k * int(P))
    return img


def _grid(step3: dict[int, list[str]], authority: bool):
    cells = []
    for k in range(6):
        c = {"type": "char" if k < 5 else "empty", "index": k, "y_top": 20 + k * P,
             "y_bottom": 20 + (k + 1) * P, "is_punct": False, "seam_top": None, "seam_bottom": None}
        if k in step3:
            c.update(jiazhu_cx=float(SEAM), jiazhu_tail_a="b" not in step3[k], jiazhu_subs=step3[k])
        cells.append(c)
    g = {"shear": 0.0, "period": float(W), "cell_h": P, "head_raise_rows": 0,
         "frame_top": None, "frame_bottom": None, "frame_bar_strategy": "side_gap"}
    if authority:
        g["jiazhu_authority"] = "step3"
    return {"image_size": [W, 6 * int(P) + 40], "chars_per_line": 6, "grid": g,
            "columns": [{"index": 1, "left_x": 0.0, "right_x": float(W),
                         "cell_left_x": 0.0, "cell_right_x": float(W), "cells": cells}]}


def _subs(res):
    out: dict[int, set] = {}
    for inst, _p in res:
        out.setdefault(int(inst.idx), set()).add(inst.sub)
    return out


S3_RUN = {1: ["a", "b"], 2: ["a", "b"], 3: ["a", "b"]}


# ── Step3：反向人裁「正文当小注」────────────────────────────────

N, Y0 = 12, 10


def _seg_column():
    """12 格：1–2 正文；3–7 雙行小注；8 是被小注段吞进去的「整宽正文」——两笔分在缝两侧、
    几何上与小注行分不开（#415「此」：左右结构字恰好在缝位有空隙）；9–12 正文。"""
    h = Y0 + N * int(P) + 20
    img = np.full((h, W), 255, np.uint8)
    img[:, :4] = 0
    img[:, -4:] = 0
    for k in range(N):
        y = Y0 + k * int(P)
        if 3 <= k + 1 <= 8:
            _small_pair(img, y)
        else:
            img[y + 20:y + 28, 36:144] = 0
            img[y + 10:y + 100, 86:94] = 0
    return img


def _cells(r):
    out: dict[int, dict] = {}
    for c in r.cells:
        out.setdefault(c.slot, {})[c.sub or ""] = c
    return out


def _seg(**kw):
    return fit_mod.segment_column(_seg_column(), period=P, n_body_slots=N, ref_w=W, seam_band=0, **kw)


# ── 数据源 / 路由 / Step8 勾选 ──────────────────────────────────

def _ev(seq, key, payload, ts):
    from open_guji_cv.feedback.events import EventTarget, make_event
    _, pg, col, _slot = key.split(":")
    e = make_event("b", seq, "confirm",
                   EventTarget(step="seed_admit", unit="cell", key=key, book="vol02",
                               page=int(pg), col=int(col), slot=0), payload, source_format="server")
    e.ts = ts
    return e


MAIN = {"v": "seg_defect", "quality": "truncated", "reason": "main_as_jiazhu"}


def test_step8_main_flag_payload_and_readback():
    from guji_manager.feedback.collate_state import seg_flags, seg_payload
    p = seg_payload(["main"])
    assert p["reason"] == "main_as_jiazhu" and p["quality"] == "truncated" and p["defect"] == "main"
    both = seg_payload(["jiazhu", "main"])
    assert both["reason"] == "main_as_jiazhu"                              # 两个都勾以「正文当小注」为准
    e = _ev(1, "vol02:100:4:17a", p, "2026-10-06T00:00:01Z")
    assert seg_flags([e], "vol02") == {"vol02:100:4:17a": ["main"]}       # quality=truncated 不读成「字形不完整」
