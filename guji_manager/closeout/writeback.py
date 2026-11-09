"""dev 上机器错位锚点的自动写回（方案七之六：vol15/17/19/20 共 52 条）。

三个条件**同时满足**才自动写，缺一条就不动（交待审格）：
1. 来源是机器（`source` 不含 human／manual／人裁／手改）；
2. 对照表给的位置上的字等于该条的 `pre_char`；
3. dev 现在这个锚点上的字与 `pre_char` 不同（确实错位了）。

对照表是「dev 当前锚点 → 正确锚点」（不是换图那张：已挪过的会被再挪一次，A33 11-09 提醒）；新 char 用 dev 当前 char。
只改 `anchor`／`char_offset`，不动 mark、pre_char、source。审计清单写进 commit 信息和轮报告；
`sample()` 取固定种子的 30 条给审阅页复核，有错回退并关掉自动。
"""
from __future__ import annotations

import random

MANUAL_KEYS = ("human", "manual", "人裁", "手改")


def is_manual(source) -> bool:
    s = str(source or "").lower()
    return any(k in s for k in MANUAL_KEYS)


def slots_of(char: dict) -> list[tuple[str, str]]:
    return [(c["a"], c["c"]) for p in char.get("pages") or [] for col in p.get("columns") or []
            for c in col.get("cells") or []]


def plan_fixes(punct: dict, char: dict, cellmap: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """返回 (可写, 不可写)。每项 {idx, mark, pre_char, source, old, new, why}；只读，不改 punct。"""
    slots = slots_of(char)
    pos = {a: i for i, (a, _c) in enumerate(slots)}
    ok, skip = [], []
    for i, p in enumerate(punct.get("punctuations") or []):
        a, pc = p.get("anchor"), p.get("pre_char")
        n = cellmap.get(a) if a else None
        if not a or n is None or n == a:
            continue                                   # 表里没要挪的
        rec = {"idx": i, "mark": p.get("mark", ""), "pre_char": pc, "source": p.get("source", ""), "old": a, "new": n}
        if pc is None:
            skip.append({**rec, "why": "无 pre_char，无从核对"})
        elif is_manual(p.get("source")):
            skip.append({**rec, "why": "来源不是机器（人裁／手改）"})
        elif n not in pos:
            skip.append({**rec, "why": f"对照表位置 {n} 不在 char 里"})
        elif slots[pos[n]][1] != pc:
            skip.append({**rec, "why": f"对照表位置的字 {slots[pos[n]][1]} ≠ pre_char {pc}"})
        elif a in pos and slots[pos[a]][1] == pc:
            skip.append({**rec, "why": "dev 当前锚点上的字就是 pre_char（没错位）"})
        else:
            ok.append(rec)
    return ok, skip


def apply_fixes(punct: dict, char: dict, fixes: list[dict]) -> int:
    """把 plan_fixes 的「可写」项写进 punct（就地）。再核一遍 anchor 没变过。返回写了几条。"""
    pos = {a: i for i, (a, _c) in enumerate(slots_of(char))}
    n = 0
    for f in fixes:
        p = punct["punctuations"][f["idx"]]
        if p.get("anchor") != f["old"]:
            raise ValueError(f"#{f['idx']} 锚点已不是 {f['old']}，计划过期")
        p["anchor"], p["char_offset"] = f["new"], pos[f["new"]]
        n += 1
    return n


def audit_lines(chapter: str, fixes: list[dict]) -> list[str]:
    """审计行（commit 信息、轮报告用）：章 #条目 标点 pre_char 旧锚→新锚。"""
    return [f"{chapter}\t#{f['idx']}\t{f['mark']!r}\t{f['pre_char']}\t{f['old']}→{f['new']}" for f in fixes]


def sample(fixes: list[dict], k: int = 30, seed: int = 0) -> list[dict]:
    """抽审：固定种子，不足 k 条全取。"""
    if len(fixes) <= k:
        return list(fixes)
    return sorted(random.Random(seed).sample(fixes, k), key=lambda f: f["idx"])
