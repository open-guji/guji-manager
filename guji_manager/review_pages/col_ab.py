"""切分 A/B 对比的整列抽查 items（col_check 页型的输入）：新切法画格框，旧切法被换掉的线画红线，只收两份产物切得不一样的列。

用途：改了切字算法（比如 row_segment 的字间界线判官 `boundary_net`）后，让人看「动过的列」新切法对不对。
输入两份 row_segment 产物（同一册、同一批页），原页图目录。只比正文格（kind 不是 blank）。
`--flag` 给了就只收新产物里带这个 flag 前缀的列（判官改过的列都打 `boundary_net：…`）；不给就收格的上下沿有任何一处差 >tol 的列。

    guji-manager review-pages ab-items --old <旧产物根>/<册> --new <新产物根>/<册> --pages-dir <原图目录> \\
        --out-dir D [--flag boundary_net] [--vol-name 史記·42]
    guji-manager review-pages build col_check --items D/items.jsonl --book <页名> --out page.html
结果照常 `colcheck-apply` 收：点了的格＝新切法在这里切错。
"""
from __future__ import annotations

import json
from pathlib import Path

MAX_H = 1100     # 列图最高（像素，超了等比缩小）
PAD = 14         # 列图左右留白
Y_PAD = 40       # 上下留白
TOL = 3          # 线差几像素以内算同一条


def _box(q) -> tuple[float, float, float, float]:
    xs = [p[0] for p in q]; ys = [p[1] for p in q]
    return min(xs), min(ys), max(xs), max(ys)


def _cols(vol_dir: Path, page: int) -> dict:
    f = vol_dir / "row_segment" / f"p{page:04d}.json"
    if not f.exists():
        return {}
    d = json.loads(f.read_text(encoding="utf-8"))["cells"]
    return {c["col"]: c for c in d["columns"]}


def _body(col: dict | None) -> list[dict]:
    return [c for c in (col or {}).get("cells", []) if c.get("kind") not in ("blank", None)]


def _edges(cells: list[dict]) -> list[float]:
    return sorted(y for c in cells for y in _box(c["quad_page"])[1::2])


def changed(old: dict | None, new: dict | None, flag: str | None) -> bool:
    if new is None:
        return False
    if flag:
        return any(str(f).startswith(flag) for f in new.get("flags", []))
    a, b = _edges(_body(old)), _edges(_body(new))
    return len(a) != len(b) or any(abs(x - y) > TOL for x, y in zip(a, b))


def build_items(old_dir, new_dir, pages_dir, out_dir, flag: str | None = None, vol_name: str | None = None,
                page_name: str = "{page}.png") -> list[dict]:
    from PIL import Image, ImageDraw
    Image.MAX_IMAGE_PIXELS = None
    old_dir, new_dir, out = Path(old_dir), Path(new_dir), Path(out_dir)
    (out / "img").mkdir(parents=True, exist_ok=True)
    vol = new_dir.name
    items = []
    for f in sorted((new_dir / "row_segment").glob("p*.json")):
        page = int(f.stem[1:])
        nc, oc = _cols(new_dir, page), _cols(old_dir, page)
        moved = [k for k in sorted(nc) if changed(oc.get(k), nc[k], flag)]
        if not moved:
            continue
        pg = Path(pages_dir) / page_name.format(page=page, page4=f"{page:04d}", vol=vol)
        im = Image.open(pg).convert("L")
        W, H = im.size
        allb = [_box(c["quad_page"]) for col in nc.values() for c in _body(col)]
        y0 = max(0, int(min(b[1] for b in allb)) - Y_PAD); y1 = min(H, int(max(b[3] for b in allb)) + Y_PAD)
        k = min(1.0, MAX_H / (y1 - y0))
        for col in moved:
            nb, ob = _body(nc[col]), _body(oc.get(col))
            # quad_page 是右上原点：x 翻成左上原点
            bs = [(W - _box(c["quad_page"])[2], _box(c["quad_page"])[1], W - _box(c["quad_page"])[0], _box(c["quad_page"])[3])
                  for c in nb]
            x0 = max(0, int(min(b[0] for b in bs)) - PAD); x1 = min(W, int(max(b[2] for b in bs)) + PAD)
            crop = im.crop((x0, y0, x1, y1)).convert("RGB")
            dr = ImageDraw.Draw(crop)
            newy = [y for b in bs for y in (b[1], b[3])]
            n_red = 0
            for y in sorted({round(y) for y in _edges(ob)}):   # 相邻两格共用的线只画一次
                if not newy or min(abs(y - n) for n in newy) > TOL:
                    yy = int(round(y - y0)); dr.line([(0, yy), (crop.width - 1, yy)], fill=(230, 0, 0), width=2)
                    n_red += 1
            if k < 1:
                crop = crop.resize((max(1, round(crop.width * k)), max(1, round(crop.height * k))), Image.LANCZOS)
            cid = f"{vol}:{page}:{col}"
            fn = out / "img" / (cid.replace(":", "_") + ".png")
            crop.save(fn)
            cells = [{"key": f"{cid}:{c['slot']}" + (f":{c['sub']}" if c.get("sub") else ""), "kind": c.get("kind"),
                      "box": [round((b[0] - x0) * k, 1), round((b[1] - y0) * k, 1),
                              round((b[2] - x0) * k, 1), round((b[3] - y0) * k, 1)]}
                     for c, b in zip(nb, bs)]
            items.append({"id": cid, "vol": vol_name or vol, "page": page, "col": col, "img": str(fn),
                          "cells": cells, "focus": True,
                          "note": f"框＝新切法｜红线＝旧切法被换掉的线（{n_red} 条）｜框切错的格请点"})
    with open(out / "items.jsonl", "w", encoding="utf-8") as fh:
        for r in items:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return items
