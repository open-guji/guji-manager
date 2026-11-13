"""收尾锚点待审格的汇总（现算，不存）：读待审单，按册、原因码数。"""
from __future__ import annotations

from collections import Counter

from . import anchors as A


def plan_stats(plan: dict) -> dict:
    """一份待审单 → {"cells": 待审总格数, "anchor_main": {主因: 格数}, "anchor_any": 带锚点信息的格数,
    "by_code": {auto_remap 原因码: 条数}, "by_layer": {层: 条数}}。一格多因时主因计原主因，锚点信息另算 anchor_any。"""
    main: Counter = Counter()
    by_code: Counter = Counter()
    by_layer: Counter = Counter()
    anyn = 0
    for x in [*plan.get("cells", []), *(plan.get(A.DEFERRED_KEY) or [])]:
        es = A.decode(x.get("pending_reason_detail"))
        if x.get("pending_reason") in A.ANCHOR_REASON_VALUES:
            main[x["pending_reason"]] += 1
        if es or x.get("pending_reason") in A.ANCHOR_REASON_VALUES or set(x.get("pending_reason_also") or []) & A.ANCHOR_REASON_VALUES:
            anyn += 1
        for e in es:
            by_code[e.get("c", "")] += 1
            by_layer[e.get("l", "")] += 1
    return {"cells": len(plan.get("cells", [])), "deferred_cells": len(plan.get(A.DEFERRED_KEY) or []), "anchor_main": dict(main), "anchor_any": anyn,
            "by_code": dict(by_code), "by_layer": dict(by_layer)}
