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


# ---- 难认字页：整列图（本格红框）＋左右邻列图＋同列上下文（1.6 起 char_card 缺省带） ----

def _col_boxes(shrink_json) -> dict[int, list[tuple[str, list]]]:
    """页内 {列号: [(格号, bbox_page), …]}（按格序）。"""
    d = json.loads(Path(shrink_json).read_text(encoding="utf-8"))
    cols = (d.get("char_index") or d.get("cell_shrink", {}).get("char_index") or {}).get("columns", [])
    return {c["col"]: [(x["id"], x.get("bbox_page")) for x in c.get("chars", []) if x.get("bbox_page")] for c in cols}


def _col_union(boxes: list[tuple[str, list]], pad: int):
    x0 = min(b[0] for _, b in boxes); y0 = min(b[1] for _, b in boxes)
    x1 = max(b[2] for _, b in boxes); y1 = max(b[3] for _, b in boxes)
    return [x0, y0, x1, y1], pad


def column_images(ids, shrink_dir: str, pages_dir: str, out_dir, page_name: str = "{page}.png",
                  pad: int = 12, ctx_n: int = 8, pack_dir: str | None = None, max_h: int = 700) -> dict:
    """对每格出：<格号>_col.png（整列，本格红框）、_nbr.png／_nbl.png（右列、左列整列图）、同列 ±ctx_n 格的上下文字串。

    ctx 取包里 seed_admit 的机器字（pack_dir 用 {vol} 占位，缺则只出图）；本格用【】括起、机器没定的字写「？」。
    返回 {格号: {"col_img", "nb_imgs":[{"img","label"}], "ctx"}}，可直接并进 char_card 的 items。
    """
    from PIL import Image, ImageDraw
    Image.MAX_IMAGE_PIXELS = None
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    res: dict[str, dict] = {}
    by_page: dict[tuple[str, int], list[str]] = defaultdict(list)
    for i in ids:
        v, p = i.split(":")[:2]
        by_page[(v, int(p))].append(i)

    def shrink(im, maxh):
        if im.height <= maxh:
            return im
        return im.resize((max(1, int(im.width * maxh / im.height)), maxh))

    for (v, p), cs in sorted(by_page.items()):
        sj = Path(_fmt(shrink_dir, v, p)) / f"p{p:04d}.json"
        pg = Path(_fmt(pages_dir, v, p)) / _fmt(page_name, v, p)
        if not sj.exists() or not pg.exists():
            continue
        cols = _col_boxes(sj)
        im = Image.open(pg).convert("RGB")
        chars: dict[str, str] = {}
        if pack_dir:
            sa = Path(_fmt(pack_dir, v, p)) / "seed_admit" / f"p{p:04d}.json"
            if sa.exists():
                for col in json.loads(sa.read_text(encoding="utf-8"))["seed_admit"]["columns"]:
                    for c in col["chars"]:
                        chars[c["id"]] = c.get("char") or ""

        refc: dict[str, str] = {}
        if pack_dir:
            ar = Path(_fmt(pack_dir, v, p)) / "align_ref" / f"p{p:04d}.json"
            if ar.exists():
                for c in json.loads(ar.read_text(encoding="utf-8")).get("align_ref", {}).get("chars", []):
                    refc[c["id"]] = c.get("align_char") or ""

        def col_img(cn, mark=None):
            bx = cols.get(cn)
            if not bx:
                return None
            ub, _ = _col_union(bx, pad)
            box = to_image_box(ub, im.width, pad)
            cr = im.crop(box)
            if mark:
                b = dict(bx).get(mark)
                if b:
                    l, t, r, btm = to_image_box(b, im.width, 0)
                    d = ImageDraw.Draw(cr)
                    d.rectangle([l - box[0] - 2, t - box[1] - 2, r - box[0] + 2, btm - box[1] + 2], outline=(220, 30, 30), width=3)
            return shrink(cr, max_h)

        for i in cs:
            col = int(i.split(":")[2])
            r: dict = {}
            c_img = col_img(col, i)
            if c_img:
                f = out / (i.replace(":", "_") + "_col.png"); c_img.save(f); r["col_img"] = str(f)
            nb = []
            for dc, lab, tag in ((-1, "右邻列（先读）", "nbr"), (1, "左邻列（后读）", "nbl")):
                ni = col_img(col + dc)
                if ni:
                    f = out / (i.replace(":", "_") + f"_{tag}.png"); ni.save(f); nb.append({"img": str(f), "label": lab})
            if nb:
                r["nb_imgs"] = nb
            seq = [k for k, _ in cols.get(col, [])]
            if chars and i in seq:
                j = seq.index(i)
                a, b = seq[max(0, j - ctx_n):j], seq[j + 1:j + 1 + ctx_n]
                tx = lambda ks: "".join((chars.get(k) or "？") for k in ks)
                r["ctx"] = f"机器：{tx(a)}【】{tx(b)}"
                if refc:
                    rx = lambda ks: "".join((refc.get(k) or "？") for k in ks)
                    r["ctx"] += f" ｜ 整理本：{rx(a)}【{refc.get(i) or '？'}】{rx(b)}"
            res[i] = r
    return res
