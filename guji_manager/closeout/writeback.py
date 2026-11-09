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


def plan_fixes(punct: dict, char: dict, cellmap: dict[str, str],
               old_pre: dict[tuple[str, str], str] | None = None) -> tuple[list[dict], list[dict]]:
    """返回 (可写, 不可写)。每项 {idx, mark, pre_char, source, old, new, why}；只读，不改 punct。

    `old_pre`：{(dev 当前锚点, mark): 旧 pre_char}。dev 上的 `pre_char` 常被「校验字同步」刷成错位处的字
    （条件 3 说的「被刷新过」），所以三个条件里的 pre_char 要用**换图前的旧值**；不给就退回条目自带的 pre_char。"""
    slots = slots_of(char)
    pos = {a: i for i, (a, _c) in enumerate(slots)}
    ok, skip = [], []
    for i, p in enumerate(punct.get("punctuations") or []):
        a = p.get("anchor")
        pc = (old_pre or {}).get((a, p.get("mark", "")), p.get("pre_char"))
        n = cellmap.get(a) if a else None
        if not a or n is None or n == a:
            continue                                   # 表里没要挪的
        rec = {"idx": i, "mark": p.get("mark", ""), "pre_char": pc, "source": p.get("source", ""), "old": a, "new": n,
               "dev_pre_char": p.get("pre_char")}
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
        if "pre_char" in p:
            p["pre_char"] = f["pre_char"]               # 校验字回到换图前的旧值（＝新锚点上的字，条件 2 已核）
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


def from_replay(rows, vol: str) -> tuple[dict[str, str], dict[tuple[str, str], str], list[str]]:
    """A33 回放不一致明细（`回放不一致明细-平移检验后-A33.tsv` 的行，列：册 层 条目 旧锚 表替换后的锚 金标位置 …）
    → 某册的（dev 当前→正确 对照表, 旧 pre_char, 冲突说明）。只取标点；条目形如 `#4105 '，' 前字=史`。
    同一 dev 锚点被指到不同目标的丢掉并记冲突（交人看）。"""
    import re
    m: dict[str, str] = {}
    pre: dict[tuple[str, str], str] = {}
    bad: set[str] = set()
    notes: list[str] = []
    for r in rows:
        if len(r) < 6 or r[1] != "标点" or str(int(r[0])) != str(int(vol)):
            continue
        dev, corr = r[5], r[4]
        mm = re.search(r"'(.*)' 前字=(.)", r[2])
        if not dev or dev == corr or "-" in corr or not mm:
            continue
        if m.get(dev, corr) != corr:
            bad.add(dev)
            notes.append(f"{dev} 指向不止一处：{m[dev]} / {corr}")
            continue
        m[dev], pre[(dev, mm.group(1))] = corr, mm.group(2)
    for d in bad:
        m.pop(d, None)
    return m, {k: v for k, v in pre.items() if k[0] in m}, notes
