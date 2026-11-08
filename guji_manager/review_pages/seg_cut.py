"""人裁切线页（seg_cut）：两套格网都切错、几个小字被并成一格时，给人看一段列图，点哪里该切开。

输入（一格一行）：{id, vol?, page?, col?, column_image(路径，--root 下按文件名找), box_shows?, expect_chars?, note?,
  grids:{main:[{id, slot, sub, bbox_col:[x0,y0,x1,y1], bbox_page:[…]}…], alt:[…]?}}
bbox_col 是列图像素坐标；切线 y 也用列图像素坐标存，另按 bbox_page 的线性关系换算成页图坐标。
结果文档：{page_type:"seg_cut", cell, v: cut|keep|unsure, cuts:[列图 y…], cuts_page:[页图 y…], how, t}。
"""
from __future__ import annotations

import struct
from pathlib import Path

LABELS = ("cut", "keep", "unsure")
PAD = 90   # 目标格上下各多看多少列图像素


def png_size(path) -> tuple[int, int]:
    b = Path(path).read_bytes()[:24]
    if b[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"{path} 不是 PNG")
    return struct.unpack(">II", b[16:24])


def target_boxes(row: dict) -> list[list[float]]:
    return [g["bbox_col"] for k in ("main", "alt") for g in (row.get("grids") or {}).get(k, []) if g["id"] == row["id"]]


def page_map(row: dict):
    """列图 y → 页图 y 的 (斜率, 截距)；取格框里 y 跨度最大的一格。"""
    best = None
    for k in ("main", "alt"):
        for g in (row.get("grids") or {}).get(k, []):
            c, p = g["bbox_col"], g["bbox_page"]
            if c[3] - c[1] > 20 and (best is None or c[3] - c[1] > best[0]):
                best = (c[3] - c[1], (p[3] - p[1]) / (c[3] - c[1]), p[1] - c[1] * (p[3] - p[1]) / (c[3] - c[1]))
    return (best[1], best[2]) if best else (1.0, 0.0)


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
        wy0, wy1 = max(0.0, y0 - PAD), min(float(h), y1 + PAD)
        k, c = page_map(r)
        grids = {n: [[g["bbox_col"][1], g["bbox_col"][3], g["id"]] for g in (r.get("grids") or {}).get(n, [])
                     if g["bbox_col"][3] >= wy0 and g["bbox_col"][1] <= wy1] for n in ("main", "alt")}
        out.append({"id": r["id"], "vol": r.get("vol"), "page": r.get("page"), "col": r.get("col"), "img": str(p),
                    "iw": w, "ih": h, "wy0": wy0, "wy1": wy1,
                    "tbox": [[b[0], b[1], b[2], b[3]] for b in tb], "grids": grids, "k": k, "c": c,
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
             "t": d.get("t")} for i, d in sorted(labels.items())]
