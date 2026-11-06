"""整理本真错复核页（页型 `ref_check`）：疑整理本错的格排最前，快速确认「整理本字对不对」。

A32 D01／L02／X01 深挖（2026-11-06）的结论：整理本真错率稳定在 3–6%，规则不能放宽，只能让人审更快、真错先被看到。
本页是 cell_pick 的核对模式（`gold_sample` mode=check）加三件事：
  1. 预选整理本字；库首位并排，一键「改作库首位」；
  2. 按 `ref_suspect` 排序：ref（疑整理本错，库首位在整理本上下文里更通顺）排最前，其次未标，lib（疑库错）排后；
  3. 每格带横向邻格条（左右各 2 格字块，目标格红框）和整理本前后文，看专名、套语最快。

输入 cells（jsonl／tsv 皆可，字段）：id（册:页:列:序，可带 volNN: 前缀）、ref（整理本字）、lib（库首位，可空）、
ref_suspect（ref|lib|空，pending-stats／待审单的 `ref_suspect`）、left／right（整理本前后文，可空）、kind（pending_reason，页内筛选）、
cov（库首位覆盖度，可空）。
裁图按 cell_shrink 字框（`crop.py` 同一口径）。图需 Pillow。
结果 `ref-check-apply`：改字的格 → tsv（格号、旧字、新字、备注），喂给 book-text 的改字流程（char_edits record/sync/bump）。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import crop as crop_mod

ORDER = {"ref": 0, "": 1, None: 1, "lib": 2}
SUSPECT_NAME = {"ref": "疑整理本错", "lib": "疑库错", "": "未标", None: "未标"}


def _vol_prefix(cid: str, default_vol: str | None) -> tuple[str, str]:
    """→ (vol 名如 vol08, 册内格号 页:列:序)。"""
    parts = cid.split(":")
    if parts[0].startswith("vol"):
        return "vol%02d" % int(parts[0][3:]), ":".join(parts[1:])
    if len(parts) == 4:
        return "vol%02d" % int(parts[0]), ":".join(parts[1:])
    if default_vol:
        return default_vol, cid
    raise ValueError(f"格号要带册：{cid}")


def _column(boxes_cols: list, cid: str):
    for col in boxes_cols:
        ids = [c["id"] for c in col.get("chars", [])]
        if cid in ids:
            return col["chars"], ids.index(cid)
    return None, None


def build_items(cells: list[dict], shrink_dir: str, pages_dir: str, out_dir, page_name: str = "{page}.png",
                strip_n: int = 2, pad: int = 3, default_vol: str | None = None) -> tuple[list[dict], list[str]]:
    """→ (items, 缺图的格号)。shrink_dir／pages_dir 可用 {vol}（volNN）{page} {page4}。"""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    items, missing = [], []
    for c in cells:
        vol, key = _vol_prefix(str(c["id"]), default_vol)
        page = int(key.split(":")[0])
        sj = Path(crop_mod._fmt(shrink_dir, vol, page)) / f"p{page:04d}.json"
        pg = Path(crop_mod._fmt(pages_dir, vol, page)) / crop_mod._fmt(page_name, vol, page)
        full = f"{vol}:{key}"
        if not sj.exists() or not pg.exists():
            missing.append(full)
            continue
        d = json.loads(sj.read_text(encoding="utf-8"))
        cols = (d.get("char_index") or d.get("cell_shrink", {}).get("char_index") or {}).get("columns", [])
        chars, at = _column(cols, full)
        if chars is None or not chars[at].get("bbox_page"):
            missing.append(full)
            continue
        im = Image.open(pg).convert("L")
        f = out / (full.replace(":", "_") + ".png")
        im.crop(crop_mod.to_image_box(chars[at]["bbox_page"], im.width, pad)).save(f)
        strip, strip_at = [], 0
        for j in range(max(0, at - strip_n), min(len(chars), at + strip_n + 1)):
            b = chars[j].get("bbox_page")
            if not b:
                continue
            sf = out / (full.replace(":", "_") + f"_s{j - at:+d}.png")
            t = im.crop(crop_mod.to_image_box(b, im.width, pad))
            t.thumbnail((120, 120))
            t.save(sf)
            if j == at:
                strip_at = len(strip)
            strip.append(str(sf))
        ref, lib = c.get("ref") or "", c.get("lib") or ""
        sus = c.get("ref_suspect") or ""
        cands = {ref: ["整理本"]} if ref else {}
        if lib and lib != ref:
            cands[lib] = ["库首位"]
        items.append({"id": full, "pre": ref, "ref_char": ref, "lib": lib or None, "cands": cands,
                      "left": c.get("left") or "", "right": c.get("right") or "",
                      "kind": c.get("kind") or SUSPECT_NAME[sus], "suspect": sus,
                      "fact": (f"库首位 {lib}" + (f" {float(c['cov']):.2f}" if c.get("cov") else "")) if lib else "",
                      "img": str(f), "strip": strip, "strip_at": strip_at})
    items.sort(key=lambda x: (ORDER.get(x["suspect"], 1), x["id"]))
    return items, missing


def apply_results(docs: list[dict]) -> list[dict]:
    """结果文档 → 改字的格 [{cell, old, new, note}]。看不清、存疑、没填字的不出。"""
    from .results import flatten
    rows = []
    for i, r in sorted(flatten(docs).items()):
        pick, pre = (r.get("pick") or "").strip(), r.get("pre")
        if r.get("verdict") not in (None, "char") or r.get("review") or not pick or pick == pre:
            continue
        rows.append({"cell": i, "old": pre, "new": pick, "note": r.get("note") or ""})
    return rows
