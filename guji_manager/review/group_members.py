# -*- coding: utf-8 -*-
"""形近字组的组内全部字：Step7 `evidence.group.members`（cv #1921，CV3 方案 B）。

只加字段不改判别：待审卡带上组内全部字（如 己巳已、日曰目），网页、相似字、终审页给每个组员出选择按钮。
cv #1921 之前的产物没有 members，这里返回 None，调用方照旧只用原来的候选来源。纯函数，不读产物。
"""
from __future__ import annotations


def group_of(evidence: dict | None) -> dict | None:
    """Step7 `evidence.group` → `{id, m:[字…]}`；没有组或没有 members（cv #1921 之前的产物）返回 None。

    cv 写的 members 是排好序的字符串（`"".join(sorted(...))`），也收列表；去重保序，只留单字。"""
    g = (evidence or {}).get("group") or {}
    raw = g.get("members")
    if not raw:
        return None
    m: list[str] = []
    for c in (list(raw) if isinstance(raw, str) else raw):
        if isinstance(c, str) and len(c) == 1 and c not in m:
            m.append(c)
    if not m:
        return None
    return {"id": str(g.get("id") or ""), "m": m}
