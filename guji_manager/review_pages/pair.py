"""字对白名单抽样页（页型 `pair_whitelist`）：按字组抽格、带前后文，页尾给每组同字率，定「双 high 可越过整理本」的白名单。

用在 sheldon 11-05 定的降人审框架：越过整理本的字组按书按组各抽 30 格金标，不继承别的书。
人看每格（原书字块＋前后文），逐格点「同字／不同字／看不清」；每组页尾即时显示同字率，再定组结论（同字／不同字／不确定）。

抽样输入（cells，每格一行）：
  {id, group, img?, left?, right?, ref_char?, char?, cap?}
  group＝字组名（如 "王/玉"）；left/right＝前后文（正文/小注读序，由调用者按 seed_admit 的读序展平）；
  ref_char＝整理本字，上下文里标【】；char＝本格机器放的字，没有就不显示。
`sample_groups` 每组按格号哈希取 n 格（稳定可复现，不依赖随机状态），返回 build 要的 items：
  {key, label, n(全组格数), pre?, hint?, tiles:[[id, img, cap, {left,right,ref}]…]}

结果（逐项文档，每组一份）：{key, pick, marks:{格号: same|diff|unclear}, same, diff, unclear, judged, n_tiles, rate}
`rates` 把结果汇成每组同字率；`whitelist` 按门槛给出可入白名单的组。
"""
from __future__ import annotations

import hashlib
from collections import defaultdict

MARKS = ("same", "diff", "unclear")


def _h(seed: str, cell_id: str) -> str:
    return hashlib.sha1(f"{seed}|{cell_id}".encode()).hexdigest()


def sample_groups(cells: list[dict], n: int = 30, seed: str = "pair-whitelist", pre: dict | None = None,
                  min_cells: int = 1) -> list[dict]:
    """每组稳定抽 n 格（不足全取）。pre：{组名: 预选}；全组格数 < min_cells 的组跳过。"""
    by: dict[str, list[dict]] = defaultdict(list)
    for c in cells:
        by[c["group"]].append(c)
    items = []
    for g in sorted(by):
        cs = by[g]
        if len(cs) < min_cells:
            continue
        pick = sorted(cs, key=lambda c: _h(seed, c["id"]))[:n]
        pick.sort(key=lambda c: c["id"])
        tiles = []
        for c in pick:
            ctx = {k: c[k] for k in ("left", "right", "ref_char") if c.get(k)}
            tiles.append([c["id"], c.get("img") or "", c.get("cap") or c.get("char") or "", ctx])
        it = {"key": g, "label": g, "n": len(cs), "tiles": tiles}
        if pre and pre.get(g):
            it["pre"] = pre[g]
        items.append(it)
    return items


def rates(docs: list[dict]) -> list[dict]:
    """结果文档 → 每组 {key, pick, same, diff, unclear, judged, n_tiles, rate(同字/已判)}。只认已确认的。"""
    from . import results
    out = []
    for d in results.flatten(docs).values():
        marks = d.get("marks") or {}
        s = sum(1 for v in marks.values() if v == "same")
        f = sum(1 for v in marks.values() if v == "diff")
        u = sum(1 for v in marks.values() if v == "unclear")
        j = s + f
        out.append({"key": d.get("key", d.get("id")), "pick": d.get("pick"), "same": s, "diff": f, "unclear": u,
                    "judged": j, "n_tiles": d.get("n_tiles", len(marks)), "rate": (s / j) if j else None,
                    "note": d.get("note") or ""})
    return sorted(out, key=lambda r: str(r["key"]))


def whitelist(rows: list[dict], min_rate: float = 1.0, min_judged: int = 30) -> dict:
    """可入白名单＝组结论「同字」、已判格数够、同字率不低于门槛、没有「不同字」标记（门槛为 1.0 时）。
    返回 {ok:[组], hold:[(组, 原因)]}。门槛由人定，默认最严（30 格全同字）。"""
    ok, hold = [], []
    for r in rows:
        why = None
        if r["pick"] != "同字":
            why = f"组结论是 {r['pick'] or '未定'}"
        elif r["judged"] < min_judged:
            why = f"只判了 {r['judged']} 格（要 ≥{min_judged}）"
        elif r["rate"] is None or r["rate"] < min_rate:
            why = f"同字率 {r['rate']:.0%}（要 ≥{min_rate:.0%}）" if r["rate"] is not None else "无已判格"
        (hold.append((r["key"], why)) if why else ok.append(r["key"]))
    return {"ok": ok, "hold": hold}
