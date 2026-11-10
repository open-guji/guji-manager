#!/usr/bin/env python
"""L05 `garble_gate`（像框线或墨点）体检：一本书（或几册）★main 包里哪些格是 L05、分哪几类、
`rare_ref_coord_min_cov`／`rare_ref_coord_group_top` 改了能放多少。新书开工后跑一遍，得到
doc/01-粗校/待审原因/garble_gate/benchmark.md 里的指标表。只读，不写产物包、不写中心库。

    python tools/l05_profile.py --ws <工作区目录> --text <中心库文本号> --out /tmp/l05 [--vols vol20,vol44] [--jobs 4]
        [--min-cov 0.85] [--no-group-top]     # 离线回放用的参数；缺省 0.85、group_top 开

前提（同 pending-stats / l01_profile）：环境里有 GUJI_DATA_TOKEN（读令牌够）与 GUJI_DATA_HOME，工作区目录只放
workspace.yaml 与 .central.json，先 `guji db pull -w <ws>` 拉字形库（output/glyph.db）；要装 open-guji-cv。

分类（互斥，按顺序）：
  C   整理本这一位没字（无对位）：框线碎片、并格、圈点○、整字没对位——只能人审，与切分类重叠
  A1  整理本字＝5b 首位，把 coord_min_cov 放到 --min-cov 即可由 rare_ref 坐标支放行
  A2  同上，但还要开 rare_ref_coord_group_top（库首位是字组成员，如 刪／冊／衛／王）
  A3  整理本字＝5b 首位，但被别的护栏挡下（shadow_veto、整理本字在字组、near_form 等硬疑问、整页无现役对位、有现役对位…）
  B   有整理本字，5b 首位不是它
输出：`cells.tsv`（每个 L05 格一行）、`summary.json`、`report.md`。
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from guji_manager._cv import connect
from guji_manager.pending_stats import nonbody_of_yaml
from guji_manager.review.reasons import _load_layer, align_for_seed, book_cells, reasons_for_pending

K = 8   # 上下文各取几字
GARBLE = "garble_gate"


def _run(*a, **kw):
    return subprocess.run(a, capture_output=True, text=True, **kw)


def _layer(root: Path, name: str, key: str, pg: str) -> dict:
    return _load_layer(root / name / pg, key) or {}


def _page_facts(root: Path, f: Path):
    """一页：按阅读序的格序列、现役对位、坐标对位、整页现役对位条数。夹注两列先读完 a 再读 b。"""
    seed = _load_layer(f, "seed_admit") or {}
    align = align_for_seed(seed, _load_layer(root / "align_ref" / f.name, "align_ref")) or {}
    cur = {c["id"]: c.get("align_char") for c in align.get("chars", [])}
    coord = {c["id"]: c["ref_char"] for c in align.get("coord") or [] if c.get("ref_char")}
    seq = []
    for col in seed.get("columns", []):
        block = []
        for ch in col.get("chars", []) + [None]:
            if ch is not None and "excluded" in (ch.get("doubts") or []):
                continue
            if ch is not None and ch.get("sub"):
                block.append(ch)
                continue
            if block:
                seq += [c for c in block if c.get("sub") == "a"] + [c for c in block if c.get("sub") != "a"]
                block = []
            if ch is not None:
                seq.append(ch)
    return seq, cur, coord, len(align.get("chars", []))


def _rows_of(v: str, root: Path, gdb: str, nonbody: dict) -> tuple[dict, list[dict]]:
    cells = book_cells(root, v)
    keys = [c for c in cells if c.split(":")[0].lstrip("0") not in nonbody]
    rs = reasons_for_pending({"cells": [{"cell": c} for c in keys]}, root, v, glyph_db=gdb)
    by = collections.Counter(r.value for r, _ in rs.values())
    want = {c for c, (r, _) in rs.items() if r.value == GARBLE}
    rows = []
    for f in sorted((root / v / "seed_admit").glob("p*.json")):
        if not any(k.startswith(f"{int(f.stem[1:])}:") for k in want):
            continue
        seq, cur, coord, n_align = _page_facts(root / v, f)
        txt = [(ch.get("char") if ch.get("admit") else None) or cur.get(ch["id"]) or coord.get(ch["id"]) or "□" for ch in seq]
        gm = {c["id"]: c for col in _layer(root / v, "glyph_match", "glyph_match", f.name).get("columns", []) for c in col.get("chars", [])}
        rc = {}
        for col in _layer(root / v, "rare_candidates", "rare_candidates", f.name).get("columns", []):
            for c in col.get("chars") or col.get("cells") or []:
                rc[c["id"]] = [x["char"] for x in c.get("candidates", [])]
        cs = _layer(root / v, "cell_shrink", "char_index", f.name)
        step3 = {}
        for key in ("columns", "alt_columns"):
            for col in cs.get(key, []) or []:
                for ch in col.get("chars", []):
                    step3.setdefault(ch["id"], ch.get("step3_kind"))
        for i, ch in enumerate(seq):
            key = ch["id"].split(":", 1)[1]
            if key not in want:
                continue
            c = cells[key]
            g = gm.get(ch["id"]) or {}
            rare = rc.get(ch["id"]) or []
            rows.append(dict(
                vol=v, cell=key, page=f.name, ref=c.ref or "", char=c.char or "", top=c.top or "", cov=g.get("cov"),
                verdict=g.get("verdict"), guard=(c.evidence or {}).get("guard"),
                cands=json.dumps([[x[0], x[1]] for x in (g.get("candidates") or [])], ensure_ascii=False),
                rare_top=rare[0] if rare else "", ref_in_5b=(rare.index(c.ref) + 1 if c.ref in rare else 0),
                cur=cur.get(ch["id"]) or "", coord=coord.get(ch["id"]) or "", page_n_align=n_align,
                jiazhu=int(step3.get(ch["id"]) == "jiazhu"),
                doubts=",".join(str(d) for d in c.doubts),
                left="".join(txt[max(0, i - K):i]), right="".join(txt[i + 1:i + 1 + K])))
    return {"vol": v, "pending": len(keys), "by": dict(by)}, rows


def _lib_n(gdb: str):
    import sqlite3
    con = sqlite3.connect(f"file:{gdb}?mode=ro", uri=True)
    n = collections.Counter()
    for ch, k in con.execute("select char, sum(n_confirmed) from glyphs group by char"):
        n[ch] += k or 0
    con.close()
    return n


def _classify(rows: list[dict], min_cov: float, group_top: bool) -> None:
    """给每行加 cls／sub／ref_in_group／top_in_group；用 cv 线上同一批纯函数回放 rare_ref 坐标支。"""
    from open_guji_cv.groups.registry import GROUPS
    from open_guji_cv.steps.seed_admit import _hard_blocked, _rare_ref_coord_ok, rare_ref_decide
    from open_guji_cv.variants import are_variants
    gid = collections.defaultdict(list)
    for k, g in GROUPS.items():
        for c in g.members:
            gid[c].append(k)
    gc = frozenset(gid)

    def ok(r, mc, gt):
        if not r["ref"] or not r["page_n_align"]:      # 整页无现役对位：线上不跑坐标支（seed_admit `and amap`）
            return False
        cands = [(c[0], c[1]) for c in json.loads(r["cands"])]
        doubts = r["doubts"].split(",") if r["doubts"] else []
        if not _rare_ref_coord_ok(r["ref"], r["top"], cands, doubts, 3, are_variants, gc, r["cov"] or 0, mc, gt):
            return False
        return bool(rare_ref_decide(doubts=doubts, guard=r["guard"], verdict=r["verdict"], lib_char=None, lib_top=r["top"],
                                    ref=r["ref"], op="replace", rare_top=r["rare_top"], are_variants=are_variants))

    for r in rows:
        r["ref_in_group"] = ",".join(gid.get(r["ref"], [])) if r["ref"] else ""
        r["top_in_group"] = ",".join(gid.get(r["top"], []))
        r["sub"] = ""
        if not r["ref"]:
            r["cls"] = "C"
        elif ok(r, min_cov, False):
            r["cls"] = "A1"
        elif group_top and ok(r, min_cov, True):
            r["cls"] = "A2"
        elif r["rare_top"] == r["ref"]:
            r["cls"] = "A3"
            doubts = r["doubts"].split(",") if r["doubts"] else []
            why = []
            if r["ref"] in gc:
                why.append("整理本字在字组")
            if any(d.startswith(("group_flow", "shadow_veto")) for d in doubts):
                why.append("shadow_veto")
            if _hard_blocked(doubts, r["guard"]):
                why.append("硬疑问")
            if r["cur"]:
                why.append("有现役对位")
            if not r["page_n_align"]:
                why.append("整页无现役对位")
            if r["cov"] is not None and r["cov"] < min_cov:
                why.append(f"cov<{min_cov}")
            r["sub"] = "+".join(why) or "其它"
        else:
            r["cls"] = "B"
            r["sub"] = "5b无" if not r["ref_in_5b"] else ("5b第2-3" if r["ref_in_5b"] <= 3 else "5b第4+")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ws", required=True, help="工作区目录（含 .central.json，已 db pull）")
    ap.add_argument("--text", required=True, help="中心库文本号（books 表的 ws）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--vols")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--min-cov", type=float, default=0.85, help="离线回放的 rare_ref_coord_min_cov（线上缺省 0.90）")
    ap.add_argument("--no-group-top", action="store_true", help="回放时不开 rare_ref_coord_group_top")
    ap.add_argument("--db", help="字形库 glyph.db 路径（缺省 <ws>/output/glyph.db）")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    gdb = a.db or str(Path(a.ws) / "output" / "glyph.db")
    if not Path(gdb).exists():
        sys.exit(f"没有 {gdb}：先 `guji db pull -w {a.ws}`")
    with connect() as con:
        cur = con.cursor()
        cur.execute("select book, raw from books where ws=%s order by book", (a.text,))
        books = {b: nonbody_of_yaml(r) for b, r in cur.fetchall()}
    vols = [v for v in books if not a.vols or v in a.vols.split(",")]

    def go(v):
        lst = [l.split("\t") for l in _run("guji", "products", "pack", "list", v, "-w", a.ws).stdout.splitlines()
               if l.lstrip().startswith("★")]
        if not lst:
            return {"vol": v, "skip": "no main"}, []
        lab = lst[0][0].split("/")[-1].strip()
        tmp = out / "tmp" / v
        shutil.rmtree(tmp, ignore_errors=True)
        _run("guji", "products", "pack", "fetch", v, "-w", a.ws, "--label", lab, "--to", str(tmp))
        root = tmp if (tmp / v / "seed_admit").is_dir() else tmp.parent
        try:
            if not (root / v / "seed_admit").is_dir():
                return {"vol": v, "skip": "fetch failed"}, []
            s, rows = _rows_of(v, root, gdb, books.get(v) or {})
            s["label"] = lab
            return s, rows
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    with ThreadPoolExecutor(a.jobs) as ex:
        res = list(ex.map(go, vols))
    stats = [s for s, _ in res]
    rows = [r for _, rs in res for r in rs]
    n = _lib_n(gdb)
    for r in rows:
        r["ref_lib_n"] = n.get(r["ref"], 0) if r["ref"] else ""
    _classify(rows, a.min_cov, not a.no_group_top)
    pend = sum(s.get("pending", 0) for s in stats)
    by_all = collections.Counter()
    for s in stats:
        by_all.update(s.get("by", {}))
    cls = collections.Counter(r["cls"] for r in rows)
    withref = [r for r in rows if r["ref"]]
    covs = sorted(r["cov"] for r in rows if r["cov"] is not None)

    def q(p):
        return round(covs[min(len(covs) - 1, int(len(covs) * p))], 3) if covs else None

    summary = {
        "text": a.text, "vols_total": len(vols), "vols_with_main": sum(1 for s in stats if "skip" not in s),
        "pending": pend, "l05": len(rows), "l05_share": round(len(rows) / pend, 4) if pend else None,
        "replay": {"min_cov": a.min_cov, "group_top": not a.no_group_top},
        "classes": dict(cls),
        "releasable": cls["A1"] + cls["A2"],
        "releasable_share": round((cls["A1"] + cls["A2"]) / len(rows), 3) if rows else None,
        "ref_blank_share": round(cls["C"] / len(rows), 3) if rows else None,
        "ref_lib_n_buckets": dict(collections.Counter(
            "0" if r["ref_lib_n"] == 0 else "1-2" if r["ref_lib_n"] <= 2 else "3-9" if r["ref_lib_n"] < 10 else "10+" for r in withref)),
        "ref_in_5b": {"top1": sum(r["ref_in_5b"] == 1 for r in withref), "top3": sum(0 < r["ref_in_5b"] <= 3 for r in withref)},
        "cov": {"min": covs[0] if covs else None, "p10": q(0.1), "median": q(0.5), "p90": q(0.9), "max": covs[-1] if covs else None},
        "char_ne_ref_share": round(sum(1 for r in withref if r["char"] != r["ref"]) / len(withref), 3) if withref else None,
        "top_attractors": collections.Counter(r["top"] for r in rows).most_common(8),
        "jiazhu_share": round(sum(r["jiazhu"] for r in rows) / len(rows), 3) if rows else None,
        "page_no_align_cells": sum(1 for r in withref if not r["page_n_align"]),
        "by_pending_reason": dict(by_all),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    cols = list(rows[0].keys()) if rows else []
    with open(out / "cells.tsv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    md = [f"# L05 体检（{a.text}）", "", f"- 待审 {pend} 格，L05 {len(rows)} 格（{summary['l05_share']:.1%}）" if pend else "- 没有待审格", ""]
    md += ["| 指标 | 值 |", "|---|---|"] + [f"| {k} | {json.dumps(v, ensure_ascii=False)} |" for k, v in summary.items()
                                           if k not in ("text", "by_pending_reason")]
    (out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
