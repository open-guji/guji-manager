"""审页图：按 cell_shrink 的字框裁（不按 row_segment 的 quad 裁）。

quad 是行切分给的列内格，左右常带进栏线、上下带进邻字，人看了会当成切分有问题；
cell_shrink 收紧后的 `char_index.columns[].chars[].bbox_page` 才是字本身。
bbox_page 是右上角原点（x 从右往左数）：x_img = W − 1 − x。

格号 `<册>:<页>:<列>:<序>`；页图、cell_shrink 文件按册号与页号找，路径模板可用 {vol} {page} {page4}。
需要 Pillow（只在裁图时导入）。
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def to_image_box(bbox_page, width: int, pad: int = 0) -> tuple[int, int, int, int]:
    """右上角原点的 [x0, y0, x1, y1] → PIL crop 用的 (left, top, right, bottom)。"""
    x0, y0, x1, y1 = bbox_page
    left, right = int(width - 1 - x1), int(width - 1 - x0) + 1
    return max(0, left - pad), max(0, int(y0) - pad), min(width, right + pad), int(y1) + 1 + pad


def _fmt(tpl: str, vol: str, page: int) -> str:
    return tpl.format(vol=vol, page=page, page4=f"{page:04d}")


def load_boxes(shrink_json) -> dict[str, list]:
    d = json.loads(Path(shrink_json).read_text(encoding="utf-8"))
    cols = (d.get("char_index") or d.get("cell_shrink", {}).get("char_index") or {}).get("columns", [])
    return {c["id"]: c.get("bbox_page") for col in cols for c in col.get("chars", [])}


def crop_cells(ids, shrink_dir: str, pages_dir: str, out_dir, page_name: str = "{page}.png",
               pad: int = 0) -> dict:
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    by_page: dict[tuple[str, int], list[str]] = defaultdict(list)
    for i in ids:
        v, p = i.split(":")[:2]
        by_page[(v, int(p))].append(i)
    ok, missing = [], []
    for (v, p), cs in sorted(by_page.items()):
        sj = Path(_fmt(shrink_dir, v, p)) / f"p{p:04d}.json"
        pg = Path(_fmt(pages_dir, v, p)) / _fmt(page_name, v, p)
        if not sj.exists() or not pg.exists():
            missing += cs
            continue
        boxes = load_boxes(sj)
        im = Image.open(pg).convert("L")
        for i in cs:
            b = boxes.get(i)
            if not b:
                missing.append(i)
                continue
            f = out / (i.replace(":", "_") + ".png")
            im.crop(to_image_box(b, im.width, pad)).save(f)
            ok.append(str(f))
    return {"ok": ok, "missing": missing}
