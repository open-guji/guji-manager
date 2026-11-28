# -*- coding: utf-8 -*-
"""给已发册的待审卡现算 `cands/1`（候选字线，CV3；`guji audit cands`）。不重跑整册、不动任何产物。

和产线新步骤（cv `glyph_candidate` 3c、`context_rank` 4b）同一份算法：
1. 字块图过 r5 向量，对全字表取余弦前 50 并展开异体族（`glyph_candidate.rank_cell`）；
2. 候选池＝卡上 3a 候选（`db.candidates`，分是覆盖分）∪ 3c 前 10；图像分取 `a`／`c` 的大者；
3. 前后文取本页 `glyph_match`＋`context_decision` 产物（`context_rank.neighbor_texts`，与 4b 同读序同邻格规则）；
4. 填空模型把池按「图像分＋0.005·logp」重排（`ctx_fill.fuse`），再交 `cands_field.build_cands` 出表（整理本字排第一）。

填空模型或前后文取不到时只出图像序（`rank=None`），不当成失败。卡片 `id` 是 `册:页:列:格[a|b]`。
cv 的名字都经 `_cv` 门面（`glyph_candidate_mod`／`context_rank_mod`／`ctx_fill_mod`，cv ≥ 登记它们的版本）。
"""
from __future__ import annotations

from collections.abc import Callable

from .cands_field import build_cands

CAND_K = 10          # 3c 前几个并进池（同收尾 `glyph_analyzer` 的 cand_k）


def final_of(card: dict, cand50: list[list], fam_of: dict[str, str]) -> dict:
    """卡上 3a 候选＋3c 候选 → 收尾 `FinalRec` 形的 dict（只带 a／c 两路证据）。"""
    cands: dict[str, dict] = {}
    for x in (card.get("db") or {}).get("candidates") or []:
        c, s = x[0], x[1]
        cands.setdefault(c, {"char": c, "p": None, "evidence": {}})["evidence"]["a"] = {"sim": round(float(s), 4)}
    for c, s in cand50[:CAND_K]:
        ev = cands.setdefault(c, {"char": c, "p": None, "evidence": {}})["evidence"]
        ev["c"] = {"sim": round(float(s), 4), **({"fam_of": fam_of[c]} if c in fam_of else {})}
    return {"cands": list(cands.values())}


def pool_of(final: dict) -> list[tuple[str, float]]:
    """池：[(字, 图像分)]，图像分取 a／c 的大者（与 cv `context_rank.pool_of` 同口径）。"""
    out = []
    for fc in final["cands"]:
        v = [float(fc["evidence"][k]["sim"]) for k in ("a", "c") if k in fc["evidence"]]
        if v:
            out.append((fc["char"], max(v)))
    return out


def cands_for_cells(card: dict, cand50: list[list], fam_of: dict[str, str], left: str, right: str, *,
                    lm=None, fuse=None, w: float = 0.005, topk: int = 10, by: str = "") -> dict | None:
    """一格：（3c 结果、前后文）→ `cands/1`。`lm`＝填空模型（`ctx_fill.shared()`，None＝只出图像序），`fuse`＝`ctx_fill.fuse`。"""
    final = final_of(card, cand50, fam_of)
    rank = None
    pool = pool_of(final)
    if lm is not None and fuse is not None and len(pool) >= 2 and (left or right):
        sem = lm.sem(left, right, [c for c, _ in pool])
        if sem is not None:
            sims = dict(pool)
            rank = {"ran": True, "ranked": [[c, round(f, 4), round(sims[c], 4), None if lp is None else round(lp, 3)]
                                            for c, f, lp in fuse(pool, sem, w)[:topk]]}
    ref = (card.get("ref") or {}).get("char")
    return build_cands(final, rank, ref, by=by)


def cands_for_cards(book: str, cards: list[dict], *, ctx, w: float = 0.005,
                    image_cache=None, log: Callable[[str], None] | None = None) -> dict[str, dict]:
    """一批卡 → `{卡 id: cands/1}`。取不到字块图的卡不出（键缺席）。`ctx`＝引擎 `RunContext`（取本页产物、现切字块图）。"""
    from .._cv import (context_rank_mod as CR, ctx_fill_mod as CF, glyph_candidate_mod as GC,
                       normalize_patch, rare_patch, resolve_patch_key)
    import numpy as np

    L = GC._load()
    lm = CF.shared()
    by = f"{GC.model_version()} ctx={CF.model_version(w)} fuse=f1" + ("" if lm else " noctx")
    out: dict[str, dict] = {}
    texts: dict[int, dict] = {}
    no_img = 0
    for i, c in enumerate(cards):
        page = int(c["page"])
        img = rare_patch(book, page, int(c["col"]), int(c["slot"]), c.get("sub") or "", image_cache)
        if img is None and ctx is not None:
            key = resolve_patch_key(book, f"p{page:04d}c{int(c['col']):02d}s{int(c['slot'])}{c.get('sub') or ''}")
            try:
                img = ctx.image("char_patch", key)
            except Exception:  # noqa: BLE001 — 切不出就当没图
                img = None
        if img is None:
            no_img += 1
            continue
        if page not in texts:
            try:
                dec = None
                try:
                    dec = ctx.product("context_decision", page)
                except Exception:  # noqa: BLE001 — 没有定字产物就用 3a 第一候选当邻字
                    pass
                texts[page] = CR.neighbor_texts(ctx.product("glyph_match", page), dec)
            except Exception:  # noqa: BLE001 — 本页没有 3a 产物：这页的卡只出图像序
                texts[page] = {}
        s = np.asarray((L["cnn"].embed([normalize_patch(img)]) @ L["mat"].T)[0])
        cand50, fam_of = GC.rank_cell(s, L["chars"], L["index"], L["family"])
        left, right = texts[page].get(c["id"], ("", ""))
        res = cands_for_cells(c, cand50, fam_of, left, right, lm=lm, fuse=CF.fuse, w=w, by=by)
        if res:
            out[c["id"]] = res
        if log and (i + 1) % 100 == 0:
            log(f"cands：{i + 1}/{len(cards)} 格")
    if log and no_img:
        log(f"cands：{no_img}/{len(cards)} 格取不到字块图，没出候选")
    return out


def attach(cards: list[dict], cands: dict[str, dict]) -> int:
    """把 cands 挂到卡上（`card["cands"]`），返回挂了几张。"""
    n = 0
    for c in cards:
        x = cands.get(c.get("id"))
        if x:
            c["cands"] = x
            n += 1
    return n
