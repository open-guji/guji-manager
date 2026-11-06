"""杠杆排序（T3）：给待审格/字对打分，决定人审点选页的出卡顺序（框架 5.2）。

输入 `pending-stats` 的 cells.tsv（需带 ref、top 两列；旧输出没有则退化为只按 pending_reason 分组）：

  guji-manager iterate leverage --cells out/r5/cells.tsv --out out/r5/leverage [--top 200] [--book sj]

一张「卡」＝一组同类格：同 pending_reason＋同一对（参校本字, 库首位字）；按下面顺序排：
  tier 0  第一次进库的字（lib_missing、lib_sparse_agree）——用户 11-03 定必须人裁，同字全书一卡；
  tier 1  其他会走人审的原因（route=human，或 llm 被大模型留回的）按分数；
  tier 2  单列/底线（hard_pair、occluded_no_ref 归留人审、unknown）放最后，不出点选页，只在报告里列。
分数 score＝同对格数 ＋ 2×(涉及册数−1)（一次确认能放掉多册）＋ 同字头在全书的总格数×0.1。
输出：leverage.tsv（rank,tier,reason,ref,top,n_cells,n_vols,score,sample_cells）、cards.tsv（每格归哪张卡，人审页按卡取格）、report.md。
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .common import cell_key, read_tsv, write_tsv

FIRST_ENTRY = ("lib_missing", "lib_sparse_agree")
BOTTOM = ("hard_pair", "occluded_no_ref", "unknown")


def _routes() -> dict:
    try:
        from ..review.pending_reason import specs
        return {k.value: v.route.value for k, v in specs().items()}
    except Exception:   # noqa: BLE001 没有配置也能跑
        return {}


def tier_of(reason: str, routes: dict) -> int:
    if reason in FIRST_ENTRY:
        return 0
    if reason in BOTTOM or routes.get(reason) == "deferred":
        return 2
    return 1


def rank(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    routes = _routes()
    rows = [r for r in rows if r.get("kind", "body") == "body"]
    head_total = Counter()
    for r in rows:
        h = r.get("ref") or r.get("top") or ""
        if h:
            head_total[h] += 1
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["pending_reason"], r.get("ref") or "", r.get("top") or "")].append(r)
    cards = []
    for (reason, ref, top), rs in groups.items():
        vols = {cell_key(r)[0] for r in rs}
        head = ref or top
        score = len(rs) + 2 * (len(vols) - 1) + (head_total[head] * 0.1 if head else 0)
        cards.append({"tier": tier_of(reason, routes), "reason": reason, "ref": ref, "top": top, "n_cells": len(rs),
                      "n_vols": len(vols), "score": round(score, 1),
                      "sample_cells": ";".join(f"{cell_key(r)[0]}:{r['cell']}" for r in sorted(rs, key=cell_key)[:3]), "_rs": rs})
    cards.sort(key=lambda c: (c["tier"], -c["score"], c["reason"], c["ref"], c["top"]))
    cell_rows = []
    for i, c in enumerate(cards, 1):
        c["rank"] = i
        for r in c.pop("_rs"):
            cell_rows.append({"rank": i, "vol": cell_key(r)[0], "cell": r["cell"], "pending_reason": c["reason"], "ref": c["ref"], "top": c["top"], "tier": c["tier"]})
    return cards, cell_rows


def render(cards: list[dict], top: int) -> str:
    n = sum(c["n_cells"] for c in cards)
    by_tier = Counter()
    for c in cards:
        by_tier[c["tier"]] += c["n_cells"]
    L = ["# 杠杆排序", "", f"共 {len(cards)} 张卡、{n} 格。第一次进库 {by_tier[0]} 格（tier 0）；其他走人审 {by_tier[1]} 格（tier 1）；底线/留后 {by_tier[2]} 格（tier 2，不出点选页）。", "",
         "| # | tier | 原因 | 参校本字 | 库首位 | 格数 | 册数 | 分 | 样例 |", "|---|---|---|---|---|---|---|---|---|"]
    for c in cards[:top]:
        L.append(f"| {c['rank']} | {c['tier']} | `{c['reason']}` | {c['ref']} | {c['top']} | {c['n_cells']} | {c['n_vols']} | {c['score']} | {c['sample_cells']} |")
    # 累计覆盖：前 k 张卡放掉多少格，帮助估人审工时
    acc, marks = 0, []
    for c in cards:
        if c["tier"] == 2:
            break
        acc += c["n_cells"]
        if c["rank"] in (10, 20, 50, 100):
            marks.append(f"前 {c['rank']} 张卡覆盖 {acc} 格")
    if marks:
        L += ["", "累计覆盖：" + "；".join(marks) + "。"]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cells", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--top", type=int, default=100)
    a = ap.parse_args(argv)
    rows = read_tsv(a.cells)
    if rows and "ref" not in rows[0]:
        print("提示：cells.tsv 没有 ref/top 列（旧版 pending-stats），只能按 pending_reason 分组", file=sys.stderr)
    cards, cell_rows = rank(rows)
    a.out.mkdir(parents=True, exist_ok=True)
    write_tsv(a.out / "leverage.tsv", ["rank", "tier", "reason", "ref", "top", "n_cells", "n_vols", "score", "sample_cells"], cards)
    write_tsv(a.out / "cards.tsv", ["rank", "vol", "cell", "pending_reason", "ref", "top", "tier"], cell_rows)
    (a.out / "report.md").write_text(render(cards, a.top), encoding="utf-8")
    print(f"{len(cards)} 张卡 / {len(cell_rows)} 格 → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
