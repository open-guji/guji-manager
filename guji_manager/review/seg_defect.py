"""切坏格检测（第一期：只读、只标，2026-11-04，史記第 8 轮计划第 3 项；A22、A31 评审过）。

离线工具，**不是 Step、不进任何 Step 的 code_deps**，不改放行。读一册若干页的 row_segment／cell_shrink／
seed_admit／align_ref 产物与字块缓存，把疑似切坏的格列成表，人看抽样后再定第二期的闸
（第二期在 seed_admit 写 `evidence.seg_kind`，why 码仍是 `seg_defect`，见 `review/reasons.py` 的 `SEG_KINDS`）。

四种 `seg_kind`（设计稿 ai-team domain/CV/质检/史記-r8-交A22/切坏检测判法设计稿-SJ.md）：

- `merged`  两字并一格：墨高 ≥ `MERGED_H` 倍基准（整字格按格高 `period`，夹注半格按本列夹注半格墨高中位），
  且竖向投影中段有低谷（墨 < `MERGED_VALLEY` 峰值、长 ≥ `MERGED_GAP` 格高），低谷上下两团各高 ≥ `MERGED_PART` 格高
  （防「三」「二」这种字中间本来就有空行）。
- `clipped` 字被切掉一截：Step3 选中的切线穿墨（`cut_candidates` 里选中那条的 `seam_ink` ≥ `CLIP_SEAM_INK`），
  线两侧的格都标，有大印（`seals` 里的 stain）的页和打了 `seal_region` 旗的格不判（印泥满纸噪点）；
  或 cell_shrink 打了 `boundary_ink` 旗、且不是列尾格、本格没放行（列尾字脚贴版框就打旗；列首格留着）（A22：05:15:8:1a 字头被切到格外）。
  殿本 vol12 152 页（A22 11-04）：原口径 clipped 370 条几乎全是误报——boundary_ink 364 条多在列尾格，字脚贴版框
  就打旗；seam_ink 12–20 的 6 条有 4 条在卷首大印页。所以 boundary_ink 不单独算、阈值从 12 提到 30。
  **同字对照**（A22-4，11-05）：列端格（贴版框一格高以内的列首／列尾格）的墨高比同册同字列中格的墨高中位数矮
  （`< SAME_H`，或 `< SAME_H_WIDE` 且宽不跟着缩：宽比/高比 ≥ `SAME_ASPECT`），说明字缺了一截（多是剥框线连笔画
  一起剥掉、或切线落在字里）。参照只取已放行、离列首列尾各 2 格以外的格，同字 ≥ `SAME_MIN_REF` 个；
  扁字（参照墨高 < `SAME_FLAT` 格高，「一」）不判。只判列端：列中格同口径在殿本 vol12 标 18 格几乎全是好字
  （列中本来就有压扁的字），没有尺子量过。尺子＝殿本列端看图单两批（10 册 548 块，人点「切笔」41 块）：
  本判据加上后 clipped 中 26/41、误标 5 块（查准 0.84）；原来 seam_ink／boundary_ink 两条只中 1 块。
  殿本 vol12 全册仍是 0 条（列端没有缺一截的字）。
- `bleed`   邻格笔画溢入：cell_shrink 的 `edge_blob` 旗（上下带里与主体隔开的一块墨，`extractor._shape_features`）。
  A22 建议改用 `partition_strip` 的归属图，第一期先用现成旗，抽样不准再换。
- `frame_residue` 框线残笔：列首／列尾格（贴着版框一格高以内）的最终字块上，按全页半格线位
  （`CellShrinkStep._page_frame_lines` 同一算法，夹注半格线位）用 `extractor.inner_frame_band_mask` 还认得出线的
  （与 cell_shrink 剥线同一个定义；剥过还在＝没剥干净）。夹注 a/b 各自一块图块，各判。

用法：`python -m guji_manager.review.seg_defect <册> --pages 2,10 -w <工作区> [--out x.tsv]`；不给 --pages 跑整册。
"""
from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path

