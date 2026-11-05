"""轮报告生成器（T7）：一键出「轮单」——本轮 vs 上一轮，按册、按列对比，回退清单，pending_reason 分布。

输入是两个 `guji-manager pending-stats` 的输出目录（各含 summary.json、cells.tsv）：

  guji-manager iterate round-report --cur out/r5 --prev out/r4 --label r5 --prev-label r4 --out out/r5-report
  # 可选：--released released.tsv（vol,cell 两列：本轮 L2/L3 已放行、不再排给人的格，用来算「净人审队列」）

输出（--out）：report.md（给人看）、by_vol.tsv、by_col.tsv、by_reason.tsv、regress.tsv（新增待审格＝回退清单）。
退出码：0 正常；2 有红灯（见 verdict），脚本里可据此拦标 main。

口径：
  首审人审率＝待审÷全册格（正文格，沿用 pending-stats，非正文页另列）；
  净人审队列＝待审 − 单列项（hard_pair、occluded_no_ref，留后/人审底）− --released 给的已放行格。
「回退」＝本轮待审、上一轮不在待审的格（格号一致的才能比；格号变了的册标 ⚠️ 变列，须逐册人工比，S 轮用）。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .common import cell_key, col_of, read_tsv, write_tsv

#: 不排给人、单列的原因（框架第二节：hard_pair 留后，occluded_no_ref 人审底）
SEPARATE = ("hard_pair", "occluded_no_ref")
#: 红灯阈值：回退格占上一轮待审的比例；册内格号集合重合率
REGRESS_RED, REGRESS_YELLOW = 0.05, 0.02
GRID_OVERLAP_MIN = 0.9


def load(d: Path) -> tuple[dict, list[dict]]:
    s = json.loads((d / "summary.json").read_text(encoding="utf-8"))
    rows = [r for r in read_tsv(d / "cells.tsv") if r.get("kind", "body") == "body"]
    return s, rows


def _pct(x) -> str:
    return "—" if x is None else f"{x * 100:.3f}%"


def _d(now: int, prev: int | None) -> str:
    if prev is None:
        return ""
    d = now - prev
    return f"（{'+' if d > 0 else ''}{d}）"


def compare(cur_dir: Path, prev_dir: Path, released: set | None = None) -> dict:
    cs, crows = load(cur_dir)
    ps, prows = load(prev_dir)
    ckeys = {cell_key(r): r for r in crows}
    pkeys = {cell_key(r): r for r in prows}
    regress = [ckeys[k] for k in ckeys if k not in pkeys]
    fixed = [pkeys[k] for k in pkeys if k not in ckeys]
    changed_reason = [(k, pkeys[k]["pending_reason"], ckeys[k]["pending_reason"]) for k in ckeys
                      if k in pkeys and pkeys[k]["pending_reason"] != ckeys[k]["pending_reason"]]

    cells_total = sum((v.get("cells") or 0) for v in cs["vols"].values())
    prev_total = sum((v.get("cells") or 0) for v in ps["vols"].values())
    n, pn = len(crows), len(prows)
    sep = sum(1 for r in crows if r["pending_reason"] in SEPARATE)
    rel = sum(1 for k in ckeys if released and k in released)
    net = n - sep - rel

    # 按册
    by_vol = []
    for v in sorted(set(cs["vols"]) | set(ps["vols"])):
        c, p = cs["vols"].get(v), ps["vols"].get(v)
        cset = {k[1] for k in ckeys if k[0] == v.zfill(3)}
        pset = {k[1] for k in pkeys if k[0] == v.zfill(3)}
        reg = sum(1 for k in ckeys if k[0] == v.zfill(3) and k not in pkeys)
        by_vol.append({"vol": v, "prev": p["n"] if p else "", "cur": c["n"] if c else "",
                       "delta": (c["n"] - p["n"]) if (c and p) else "", "cells": c.get("cells") if c else "",
                       "rate": c["n"] / c["cells"] if c and c.get("cells") else "",
                       "regress": reg, "fixed": sum(1 for k in pkeys if k[0] == v.zfill(3) and k not in ckeys),
                       "rev": (c or {}).get("rev", ""), "prev_rev": (p or {}).get("rev", ""),
                       "cv": (c or {}).get("cv", ""), "prev_cv": (p or {}).get("cv", "")})
    # 按列
    ccol, pcol = Counter(), Counter()
    for k in ckeys:
        ccol[(k[0], col_of(k[1]))] += 1
    for k in pkeys:
        pcol[(k[0], col_of(k[1]))] += 1
    by_col = []
    for key in set(ccol) | set(pcol):
        by_col.append({"vol": key[0], "col": key[1], "prev": pcol[key], "cur": ccol[key], "delta": ccol[key] - pcol[key]})
    by_col.sort(key=lambda r: (-r["delta"], r["vol"], r["col"]))
    # 按原因
    reasons = []
    cr, pr = Counter(r["pending_reason"] for r in crows), Counter(r["pending_reason"] for r in prows)
    for k in sorted(set(cr) | set(pr), key=lambda x: -cr[x]):
        reasons.append({"reason": k, "prev": pr[k], "cur": cr[k], "delta": cr[k] - pr[k]})
    # 格号是否一致：上一轮的待审格有多少在本轮的册里还「存在」不可知（库里无全格表），只能看待审格号重合率
    grid = {}
    for v in cs["vols"]:
        a = {k[1] for k in ckeys if k[0] == v.zfill(3)}
        b = {k[1] for k in pkeys if k[0] == v.zfill(3)}
        if a and b:
            grid[v] = len(a & b) / min(len(a), len(b))
    drift = sorted(v for v, x in grid.items() if x < GRID_OVERLAP_MIN)

    red, yellow = [], []
    if pn:
        ratio = len(regress) / pn
        if ratio >= REGRESS_RED:
            red.append(f"回退格 {len(regress)} 占上一轮待审 {ratio * 100:.1f}% ≥{REGRESS_RED * 100:.0f}%：先查回退，不标 main")
        elif ratio >= REGRESS_YELLOW:
            yellow.append(f"回退格 {len(regress)} 占上一轮待审 {ratio * 100:.1f}% ≥{REGRESS_YELLOW * 100:.0f}%：看回退清单是否集中在少数列")
    if drift:
        yellow.append(f"待审格号与上一轮重合率 <{GRID_OVERLAP_MIN * 100:.0f}% 的册：{','.join(drift)}（可能变列；S 轮标 main 前须逐册比格号，通知 A33/A23/A30/A20）")
    if cs.get("n_nonbody", 0) != ps.get("n_nonbody", 0):
        yellow.append(f"非正文页待审格数变了（{ps.get('n_nonbody', 0)}→{cs.get('n_nonbody', 0)}）：核页型配置")
    if n > pn:
        yellow.append(f"待审总数反升 {pn}→{n}")
    return {"n": n, "prev_n": pn, "cells_total": cells_total, "prev_cells_total": prev_total, "sep": sep, "released": rel, "net": net,
            "regress": regress, "fixed_n": len(fixed), "changed_reason": changed_reason, "by_vol": by_vol, "by_col": by_col,
            "reasons": reasons, "drift": drift, "red": red, "yellow": yellow}


#: 收口单归宿（框架第九节）：人审底／留后／点校待办／精校待办
CLOSING = {"occluded_no_ref": "人审底", "hard_pair": "留后（交点校 A33 出裁定表）", "seg_defect": "人审底（断烂图源）"}


def closing_rows(res: dict) -> list[dict]:
    out = []
    for r in res["reasons"]:
        dest = CLOSING.get(r["reason"], "精校待办")
        out.append({"reason": r["reason"], "n": r["cur"], "dest": dest, "dianjiao": r["cur"] if r["reason"] == "hard_pair" else 0})
    return out


def notify_a33(res: dict, label: str, kind: str, packs: dict) -> str:
    """通知点校的消息（ai-team 通用/重跑轮次规矩.md「通知点校」）：S 轮标 main 前，D 轮标 main 后。"""
    L = [f"【A31→A33】{kind}轮 {label} 出口（{'标 main 前，请先 auto_remap 并回执' if kind == 'S' else '标 main 后，请批量 punct_redo'}）"]
    for r in sorted(res["by_vol"], key=lambda r: r["vol"]):
        old, new = packs.get(r["vol"], (r["prev_rev"] or "?", r["rev"] or "?"))
        drift = "变" if (kind == "S" and r["vol"].zfill(3) in {v.zfill(3) for v in res["drift"]}) else ("不变" if kind == "D" or r["vol"] not in res["drift"] else "变")
        L.append(f"{r['vol']} {old} → {new} 格号:{drift}")
    if kind == "S":
        L.append("注：格号「变」由待审格号重合率 <90% 推断，只是线索；以 auto_remap 实比为准，重合率高也可能列数变了。")
    return "\n".join(L) + "\n"


def render(res: dict, label: str, prev_label: str, top: int = 15) -> str:
    n, pn, ct, pct = res["n"], res["prev_n"], res["cells_total"], res["prev_cells_total"]
    L = [f"# 轮报告 {label}（对比 {prev_label}）", ""]
    verdict = "🔴 红灯" if res["red"] else "🟡 黄灯" if res["yellow"] else "🟢 绿灯"
    L += [f"**{verdict}**", ""]
    for x in res["red"]:
        L.append(f"- 🔴 {x}")
    for x in res["yellow"]:
        L.append(f"- 🟡 {x}")
    L += ["", "## 一、两个数", "",
          "| | 本轮 | 上一轮 |", "|---|---|---|",
          f"| 待审格（正文） | {n}{_d(n, pn)} | {pn} |",
          f"| **首审人审率** | {_pct(n / ct if ct else None)} | {_pct(pn / pct if pct else None)} |",
          f"| 单列（hard_pair＋occluded_no_ref） | {res['sep']} | |",
          f"| 已放行不排给人（--released） | {res['released']} | |",
          f"| **净人审队列** | {res['net']}（{_pct(res['net'] / ct if ct else None)}） | |", "",
          f"回退（本轮待审、上一轮不在）**{len(res['regress'])}** 格；上一轮待审本轮已清 **{res['fixed_n']}** 格；原因改判 {len(res['changed_reason'])} 格。", "",
          "## 二、按待审原因", "", "| pending_reason | 上一轮 | 本轮 | 增减 |", "|---|---|---|---|"]
    for r in res["reasons"]:
        L.append(f"| `{r['reason']}` | {r['prev']} | {r['cur']} | {'+' if r['delta'] > 0 else ''}{r['delta']} |")
    L += ["", "## 三、按册（增减最大 / 有回退的册优先）", "", "| 册 | 上轮 | 本轮 | 增减 | 回退 | 清掉 | 人审率 | cv 上轮→本轮 | 册配置 rev |", "|---|---|---|---|---|---|---|---|---|"]
    vols = sorted(res["by_vol"], key=lambda r: (-(r["regress"] or 0), -(r["delta"] if isinstance(r["delta"], int) else 0)))
    for r in vols[:top]:
        L.append(f"| {r['vol']} | {r['prev']} | {r['cur']} | {r['delta']} | {r['regress']} | {r['fixed']} | {_pct(r['rate'] or None)} | {r['prev_cv']}→{r['cv']} | {r['rev']} |")
    if len(vols) > top:
        L.append(f"| … | 另 {len(vols) - top} 册见 by_vol.tsv | | | | | | | |")
    L += ["", "## 四、按列（待审增加最多的列；整列回退多半是切分变了）", "", "| 册 | 页:列 | 上轮 | 本轮 | 增减 |", "|---|---|---|---|---|"]
    for r in [c for c in res["by_col"] if c["delta"] > 0][:top]:
        L.append(f"| {r['vol']} | {r['col']} | {r['prev']} | {r['cur']} | +{r['delta']} |")
    L += ["", "## 五、回退清单（前若干；全表 regress.tsv）", "", "| 册 | 格 | pending_reason |", "|---|---|---|"]
    for r in res["regress"][:top]:
        L.append(f"| {r['vol']} | {r['cell']} | `{r['pending_reason']}` |")
    if not res["regress"]:
        L.append("| （无） | | |")
    L += ["", "## 六、收口单草稿（含「点校待办」栏）", "", "| pending_reason | 格数 | 归宿 | 点校待办 |", "|---|---|---|---|"]
    for c in closing_rows(res):
        L.append(f"| `{c['reason']}` | {c['n']} | {c['dest']} | {c['dianjiao'] or ''} |")
    L += ["", "> 回退只说明「本轮新进待审」，不等于错：先看是不是集中在少数列/页（切分变了），再看对应修复的预期影响。"
          "放行字变（上一轮放行、本轮改字）与人裁丢失须另用 A/B 回归核（框架 8.2 步 3、验收标准），本表不含。", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cur", type=Path, required=True, help="本轮 pending-stats 输出目录")
    ap.add_argument("--prev", type=Path, required=True, help="上一轮 pending-stats 输出目录")
    ap.add_argument("--label", default="本轮")
    ap.add_argument("--prev-label", default="上一轮")
    ap.add_argument("--released", type=Path, help="tsv（vol,cell）：本轮已放行、不排给人的格，用来算净队列")
    ap.add_argument("--round-kind", choices=("S", "D"), help="给了就同时生成通知 A33 的消息 notify_A33.txt（S 轮标 main 前发，D 轮标 main 后发）")
    ap.add_argument("--packs", type=Path, help="tsv（vol,old_pack,new_pack）：通知里写包标签；缺省写 summary 里的 rev")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    released = {cell_key(r) for r in read_tsv(a.released)} if a.released else None
    res = compare(a.cur, a.prev, released)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "report.md").write_text(render(res, a.label, a.prev_label, a.top), encoding="utf-8")
    write_tsv(a.out / "by_vol.tsv", list(res["by_vol"][0].keys()) if res["by_vol"] else ["vol"], res["by_vol"])
    write_tsv(a.out / "by_col.tsv", ["vol", "col", "prev", "cur", "delta"], res["by_col"])
    write_tsv(a.out / "by_reason.tsv", ["reason", "prev", "cur", "delta"], res["reasons"])
    write_tsv(a.out / "regress.tsv", ["vol", "cell", "pending_reason", "big", "sub", "owner"], res["regress"])
    if a.round_kind:
        packs = {cell_key(x)[0]: (x["old_pack"], x["new_pack"]) for x in read_tsv(a.packs)} if a.packs else {}
        (a.out / "notify_A33.txt").write_text(notify_a33(res, a.label, a.round_kind, packs), encoding="utf-8")
    print(f"待审 {res['prev_n']}→{res['n']}，净队列 {res['net']}，回退 {len(res['regress'])}，清掉 {res['fixed_n']} → {a.out}/report.md"
          + ("  🔴" if res["red"] else "  🟡" if res["yellow"] else "  🟢"))
    return 2 if res["red"] else 0


if __name__ == "__main__":
    sys.exit(main())
