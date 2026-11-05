"""读 A22 的 seg_causes 输出（逐页.tsv / 逐格.tsv，中文表头）→ 切分归因看图页（seg_cause）的卡片。

一行逐页.tsv ＝ 一张卡；卡里列该页的待审格（取自逐格.tsv）。显示名和「先怎么办」从
`guji_manager.review.seg_causes.CAUSES` 取（没有就退回成因码），不在这里另抄。
裁图：seg_causes 不出图；调用者按 cell_shrink 字框裁好，给 `crop(格号) -> 图路径或 data URI` 即可。
预选是启发式（页型→特殊页型；列/行/槽/切分缺陷→切分错；其余→切对了不是切分），按台账再调。
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable

OPTIONS = ("切分错", "切对了不是切分", "特殊页型", "看不出")
_PRE = {"page_kind": "特殊页型", "pinned": "特殊页型", "known": "特殊页型",
        "page_gate": "切分错", "col_grid": "切分错", "col_gate": "切分错", "slot_short": "切分错",
        "slot_shift": "切分错", "slot_count": "切分错", "row_height": "切分错", "seg_defect": "切分错",
        "ref_none": "切对了不是切分", "grid_ok": "切对了不是切分", "seal_stain": "切对了不是切分",
        "seal": "切对了不是切分", "invert": "切对了不是切分"}


def _tsv(p) -> list[dict]:
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _causes():
    try:
        from guji_manager.review.seg_causes import CAUSES
        return CAUSES
    except Exception:
        return {}


def _name_advice(code: str, causes) -> tuple[str, str]:
    c = causes.get(code) if hasattr(causes, "get") else None
    if c is None:
        return code, ""
    if isinstance(c, dict):
        return c.get("name", code), c.get("advice") or c.get("todo") or ""
    if isinstance(c, (tuple, list)):
        return (c[0] if c else code), (c[1] if len(c) > 1 else "")
    return getattr(c, "name", code), getattr(c, "advice", "") or getattr(c, "todo", "")


def build_cards(per_page_tsv, per_cell_tsv, crop: Callable[[str], str] | None = None) -> list[dict]:
    causes = _causes()
    cells: dict[tuple, list[dict]] = {}
    for r in _tsv(per_cell_tsv):
        cells.setdefault((r["册"], r["页"]), []).append(
            {"id": r["格号"], "reason": r.get("pending_reason", ""), "img": crop(r["格号"]) if crop else ""})
    cards = []
    for r in _tsv(per_page_tsv):
        code = (r.get("主成因") or "").split()[0].split("=")[0] if r.get("主成因") else ""
        name, advice = _name_advice(code, causes)
        cs = cells.get((r["册"], r["页"]), [])
        cards.append({"key": f"{r['册']}:{r['页']}", "vol": r["册"], "page": r["页"], "cause": code,
                      "cause_name": name, "advice": advice, "detail": r.get("细节", ""),
                      "flags": r.get("全部旗", ""), "cells": cs, "pre": _PRE.get(code, "看不出")})
    return cards
