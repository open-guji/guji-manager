"""裁图几何特征：判「切得干不干净」，与字对不对无关。

史記第 1 轮被拦的格，大多字本身没错，是图块里混进了版框横线、邻格笔画、碎点、灰糊底纹。
这些只看图块就量得出来。`edge_frame_line` 与 cv `open_guji_cv/clustering/patch_qc.py` 同判据
（manager 不 import cv 内部，所以在这里留一份；改判据两边一起改）。
"""
from __future__ import annotations

import cv2
import numpy as np

THR = 128

# 顶/底残留框线判据（史記第 1 轮：命中被拦 47/323，误中放行 1/2797）
EDGE_ZONE, EDGE_MIN_GAP_PX = 0.3, 2
LINE_MIN_ASPECT, LINE_MIN_SPAN, LINE_MAX_THICK = 3.3, 0.35, 0.13
LINE_MIN_GAP, LINE_WIDE_BODY, LINE_WIDE_THICK = 0.09, 1.15, 0.08


def _band(ink: np.ndarray) -> dict | None:
    """从上边往里第一段墨带（后面隔着空白才是字身）；没有就 None。"""
    h, w = ink.shape
    occ = ink.any(axis=1)
    if not occ.any():
        return None
    y0 = int(np.argmax(occ)); y = y0
    while y < h and occ[y]:
        y += 1
    y1 = y
    while y < h and not occ[y]:
        y += 1
    gap = y - y1
    if y >= h or gap < EDGE_MIN_GAP_PX or y1 > EDGE_ZONE * h:
        return None
    cols = np.flatnonzero(ink[y0:y1].any(axis=0))
    bcols = np.flatnonzero(ink[y:].any(axis=0))
    bw, bh = int(cols[-1] - cols[0] + 1), y1 - y0
    return dict(thick=bh / h, gap=gap / h, span=bw / w, aspect=bw / bh,
                body_ratio=bw / int(bcols[-1] - bcols[0] + 1))


def _is_line(b: dict | None) -> bool:
    if not b or not (b["aspect"] >= LINE_MIN_ASPECT and b["span"] >= LINE_MIN_SPAN
                     and b["thick"] <= LINE_MAX_THICK):
        return False
    return b["gap"] >= LINE_MIN_GAP or (b["body_ratio"] >= LINE_WIDE_BODY and b["thick"] <= LINE_WIDE_THICK)


def edge_frame_line(gray: np.ndarray) -> list[str]:
    """图块顶/底残留的版框／界栏横线：返回命中的边（"top"/"bottom"）。"""
    ink = gray < THR
    return [s for s, m in (("top", ink), ("bottom", ink[::-1])) if _is_line(_band(m))]


def features(gray: np.ndarray) -> dict[str, float]:
    """一组数值特征（顺序固定，见 FEATURE_NAMES）。"""
    h, w = gray.shape
    b = gray < THR
    tot = int(b.sum()) + 1
    n, lab, st, _ = cv2.connectedComponentsWithStats(b.astype(np.uint8), 8)
    areas = st[1:, 4] if n > 1 else np.array([0])
    order = np.argsort(-areas)
    f = {"h": h, "w": w, "ar": w / h, "ink": float(b.mean()),
         "ncc": float((areas >= 0.02 * tot).sum()), "ncc_all": float(n - 1),
         "big_frac": float(areas[order[0]] / tot) if n > 1 else 0.0,
         "second_frac": float(areas[order[1]] / tot) if n > 2 else 0.0,
         "edge_top": float(b[:3].mean()), "edge_bot": float(b[-3:].mean()),
         "edge_lef": float(b[:, :3].mean()), "edge_rig": float(b[:, -3:].mean()),
         "specks": float((areas <= 6).sum()) if n > 1 else 0.0,
         "gray_frac": float(((gray > 60) & (gray < 190)).sum() / max(1, (gray < 190).sum()))}
    if n > 1:
        i = order[0] + 1
        x, y, ww, hh = (int(v) for v in st[i, :4])
        out = b.copy(); out[y:y + hh, x:x + ww] = False
        border = sum(int(st[j, 4]) for j in range(1, n) if j != i and st[j, 4] >= 8 and
                     (st[j, 0] == 0 or st[j, 1] == 0 or st[j, 0] + st[j, 2] >= w or st[j, 1] + st[j, 3] >= h))
        f.update(mx0=x / w, mx1=(x + ww) / w, my0=y / h, my1=(y + hh) / h, mbw=ww / w, mbh=hh / h,
                 out_frac=float(out.sum() / tot), other_border=border / tot,
                 hrule=max([st[j, 2] / w for j in range(1, n) if st[j, 3] <= 0.12 * h and st[j, 2] >= 0.5 * w] + [0.0]))
    else:
        f.update(mx0=0, mx1=0, my0=0, my1=0, mbw=0, mbh=0, out_frac=0, other_border=0, hrule=0)
    lines = edge_frame_line(gray)
    f["frame_top"] = float("top" in lines)
    f["frame_bot"] = float("bottom" in lines)
    return {k: float(v) for k, v in f.items()}


FEATURE_NAMES = list(features(np.full((40, 40), 255, np.uint8)).keys())


def read_gray(path) -> np.ndarray:
    g = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if g is None:
        raise FileNotFoundError(path)
    return g
