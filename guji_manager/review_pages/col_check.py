"""整列切分抽查页（col_check）：一页书一屏，各列按原书从右到左排开，每列叠上这列的格框，人点哪格切错了。

用途：切字 benchmark（A22 cut-bench）的银标（算法出的格）要人抽查才能当金标；也可用于任何「这批列切得对不对」的整列验收。
输入（一列一行）：{id(列号，如 053:76:3), vol, page, col, img(列图路径，调用者从原图裁好、缩好),
  cells:[{key(格号), kind?, box:[x0,y0,x1,y1](img 像素)}], note?, screen?(分屏键)}
同一 (vol, page) 的列排在同一屏，第 1 列在最右（古籍从右往左读）。
给了 `screen` 就按它分屏、保持输入顺序（一屏可混放不同页的列，每列标「册·页·列」；1.1.0）。
`compact: true`＋`show_w`(显示宽 px)：列图是压缩过的矮条（如上下压缩看左右切线），按图原宽显示、一屏自动换行排多列（1.2.0）。
列图请按同一页同一上下范围、同一比例裁，各列才对得齐（cut_bench.py review-items 这么做）。
结果文档：{page_type:"col_check", cell(列号), label: ok|bad|unsure, bad:[格号…](label=bad 时点了哪些格), how, t}。
how=page_ok 是「本屏其余都对」一键补的。
"""
from __future__ import annotations

import struct
from pathlib import Path

LABELS = ("ok", "bad", "unsure")
LABEL_NAMES = {"ok": "全对", "bad": "有错", "unsure": "看不出"}


def png_size(path) -> tuple[int, int]:
    b = Path(path).read_bytes()[:24]
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", b[16:24])
    raise SystemExit(f"{path} 不是 PNG（col_check 的列图请出 PNG）")


def normalize(items: list[dict], root=None) -> list[dict]:
    """补图尺寸、按 (vol, page, -col) 排好，并给出每列所在的屏号。
    `focus: true` 的列（确认页里刚修过的列）页面上加粗描边、标「请确认」，同页其余列照常显示作对照。"""
    out = []
    for r in items:
        p = Path(r["img"])
        if root and not p.exists():
            p = Path(root) / p.name
        if not p.exists():
            raise SystemExit(f"{r['id']}：列图找不到 {r['img']}")
        w, h = png_size(p)
        out.append({"id": r["id"], "vol": r.get("vol"), "page": r.get("page"), "col": r.get("col"),
                    "img": str(p), "iw": w, "ih": h, "note": r.get("note"), "focus": bool(r.get("focus")),
                    "_skey": r.get("screen"), "compact": bool(r.get("compact")), "show_w": r.get("show_w"),
                    "cells": [{"key": c["key"], "kind": c.get("kind"), "box": [float(v) for v in c["box"]]}
                              for c in r.get("cells", [])]})
    custom = any(r["_skey"] is not None for r in out)
    if not custom:
        out.sort(key=lambda r: (str(r["vol"]), _num(r["page"]), _num(r["col"])))   # 第 1 列在前，模板 row-reverse 排到最右
    screens: dict = {}
    for r in out:
        key = r.pop("_skey")
        r["screen"] = screens.setdefault(str(key) if custom else (r["vol"], r["page"]), len(screens))
        if custom:
            r["mixed"] = True
    return out


def _num(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def labels_from_docs(docs: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for d in docs:
        if d.get("page_type") != "col_check" or d.get("how") not in ("click", "page_ok") or d.get("label") not in LABELS:
            continue
        cell = d.get("cell") or d.get("id")
        if cell not in out or (d.get("t") or 0) >= (out[cell].get("t") or 0):
            out[cell] = d
    return out


def label_rows(labels: dict) -> list[dict]:
    return [{"id": i, "label": d["label"], "bad": d.get("bad") or [], "how": d.get("how"), "t": d.get("t")}
            for i, d in sorted(labels.items())]