import numpy as np

SEG_KINDS = ("merged", "clipped", "bleed", "frame_residue")

MERGED_H = 1.6
MERGED_VALLEY = 0.10
MERGED_GAP = 0.08
MERGED_PART = 0.30
CLIP_SEAM_INK = 30   # 殿本 vol12：12–20 全误报（A22 11-04）
SAME_H = 0.80        # 同字对照：墨高比低于它就算缺一截
SAME_H_WIDE = 0.85   # 墨高比在 SAME_H～它之间时，还要宽不跟着缩
SAME_ASPECT = 1.30   # 宽比/墨高比 ≥ 它＝只矮不窄（整字压扁的宽也跟着缩）
SAME_MIN_REF = 5     # 同字参照至少几个
SAME_FLAT = 0.30     # 参照墨高 < 它×格高的扁字（「一」）不判：墨高只有几像素，比值不稳
INK_THR = 160        # 墨像素：灰度 < 它
EDGE_ROWS = 3        # 列端边线压墨：量字块靠版框一侧最外几行墨

FIELDS = ("格号", "seg_kind", "特征", "放行", "通道", "机器字", "整理本字", "字块键")


def _valley_split(patch: np.ndarray, cell_h: float) -> str | None:
    """竖向投影中段的低谷：返回特征说明，没有就 None。"""
    if patch is None or patch.size == 0:
        return None
    ink = (patch < 128).sum(axis=1).astype(float)
    if ink.max() <= 0:
        return None
    nz = np.nonzero(ink)[0]
    top, bot = int(nz[0]), int(nz[-1])
    low = ink < MERGED_VALLEY * ink.max()
    best = None
    y = top
    while y <= bot:
        if low[y]:
            y0 = y
            while y <= bot and low[y]:
                y += 1
            if y0 > top and y <= bot and (y - y0) >= MERGED_GAP * cell_h \
                    and (y0 - top) >= MERGED_PART * cell_h and (bot - y + 1) >= MERGED_PART * cell_h:
                best = (y0, y)
        y += 1
    return None if best is None else f"valley={best[0]}-{best[1]}"


def _ink_h(patch: np.ndarray | None) -> int | None:
    """字块墨高：墨像素（< INK_THR）≥ 2 个的行，首末行之间的高。"""
    if patch is None or patch.size == 0:
        return None
    rows = np.nonzero((patch < INK_THR).sum(axis=1) >= 2)[0]
    return None if rows.size == 0 else int(rows[-1] - rows[0] + 1)


def edge_ink(patch: np.ndarray | None, bottom: bool) -> float:
    """列端边线压墨：字块靠版框一侧（列首格量上沿、列尾格量下沿）最外 `EDGE_ROWS` 行墨里，
    有墨的列占字块宽的比例。笔画被截断的字，截口那一侧常有好几笔齐刷刷顶到边上。"""
    if patch is None or patch.size == 0:
        return 0.0
    ink = patch < INK_THR
    rows = np.nonzero(ink.sum(axis=1) >= 2)[0]
    if rows.size == 0:
        return 0.0
    band = ink[rows[-1] - EDGE_ROWS + 1: rows[-1] + 1] if bottom else ink[rows[0]: rows[0] + EDGE_ROWS]
    return float(band.any(axis=0).sum()) / ink.shape[1]


def same_char_clip(h: int, w: int, ref: tuple[float, float, int] | None, period: float) -> str | None:
    """同字对照：字块墨高 h、宽 w 对参照（墨高中位、宽中位、个数），像缺了一截就返回特征说明。"""
    if ref is None or h is None or not period:
        return None
    rh_med, rw_med, n = ref
    if n < SAME_MIN_REF or rh_med < SAME_FLAT * period or rh_med <= 0 or rw_med <= 0:
        return None
    rh, rw = h / rh_med, w / rw_med
    if rh < SAME_H or (rh < SAME_H_WIDE and rw / rh >= SAME_ASPECT):
        return f"同字墨高 {rh:.2f} 宽 {rw:.2f}（参照 {n} 个）"
    return None


