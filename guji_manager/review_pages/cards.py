"""一字一卡：同字头合一张卡，抽 3–5 个样例给人看，其余跟随。

样例挑法：先放置信最低的 2 格（最可能错、最该看），再在剩余格里等距取，凑够 k 个。
结果展开：卡全对 → 样例确认、跟随格 follow；样例里有「不对」→ 卡判 split，跟随格不放，退回逐格。
"""
from __future__ import annotations

from collections import defaultdict

_RANK = {"low": 0, "mid": 1, "high": 2}


def pick_samples(items: list[dict], k: int = 5) -> list[dict]:
    if len(items) <= k:
        return list(items)
    by_conf = sorted(items, key=lambda r: (_RANK.get(r.get("pre_conf"), 1), r["id"]))
    chosen = by_conf[:2]
    rest = [r for r in sorted(items, key=lambda r: r["id"]) if r not in chosen]
    need = k - len(chosen)
    step = (len(rest) - 1) / max(need - 1, 1) if need > 1 else 0
    chosen += [rest[round(i * step)] for i in range(need)] if need > 1 else rest[:need]
    seen, out = set(), []
    for r in chosen:
        if r["id"] not in seen:
            seen.add(r["id"]); out.append(r)
    return out


def build_cards(rows: list[dict], k: int = 5) -> list[dict]:
    """rows: 每格 {id, pre, pre_conf, img?, kind?}。返回卡片列表，大卡在前。"""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("pre"):
            groups[r["pre"]].append(r)
    cards = []
    for ch, items in groups.items():
        samples = pick_samples(items, k)
        sid = {s["id"] for s in samples}
        cards.append({"char": ch, "n": len(items), "samples": samples,
                      "followers": sorted(r["id"] for r in items if r["id"] not in sid),
                      "kinds": sorted({r.get("kind") for r in items if r.get("kind")})})
    cards.sort(key=lambda c: (-c["n"], c["char"]))
    return cards


def expand_card_result(card: dict, doc: dict) -> list[dict]:
    """card: build_cards 的一张卡；doc: 页面存回的 {char, pick, bad:[样例格号], secs}。
    返回每格决定 {id, char, status: ok|bad|follow|audit}；pick 可能改了字（人把预选字改成别的）。"""
    ch = doc.get("pick") or card["char"]
    bad = set(doc.get("bad", []))
    out = [{"id": s["id"], "char": ch, "status": "bad" if s["id"] in bad else "ok"} for s in card["samples"]]
    status = "follow" if not bad else "audit"      # 有错样例：跟随格不放，退回逐格审
    out += [{"id": i, "char": ch, "status": status} for i in card["followers"]]
    return out
