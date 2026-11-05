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


def build_cards(rows: list[dict], k: int = 5, solo: bool = False) -> list[dict]:
    """rows: 每格 {id, pre, pre_conf, img?, kind?}。返回卡片列表，大卡在前。
    solo=True（难认字页）：一格一卡、不合卡、照 rows 顺序，没有跟随格。"""
    if solo:
        return [{"char": r.get("pre") or "？", "n": 1, "samples": [r], "followers": [],
                 "kinds": [r["kind"]] if r.get("kind") else [], "kind_of": {r["id"]: r["kind"]} if r.get("kind") else {}}
                for r in rows]
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
                      "kinds": sorted({r.get("kind") for r in items if r.get("kind")}),
                      "kind_of": {r["id"]: r["kind"] for r in items if r.get("kind")}})
    cards.sort(key=lambda c: (-c["n"], c["char"]))
    return cards


def _cell_status(v: str | None, ch: str) -> tuple[str, str]:
    """逐格结果 → (status, char)。v：seg|unclear|other|pick:<字>|None。"""
    if v and v.startswith("unknown"):          # 难认字页：认不出（冒号后的部件由 expand 另记 parts）
        return "unknown", ch
    if v == "notchar":
        return "notchar", ch
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
      notchar（不是字）、unknown（认不出，能看出的部件记在 parts）、
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
        row = {"id": s["id"], "char": c, "status": st_, "kind": s.get("kind")}
        if st_ == "unknown" and per.get(s["id"], "")[8:]:
            row["parts"] = per[s["id"]][8:]
        out.append(row)
    if doc is not None:
        status = "follow" if all(r["status"] == "ok" for r in out) else "audit"
        ko = card.get("kind_of") or {}
        out += [{"id": i, "char": ch, "status": status, "kind": ko.get(i)} for i in card["followers"]]
    return out