def _body(cc_chars):
    return [r for r in cc_chars if r.patch_key and r.cell_type != "empty"]


def same_char_refs(book: str, pages, store, cache) -> dict:
    """同册同字参照：(字, 是否夹注) → (墨高中位, 宽中位, 个数)。只取已放行、离本列首末各 2 格以外的格。"""
    from .._cv import page_key, read_view, resolve_patch_key, steps  # noqa: F401  —— steps 注册产物种类
    acc: dict[tuple[str, bool], list[tuple[int, int]]] = {}
    for page in pages:
        pk = page_key(page)
        chars = read_view(store, book, "cell_shrink", pk, "char_index")
        adm = store.read(book, "seed_admit", pk, "seed_admit")
        if chars is None or adm is None:
            continue
        arec = {r.id: r for c in adm.columns for r in c.chars}
        for cc in chars.columns:
            body = _body(cc.chars)
            if not body:
                continue
            lo, hi = min(r.slot for r in body), max(r.slot for r in body)
            for r in body:
                a = arec.get(r.id)
                if a is None or not a.admit or not a.char or not (lo + 2 <= r.slot <= hi - 2):
                    continue
                p = _patch(cache, book, resolve_patch_key(book, r.patch_key, store))
                h = _ink_h(p)
                if h:
                    acc.setdefault((a.char, bool(r.sub)), []).append((h, p.shape[1]))
    return {k: (statistics.median(x[0] for x in v), statistics.median(x[1] for x in v), len(v))
            for k, v in acc.items()}


def _patch(cache, book: str, key: str | None):
    if not key:
        return None
    import cv2
    from .._cv import imread as cv_imread
    p = cache.path(book, "char_patch", key)
    if not p.exists():
        return None
    return cv_imread(str(p), cv2.IMREAD_GRAYSCALE)


class _LineCtx:
    """给 `CellShrinkStep._page_frame_lines` 用的最小上下文：只读列图、参数取 cell_shrink 缺省＋半格线位开。"""

    def __init__(self, cache, book: str, frame_line_max_off: float):
        from .._cv import CellShrinkParams
        self._cache, self._book = cache, book
        self._p = CellShrinkParams(frame_line_max_off=frame_line_max_off, jiazhu_strip_rules=True)

    def image(self, kind: str, key: str):
        import cv2
        from .._cv import imread as cv_imread
        try:
            return cv_imread(str(self._cache.path(self._book, kind, key)), cv2.IMREAD_GRAYSCALE)
        except FileNotFoundError:   # 与 cv2.imread 同口径：缺图给 None
            return None

    def params_for(self, _step):
        return self._p


def _frame_residue(patch, r, cc_cells, lines: dict) -> str | None:
    """列端格最终字块上还认得出的内框细线：返回特征说明，没有就 None。"""
    from .._cv import inner_frame_band_mask
    if patch is None or cc_cells is None:
        return None
    cell_h = float(cc_cells.period or 0)
    if cell_h <= 0:
        return None
    y0 = r.bbox_col[1]
    out = []
    for bottom, key, edge in ((False, "frame_half_lines_top", cc_cells.border_top),
                              (True, "frame_half_lines_bottom", cc_cells.border_bottom)):
        lys = (lines.get(key) or {}).get(cc_cells.col) or []
        if edge is None or not lys:
            continue
        near = (r.bbox_col[3] >= edge - cell_h) if bottom else (r.bbox_col[1] <= edge + cell_h)
        if not near:
            continue
        ly = tuple((float(v) - y0, float(th)) for v, th in lys)
        m = inner_frame_band_mask(np.ascontiguousarray(patch), cell_h, bottom, ly)
        if m is not None and m.any():
            out.append(("下" if bottom else "上") + f"线 {int(m.sum())}px")
    return " ".join(out) or None


