"""人裁切线页（seg_cut）：两套格网都切错、几个小字被并成一格时，给人看一段列图，点哪里该切开。

输入（一格一行）：{id, vol?, page?, col?, column_image(路径，--root 下按文件名找), box_shows?, expect_chars?, note?,
  grids:{main:[{id, slot, sub, bbox_col:[x0,y0,x1,y1], bbox_page:[…]}…], alt:[…]?}}
bbox_col 是列图像素坐标；切线 y 也用列图像素坐标存，另按 bbox_page 的线性关系换算成页图坐标。
结果文档：{page_type:"seg_cut", cell, label:"cut", cuts:[{d:v|h, p}…]（列图像素；竖线 p 是 x，横线 p 是 y）, cuts_page:同形页图坐标, how, t}。
2.0.0 起只有「点哪里切」一个动作：默认竖切（双行夹注小字左右并排），可切到横切。
"""
from __future__ import annotations

import struct
from pathlib import Path

LABELS = ("cut", "keep", "unsure")
PAD = 30   # 目标格四周各多看多少列图像素


def png_size(path) -> tuple[int, int]:
    b = Path(path).read_bytes()[:24]
    if b[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"{path} 不是 PNG")
    return struct.unpack(">II", b[16:24])


def target_boxes(row: dict) -> list[list[float]]:
    return [g["bbox_col"] for k in ("main", "alt") for g in (row.get("grids") or {}).get(k, []) if g["id"] == row["id"]]


def page_map(row: dict):
    """列图 → 页图的线性换算 (ky, cy, kx, cx)：页 y = 列 y*ky+cy，页 x = 列 x*kx+cx；取格框最大的一格。"""
    best = None
    for k in ("main", "alt"):
        for g in (row.get("grids") or {}).get(k, []):
            c, p = g["bbox_col"], g["bbox_page"]
            if c[3] - c[1] > 20 and c[2] - c[0] > 20 and (best is None or c[3] - c[1] > best[0]):
                ky, kx = (p[3] - p[1]) / (c[3] - c[1]), (p[2] - p[0]) / (c[2] - c[0])
                best = (c[3] - c[1], ky, p[1] - c[1] * ky, kx, p[0] - c[0] * kx)
    return best[1:] if best else (1.0, 0.0, 1.0, 0.0)


def normalize(items: list[dict], root=None) -> list[dict]:
    out = []
    for r in items:
        f = r.get("column_image") or ""
        p = Path(f)
        if root and not p.exists():
            p = Path(root) / p.name
        if not p.exists():
            raise SystemExit(f"{r['id']}：列图找不到 {f}（用 --root 指到放列图的目录）")
        w, h = png_size(p)
        tb = target_boxes(r)
        y0, y1 = (min(b[1] for b in tb), max(b[3] for b in tb)) if tb else (0, h)
        x0, x1 = (min(b[0] for b in tb), max(b[2] for b in tb)) if tb else (0, w)
        wy0, wy1 = max(0.0, y0 - PAD), min(float(h), y1 + PAD)
        wx0, wx1 = max(0.0, x0 - PAD), min(float(w), x1 + PAD)
        ky, cy, kx, cx = page_map(r)
        out.append({"id": r["id"], "vol": r.get("vol"), "page": r.get("page"), "col": r.get("col"), "img": str(p),
                    "iw": w, "ih": h, "wy0": wy0, "wy1": wy1, "wx0": wx0, "wx1": wx1,
                    "tbox": [[b[0], b[1], b[2], b[3]] for b in tb], "ky": ky, "cy": cy, "kx": kx, "cx": cx,
                    "shows": r.get("box_shows"), "expect": r.get("expect_chars") or [], "note": r.get("note")})
    return out


def labels_from_docs(docs: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for d in docs:
        if d.get("page_type") != "seg_cut" or d.get("how") not in ("click", "page_ok") or d.get("label") not in LABELS:
            continue
        cell = d.get("cell") or d.get("id")
        if cell not in out or (d.get("t") or 0) >= (out[cell].get("t") or 0):
            out[cell] = d
    return out


def label_rows(labels: dict) -> list[dict]:
    return [{"id": i, "label": d["label"], "cuts_col": d.get("cuts") or [], "cuts_page": d.get("cuts_page") or [],
             "t": d.get("t")} for i, d in sorted(labels.items())]   # cuts: [{d:"v"|"h", p:坐标}]，v＝竖线（p 是 x），h＝横线（p 是 y）
