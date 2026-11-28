# -*- coding: utf-8 -*-
"""把 `guji audit cands` 算出的 `cands/1` 并进待审条目 doc（只追加新 ver，不动别的字段、不动别的条目）。

流程：`guji audit cands <册>`（出 `<册>.cards.cands.json`）→ `guji pending cands <册> --cards <该文件>`（本模块）→ `guji db sync`
→ 网站经 Worker `pending-doc` 读到 `doc.cands`（Worker 原样透传 raw.doc）。

配对：条目格号（`页:列:格[a|b]`，可变）对卡片 id 去册前缀后的格号；两边都有 `u` 且不同时不配（格号漂移，宁缺勿错）。
幂等：条目 doc 里已有同样的 cands（v／by／top／list 全同）不再追加；算法版本 `by` 变了或名次变了才追加新 ver。
只处理 open 条目（resolved／withdrawn／closed 不动）。
"""
from __future__ import annotations

import json

from .pending_items import ItemStore, norm_cell

OP = "cands"
WHY = "补候选字 cands/1（CV3）"


def _same(a: dict | None, b: dict | None) -> bool:
    key = lambda x: json.dumps({k: (x or {}).get(k) for k in ("v", "by", "top", "list", "p_other", "p_map")},
                               ensure_ascii=False, sort_keys=True)
    return a is not None and b is not None and key(a) == key(b)


def merge_cands(store: ItemStore, cards: list[dict], *, by: str, why: str = WHY) -> dict:
    """返回计数字典：{追加, 已有, 无卡, 无候选, u 不符, open}。调用方负责 `store.save()`。"""
    by_cell: dict[str, dict] = {}
    for c in cards:
        cid = str(c.get("id") or "")
        if cid:
            by_cell[norm_cell(cid)] = c
    n = {"open": 0, "追加": 0, "已有": 0, "无卡": 0, "无候选": 0, "u 不符": 0}
    for r in store.by_state("open"):
        n["open"] += 1
        c = by_cell.get(norm_cell(r["cell"]))
        if c is None:
            n["无卡"] += 1
            continue
        cu, iu = c.get("u"), r.get("u")
        if cu is not None and iu is not None and int(cu) != int(iu):
            n["u 不符"] += 1
            continue
        cands = c.get("cands")
        if not cands or not cands.get("list"):
            n["无候选"] += 1
            continue
        if _same((r.get("doc") or {}).get("cands"), cands):
            n["已有"] += 1
            continue
        store.set_fields(r["id"], {"cands": cands}, by=by, why=why, op=OP)
        n["追加"] += 1
    return n