def _at_frame_end(r, lo: int, hi: int, c_cells, cell_h: float) -> str | None:
    """列首格（本列第一个字格、贴上版框一格高以内）给 "top"，列尾格（最后一个、贴下版框一格高以内）给 "bottom"。"""
    if r.slot == lo and c_cells.border_top is not None and r.bbox_col[1] <= c_cells.border_top + cell_h:
        return "top"
    if r.slot == hi and c_cells.border_bottom is not None and r.bbox_col[3] >= c_cells.border_bottom - cell_h:
        return "bottom"
    return None


def scan_page(book: str, page: int, store, cache, frame_line_max_off: float = 0.35,
              refs: dict | None = None, min_edge_ink: float = 0.0) -> list[dict]:
    """一页的疑似切坏格。`refs` 是 `same_char_refs` 的同字参照；不给就不做同字对照。
    `min_edge_ink`：同字对照命中后还要列端边线压墨（`edge_ink`）≥ 它才标，书级参数，缺省 0＝不要求。
    史記 02/03/08（SJ 11-05）：写本字大小差异大，同字对照 117 格只约 14 格真切坏，真的边线压墨都 ≥ 0.2；
    殿本尺子上加 0.2 会把 25 格真切坏掉到 17 格、误标只少 1 格，所以殿本不开。"""
    from .._cv import steps  # noqa: F401  —— 注册产物种类
    from .._cv import page_key
    from .._cv import read_view, resolve_patch_key
    pk = page_key(page)
    cells = read_view(store, book, "row_segment", pk, "cells")
    chars = read_view(store, book, "cell_shrink", pk, "char_index")
    adm = store.read(book, "seed_admit", pk, "seed_admit")
    ref = store.read(book, "align_ref", pk, "align_ref")
    try:
        seals = store.read(book, "seal_detect", pk, "seals")
    except Exception:                          # noqa: BLE001
        seals = None
    stain_page = any(x.kind == "stain" for x in (seals.seals if seals else []))
    if chars is None:
        return []
    arec = {r.id: r for c in (adm.columns if adm else []) for r in c.chars}
    coord = {r.id: r.ref_char for r in (ref.coord if ref else [])}
    # Step3 切线穿墨：(列, 格号) → seam_ink
    seam: dict[tuple[int, int], int] = {}
    period: dict[int, float] = {}
    for cc in (cells.columns if cells else []):
        period[cc.col] = float(cc.period or 0) or 0.0
        for cut in (getattr(cc, "cut_candidates", None) or []):
            cut = cut if isinstance(cut, dict) else cut.model_dump()
            cands, i = cut.get("candidates") or [], cut.get("chosen") or 0
            if not cands or i >= len(cands):
                continue
            si = int(cands[i].get("seam_ink") or 0)
            if si >= CLIP_SEAM_INK:
                for s in (cut.get("slot_above"), cut.get("slot_below")):
                    if s is not None:
                        seam[(cc.col, int(s))] = max(seam.get((cc.col, int(s)), 0), si)
    lines: dict = {}
    if cells is not None:
        from .._cv import CellShrinkStep
        try:
            lines = CellShrinkStep._page_frame_lines(None, _LineCtx(cache, book, frame_line_max_off), page, cells)
        except Exception:                      # noqa: BLE001 —— 缺列图就不判这一类
            lines = {}
    by_col = {cc.col: cc for cc in (cells.columns if cells else [])}
    out: list[dict] = []
    for cc in chars.columns:
        jz = [r.height for r in cc.chars if r.sub and r.patch_key and r.height]
        jz_med = statistics.median(jz) if jz else 0.0
        ph = period.get(cc.col) or 0.0
        body = _body(cc.chars)
        hi = max((r.slot for r in body), default=0)
        lo = min((r.slot for r in body), default=0)
        c_cells = by_col.get(cc.col)
        for r in cc.chars:
            if not r.patch_key or r.cell_type == "empty":
                continue
            hits: list[tuple[str, str]] = []
            base = jz_med if r.sub else ph
            if base and r.height >= MERGED_H * base:
                v = _valley_split(_patch(cache, book, resolve_patch_key(book, r.patch_key, store)), base)
                if v:
                    hits.append(("merged", f"h={r.height:.0f}/{base:.0f} {v}"))
            a = arec.get(r.id)
            si = None if stain_page or "seal_region" in r.flags else seam.get((cc.col, r.slot))
            if si:
                hits.append(("clipped", f"seam_ink={si}"))
            elif "boundary_ink" in r.flags and r.slot < hi and not (a is not None and a.admit):
                hits.append(("clipped", "boundary_ink"))
            elif refs and a is not None and a.char and c_cells is not None and ph \
                    and (end := _at_frame_end(r, lo, hi, c_cells, ph)):
                p = _patch(cache, book, resolve_patch_key(book, r.patch_key, store))
                sc = same_char_clip(_ink_h(p), p.shape[1] if p is not None else 0,
                                    refs.get((a.char, bool(r.sub))), ph)
                ei = edge_ink(p, end == "bottom") if sc else 0.0
                if sc and ei >= min_edge_ink:
                    hits.append(("clipped", f"{sc} 边线压墨 {ei:.2f}"))
            if "edge_blob" in r.flags:
                hits.append(("bleed", "edge_blob"))
            if lines:
                fr = _frame_residue(_patch(cache, book, resolve_patch_key(book, r.patch_key, store)),
                                    r, by_col.get(cc.col), lines)
                if fr:
                    hits.append(("frame_residue", fr))
            for kind, feat in hits:
                out.append({"格号": r.id.split(":", 1)[1] if r.id.count(":") >= 4 else r.id,
                            "seg_kind": kind, "特征": feat,
                            "放行": "是" if a is not None and a.admit else "否",
                            "通道": (a.channel or "") if a is not None else "",
                            "机器字": (a.char or "") if a is not None else "",
                            "整理本字": coord.get(r.id) or "",
                            "字块键": r.patch_key})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("book")
    ap.add_argument("--pages", default="")
    ap.add_argument("-w", "--workspace", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--clip-edge-ink", type=float, default=0.0,
                    help="同字对照还要列端边线压墨 ≥ 它（书级；史記建议 0.2，殿本不用）")
    ap.add_argument("--no-same-char", action="store_true", help="不做同字对照（省读全册字块）")
    ap.add_argument("--frame-line-max-off", type=float, default=0.35, help="同册配置 cell_shrink.frame_line_max_off")
    a = ap.parse_args(argv)
    from .._cv import ImageCache
    from .._cv import ProductStore
    ws = Path(a.workspace)
    store, cache = ProductStore(ws / "products"), ImageCache(ws / "cache")
    if a.pages:
        pages = [int(x) for x in a.pages.split(",") if x.strip()]
    else:
        pages = sorted(int(p.stem[1:]) for p in store.step_dir(a.book, "cell_shrink").glob("p*.json"))
    all_pages = sorted(int(p.stem[1:]) for p in store.step_dir(a.book, "cell_shrink").glob("p*.json"))
    refs = None if a.no_same_char else same_char_refs(a.book, all_pages, store, cache)
    rows = [r for p in pages for r in scan_page(a.book, p, store, cache, a.frame_line_max_off, refs,
                                                    a.clip_edge_ink)]
    import contextlib
    with (open(a.out, "w", encoding="utf-8", newline="") if a.out else contextlib.nullcontext(sys.stdout)) as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    by = {k: sum(1 for r in rows if r["seg_kind"] == k) for k in SEG_KINDS}
    print(f"{a.book}: {len(pages)} 页，{len(rows)} 条 {by}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
