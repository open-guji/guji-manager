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


def _cell_status(v: str | None, ch: str) -> tuple[str, str]:
    """逐格结果 → (status, char)。v：seg|unclear|other|pick:<字>|None。"""
    if not v or v == "ok":
        return "ok", ch
    if v.startswith("pick:"):
        x = v[5:]
        return ("ok", ch) if x == ch else ("pick", x)
    return {"seg": "seg", "unclear": "unclear", "other": "bad"}.get(v, "bad"), ch


def expand_card_result(card: dict, doc: dict | None, cells: dict[str, str] | None = None) -> list[dict]:
    """card: build_cards 的一张卡；doc: 页面「本页其余都对」时存回的 {char, pick, bad:[样例格号], cells?}，
    没点下一页时为 None；cells: 逐格文档 {格号: v}（模板 1.1 起每点一下就存，比页文档新）。

    返回每格决定 {id, char, status}：
      ok（样例对）、pick（这格改成 char）、seg（切分有问题）、unclear（看不清）、bad（不对，没填字）、
      follow（跟随格，样例全对时放）、audit（样例有不对，跟随格退回逐格审）。
    doc 为 None 时只出点过的样例格，跟随格不出（这张卡还没审完）。"""
    ch = (doc or {}).get("pick") or card["char"]
    per = dict((doc or {}).get("cells") or {})
    for i in (doc or {}).get("bad", []):
        per.setdefault(i, "other")
    per.update(cells or {})
    out = []
    for s in card["samples"]:
        if doc is None and s["id"] not in per:
            continue
        st_, c = _cell_status(per.get(s["id"]), ch)
        out.append({"id": s["id"], "char": c, "status": st_})
    if doc is not None:
        status = "follow" if all(r["status"] == "ok" for r in out) else "audit"
        out += [{"id": i, "char": ch, "status": status} for i in card["followers"]]
    return out
