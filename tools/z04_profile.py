#!/usr/bin/env python
"""Z04 `group_ref_dissent`（与参校本不同）体检：一本书★main 包里哪些格是 Z04、分哪几类、哪个解法给的字。
新书开工后跑一遍，得到 doc/01-粗校/待审原因/group_ref_dissent/README.md 第六节的体检信号。只读，不写产物包、不写中心库。

    python tools/z04_profile.py --ws <工作区目录> --text <中心库文本号> --out /tmp/z04 [--vols vol20,vol44] [--jobs 4]
        [--gold Z04-逐格-三书147格.tsv]   # 可选：带目视金标，另算拦对率

前提（同 pending-stats／l01_profile）：环境里有 GUJI_DATA_TOKEN（读令牌够）、GUJI_DATA_HOME，工作区目录只放
workspace.yaml 与 .central.json；要装 open-guji-cv。分类口径随 `reasons.py` 当前版本走，所以改了 Z 类定义后重跑就是新口径。

结构分类（参校字相对这一组，互斥）：
  组外字    参校字不是组员也不是陪衬字（#1189 coord_outside_skip 之后只剩现役对位的少数格）
  陪衬字    参校字在组的 tolerate 里（蒙 的 䝉／家，寶 的 寳…）
  组内另一字 参校字是本组另一个字（字形细部之争：门族、入人八、于千子干、而面…）
输出：`cells.tsv`（每个 Z04 格一行）、`summary.json`、`report.md`。
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from guji_manager._cv import connect
from guji_manager.pending_stats import nonbody_of_yaml
from guji_manager.review.reasons import book_cells, reasons_for_pending

Z04 = "group_ref_dissent"
GAP = "〓"


def _run(*a):
    return subprocess.run(a, capture_output=True, text=True)


def _kind(g: str, ref: str | None) -> str:
    from open_guji_cv.groups.registry import FLOW_GROUPS as G
    if ref in (None, "", GAP):
        return "参校字缺（〓）"
    spec = G[g]
    if ref in spec.members:
        return "组内另一字"
    if ref in set(spec.flow.tolerate or ()):
        return "陪衬字"
    return "组外字"


def _vol(ws: str, wsdir: str, v: str, out: Path, nb: dict) -> dict:
    L = [l.split("\t") for l in _run("guji", "products", "pack", "list", v, "-w", wsdir).stdout.splitlines()
         if l.lstrip().startswith("★")]
    if not L:
        return {"vol": v, "skip": "no main"}
    lab = L[0][0].split("/")[-1].strip()
    tmp = out / "tmp" / v
    shutil.rmtree(tmp, ignore_errors=True)
    _run("guji", "products", "pack", "fetch", v, "-w", wsdir, "--label", lab, "--to", str(tmp))
    root = tmp if (tmp / v / "seed_admit").is_dir() else tmp.parent
    if not (root / v / "seed_admit").is_dir():
        return {"vol": v, "skip": "fetch failed", "label": lab}
    cells = book_cells(str(root), v)
    keys = [c for c in cells if c.split(":")[0].lstrip("0") not in (nb.get(v) or {})]
    rs = reasons_for_pending({"cells": [{"cell": c} for c in keys]}, str(root), v)
    rows = []
    for cid, (r, _) in rs.items():
        if r.value != Z04:
            continue
        c = cells[cid]
        g = c.group or {}
        sol = [s for s in g.get("solvers") or [] if s.get("char")]
        rows.append(dict(vol=v, cell=cid, group=g.get("id"), why=str(g.get("why", "")).split(":")[0], mode=g.get("mode"),
                         decision=g.get("decision"), ref=c.ref, ref_op=c.ref_op, kind=_kind(g.get("id"), c.ref),
                         given="/".join(sorted({s["char"] for s in sol})),
                         by="+".join(sorted(s["solver"] for s in sol)), cands=" ".join(f"{x}{y:.3f}" for x, y in c.cands[:3]),
                         pack=lab))
    shutil.rmtree(tmp, ignore_errors=True)
    return {"vol": v, "label": lab, "pending": len(keys), "z04": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws", required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--vols")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--gold")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        cur = con.cursor()
        cur.execute("select book, raw from books where ws=%s order by book", (a.text,))
        rows = cur.fetchall()
    vols = [b for b, _ in rows]
    nb = {b: nonbody_of_yaml(r) for b, r in rows}
    if a.vols:
        vols = [v for v in vols if v in set(a.vols.split(","))]
    with ThreadPoolExecutor(a.jobs) as ex:
        res = list(ex.map(lambda v: _vol(a.text, a.ws, v, out, nb), vols))
    cells = [x for r in res for x in r.get("z04", [])]
    pending = sum(r.get("pending", 0) for r in res)
    with open(out / "cells.tsv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(cells[0]) if cells else ["vol"], delimiter="\t")
        w.writeheader()
        w.writerows(cells)
    C = collections.Counter
    summ = {"pending": pending, "z04": len(cells), "why": C(x["why"] for x in cells), "mode": C(x["mode"] for x in cells),
            "kind": C(x["kind"] for x in cells), "group": C(x["group"] for x in cells).most_common(15),
            "by": C(x["by"] for x in cells), "old_pack": sum(1 for x in cells if x["pack"].startswith("cv0.5"))}
    lines = [f"# Z04 体检（{a.text}）", "", f"待审 {pending} 格，Z04 {len(cells)} 格（{len(cells) / max(pending, 1):.1%}）；"
             f"其中 cv<0.6 旧包 {summ['old_pack']} 格（重跑自消）。", ""]
    for k in ("why", "mode", "kind", "by"):
        lines += [f"## 按 {k}", "", "| 值 | 格 |", "|---|---:|"] + [f"| {x} | {n} |" for x, n in summ[k].most_common()] + [""]
    lines += ["## 字组 top15", "", "| 组 | 格 |", "|---|---:|"] + [f"| {x} | {n} |" for x, n in summ["group"]] + [""]
    if a.gold:
        gold = {(r["册"], r["格"], r["字组"]): r["目视初判"] for r in csv.DictReader(open(a.gold, encoding="utf-8"), delimiter="\t")}
        hit = [gold.get((x["vol"], x["cell"], x["group"])) for x in cells]
        d = C(h for h in hit if h)
        dec = d["r"] + d["g"]
        lines += ["## 拦对率（金标里可判格）", "", f"命中金标 {sum(d.values())}/{len(cells)} 格；图上是参校字 {d['r']}、是给字 {d['g']}、"
                  f"拦对率 {d['r'] / dec:.0%}" if dec else "金标里没有可判格", ""]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
