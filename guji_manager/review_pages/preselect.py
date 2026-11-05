"""预选：参校本字／库首位／独立识读（文本层或 OCR）／大模型读法，合成每格的预选答案。

规则（框架第十五节）：
- 三方一致（参校本＝库首位＝独立识读，且字形分过门槛）→ route=auto，不上页（放行本身仍要过验收纪律）。
- 其余格 route=page，分「分歧类型」，预选＝加权多数，附依据与置信；同类排在一起。

纯函数，不读文件。输入每格：
  {id, ref, lib, lib_score, text, ocr, llm, llm_conf}
缺的字段留空即可；"独立识读"取 text（文本层）优先，否则 ocr。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable

GATE = 0.95            # 字形分过门槛（与降人审迭代框架 L2 一致：库前五 ≥0.95）
KINDS = ("ref_vs_lib", "ref_missing", "lib_missing", "indep_dissent", "no_indep", "weak_glyph")


def _indep(cell: dict) -> tuple[str | None, str | None]:
    if cell.get("text"):
        return cell["text"], "text"
    if cell.get("ocr"):
        return cell["ocr"], "ocr"
    return None, None


def classify(cell: dict, gate: float = GATE) -> dict:
    ref, lib = cell.get("ref") or None, cell.get("lib") or None
    ind, ind_src = _indep(cell)
    llm = cell.get("llm") or None
    score = cell.get("lib_score")
    votes: list[tuple[str, str]] = []           # (来源, 字)
    for src, ch in (("ref", ref), ("lib", lib), (ind_src, ind), ("llm", llm)):
        if ch:
            votes.append((src, ch))
    cnt = Counter(ch for _, ch in votes)
    pre, n = (cnt.most_common(1)[0] if cnt else (None, 0))
    if cnt and list(cnt.values()).count(n) > 1:   # 平票：参校本优先，其次库首位
        pre = ref or lib or pre
        n = cnt[pre]
    glyph_ok = score is not None and score >= gate
    agree3 = bool(ref and lib and ind and ref == lib == ind and glyph_ok)
    if agree3:
        kind, route = "agree3", "auto"
    else:
        route = "page"
        if ref and lib and ref != lib:
            kind = "ref_vs_lib"
        elif not ref:
            kind = "ref_missing"
        elif not lib:
            kind = "lib_missing"
        elif ind and ind != ref:
            kind = "indep_dissent"
        elif not ind:
            kind = "no_indep"
        else:
            kind = "weak_glyph"
    llm_high = cell.get("llm_conf") == "high"
    if n >= 3 and glyph_ok:
        conf = "high"
    elif n >= 2 and (glyph_ok or llm_high):
        conf = "mid"
    else:
        conf = "low"
    return {"id": cell["id"], "route": route, "kind": kind, "pre": pre, "pre_conf": conf,
            "pre_src": [s for s, ch in votes if ch == pre], "votes": votes}


def preselect(cells: Iterable[dict], gate: float = GATE) -> dict:
    """返回 {auto: [...], page: [...按分歧类型分组、组内低置信在前], stats}。"""
    auto, page = [], []
    for c in cells:
        r = classify(c, gate)
        r["cell"] = c
        (auto if r["route"] == "auto" else page).append(r)
    order = {k: i for i, k in enumerate(KINDS)}
    rank = {"low": 0, "mid": 1, "high": 2}
    page.sort(key=lambda r: (order[r["kind"]], r["pre"] or "", rank[r["pre_conf"]]))
    by_kind: dict[str, int] = defaultdict(int)
    for r in page:
        by_kind[r["kind"]] += 1
    n = len(auto) + len(page)
    return {"auto": auto, "page": page,
            "stats": {"cells": n, "auto": len(auto), "page": len(page),
                      "page_rate": round(len(page) / n, 4) if n else 0.0, "by_kind": dict(by_kind)}}
