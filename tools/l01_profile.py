#!/usr/bin/env python
"""L01 `lib_missing` 体检：一本书（或几册）★main 包里哪些格是 L01、各是什么情况、有多少能靠已有证据救。

新书开工后跑一遍，得到 doc/01-粗校/待审原因/lib_missing/benchmark.md 里的指标表。只读，不写产物包、不写中心库。

    python tools/l01_profile.py --ws <工作区目录> --text <中心库文本号> --out /tmp/l01 [--vols vol20,vol44] [--jobs 4]
    python tools/l01_profile.py --ws <工作区目录> --text <文本号> --out /tmp/l01 --crops   # 另裁格图并按形状分类（要原图）

前提（同 pending-stats）：环境里有 GUJI_DATA_TOKEN（读令牌够）与 GUJI_DATA_HOME；工作区目录只放 workspace.yaml 与
.central.json，先 `guji db pull -w <ws>` 拉字形库（output/glyph.db）。

输出：`cells.tsv`（每个 L01 格一行）、`summary.json`、`report.md`。
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import shutil
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from guji_manager._cv import connect
from guji_manager.pending_stats import nonbody_of_yaml
from guji_manager.review.reasons import (_load_layer, align_for_seed, book_cells, reasons_for_pending)

K = 8   # 上下文各取几字


def _run(*a, **kw):
    return subprocess.run(a, capture_output=True, text=True, **kw)


def _page_facts(root: Path, f: Path):
    """一页：按阅读序的格序列、现役对位、坐标对位、cell_shrink 墨框。夹注两列先读完 a 再读 b。"""
    seed = _load_layer(f, "seed_admit") or {}
    align = align_for_seed(seed, _load_layer(root / "align_ref" / f.name, "align_ref")) or {}
    cur = {c["id"]: c.get("align_char") for c in align.get("chars", [])}
    coord = {c["id"]: c["ref_char"] for c in align.get("coord") or [] if c.get("ref_char")}
    cs = _load_layer(root / "cell_shrink" / f.name, "char_index") or {}
    box = {}
    for key in ("columns", "alt_columns"):
        for col in cs.get(key, []) or []:
            for ch in col.get("chars", []):
                box.setdefault(ch["id"], {k: ch.get(k) for k in ("width", "height", "bbox_page", "step3_kind", "flags")})
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
    return seq, cur, coord, box


def _layer(root: Path, name: str, key: str, pg: str) -> dict:
    return _load_layer(root / name / pg, key) or {}


def _rows_of(v: str, root: Path, gdb: str, nonbody: dict) -> tuple[dict, list[dict]]:
    cells = book_cells(root, v)
    keys = [c for c in cells if c.split(":")[0].lstrip("0") not in nonbody]
    rs = reasons_for_pending({"cells": [{"cell": c} for c in keys]}, root, v, glyph_db=gdb)
    by = collections.Counter(r.value for r, _ in rs.values())
    want = {c for c, (r, _) in rs.items() if r.value == "lib_missing"}
    rows = []
    for f in sorted((root / v / "seed_admit").glob("p*.json")):
        if not any(k.startswith(f"{int(f.stem[1:])}:") for k in want):
            continue
        seq, cur, coord, box = _page_facts(root / v, f)
        txt = [(ch.get("char") if ch.get("admit") else None) or cur.get(ch["id"]) or coord.get(ch["id"]) or "□" for ch in seq]
        gm = {c["id"]: c for col in _layer(root / v, "glyph_match", "glyph_match", f.name).get("columns", []) for c in col.get("chars", [])}
        rc = {}
        for col in _layer(root / v, "rare_candidates", "rare_candidates", f.name).get("columns", []):
            for c in col.get("chars") or col.get("cells") or []:
                rc[c["id"]] = [x["char"] for x in c.get("candidates", [])]
        for i, ch in enumerate(seq):
            key = ch["id"].split(":", 1)[1]
            if key not in want:
                continue
            c = cells[key]
            _, detail = rs[key]
            g = gm.get(ch["id"]) or {}
            rare = rc.get(ch["id"]) or []
            rows.append(dict(
                vol=v, cell=key, page=f.name, detail=detail, kind=detail.split(":")[0], ref=c.ref or "", char=c.char or "",
                top=c.top or "", cov=g.get("cov"), n_verified=g.get("n_verified"), guard=(c.evidence or {}).get("guard"),
                has_lib_miss_code=int(c.lib_miss),
                garble=int("ctx_garble_shape" in c.doubts), ref_in_5b=(rare.index(c.ref) + 1 if c.ref in rare else 0),
                cur=cur.get(ch["id"]) or "", coord=coord.get(ch["id"]) or "",
                jiazhu=int((box.get(ch["id"]) or {}).get("step3_kind") == "jiazhu"),
                flags=",".join((box.get(ch["id"]) or {}).get("flags") or []),
                bbox=json.dumps((box.get(ch["id"]) or {}).get("bbox_page")),
                left="".join(txt[max(0, i - K):i]), right="".join(txt[i + 1:i + 1 + K]),
                doubts=",".join(str(d) for d in c.doubts)))
    return {"vol": v, "pending": len(keys), "by": dict(by)}, rows


def _lib_n(gdb: str):
    import sqlite3
    con = sqlite3.connect(f"file:{gdb}?mode=ro", uri=True)
    n = collections.Counter()
    for ch, k in con.execute("select char, sum(n_confirmed) from glyphs group by char"):
        n[ch] += k or 0
    con.close()
    return n


def _classify_shapes(rows: list[dict], ws: str, jobs: int) -> None:
    """可选：拉原图裁格图，按宽高比、边缘粗条、散点个数分形状类（B 框线粗条／W 横条并格／N 窄条／T 碎片／S 点状散墨／O 其余）。"""
    import numpy as np
    from PIL import Image
    from scipy import ndimage as ndi
    from guji_manager.review_pages.crop import to_image_box
    Image.MAX_IMAGE_PIXELS = None
    byv = collections.defaultdict(list)
    for r in rows:
        byv[r["vol"]].append(r)

    def one(v):
        tmp = Path(ws) / ".l01_img" / v
        _run("guji", "source", "pull", v, "-w", ws, "--to", str(tmp), env={**os.environ, "GUJI_WORKSPACE": ws})
        for r in byv[v]:
            p = tmp / f"{int(r['page'][1:5])}.png"
            bx = json.loads(r["bbox"])
            if not bx or not p.exists():
                r["shape"] = ""
                continue
            im = Image.open(p).convert("L")
            a = np.array(im.crop(to_image_box(bx, im.width, 4))) < 128
            h, w = a.shape
            lab, n = ndi.label(a)
            sizes = ndi.sum(a, lab, range(1, n + 1)) if n else np.array([0])
            nsmall = int((sizes < max(6, 0.004 * h * w)).sum())
            asp = w / h
            edge = max(a[:, :max(2, w // 12)].mean(), a[:, -max(2, w // 12):].mean(),
                       a[:max(2, h // 12)].mean(), a[-max(2, h // 12):].mean())
            bar = (a.mean(0) > 0.85).any() or (a.mean(1) > 0.85).any()
            r["shape"] = ("W" if asp > 1.5 or (h < 45 and asp > 1.1) else "B" if bar or edge > 0.6 else
                          "T" if min(w, h) < 40 else "N" if asp < 0.6 else "S" if nsmall >= 8 else "O")
        shutil.rmtree(tmp, ignore_errors=True)

    with ThreadPoolExecutor(jobs) as ex:
        list(ex.map(one, sorted(byv)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ws", required=True, help="工作区目录（含 .central.json，已 db pull）")
    ap.add_argument("--text", required=True, help="中心库文本号（books 表的 ws）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--vols")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--crops", action="store_true")
    ap.add_argument("--db", help="字形库 glyph.db 路径（缺省用 <ws>/output/glyph.db＝最新库；要与线上口径一致请给册钉库的 db，如 殿本 g19）")
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
    if a.crops and rows:
        _classify_shapes(rows, a.ws, a.jobs)
    pend = sum(s.get("pending", 0) for s in stats)
    by_all = collections.Counter()
    for s in stats:
        by_all.update(s.get("by", {}))
    kinds = collections.Counter(r["kind"] for r in rows)
    withref = [r for r in rows if r["ref"]]
    covs = [r["cov"] for r in rows if r["cov"]]

    def q(xs, p):
        return round(sorted(xs)[min(len(xs) - 1, int(len(xs) * p))], 3) if xs else None

    summary = {
        "text": a.text, "vols_total": len(vols), "vols_with_main": sum(1 for s in stats if "skip" not in s),
        "pending": pend, "l01": len(rows), "l01_share": round(len(rows) / pend, 4) if pend else None,
        "kinds": dict(kinds),
        "new_in_l02_merge": sum(1 for r in rows if not r["has_lib_miss_code"]),
        "ref_blank_share": round(kinds["ref_blank"] / len(rows), 3) if rows else None,
        "with_ref": len(withref),
        "ref_lib_n_buckets": dict(collections.Counter(
            "0" if r["ref_lib_n"] == 0 else "1-2" if r["ref_lib_n"] <= 2 else "3-9" if r["ref_lib_n"] < 10 else "10-49" if r["ref_lib_n"] < 50 else "50+"
            for r in withref)),
        "ref_in_5b": {"top1": sum(r["ref_in_5b"] == 1 for r in withref), "top3": sum(0 < r["ref_in_5b"] <= 3 for r in withref),
                      "top5": sum(0 < r["ref_in_5b"] <= 5 for r in withref)},
        "cov": {"min": min(covs) if covs else None, "median": q(covs, 0.5), "max": max(covs) if covs else None},
        "garble_share": round(sum(r["garble"] for r in rows) / len(rows), 3) if rows else None,
        "jiazhu_share": round(sum(r["jiazhu"] for r in rows) / len(rows), 3) if rows else None,
        "coord_only_share": round(sum(1 for r in withref if not r["cur"]) / len(withref), 3) if withref else None,
        "pages_ge3_cells": sum(c for c in collections.Counter((r["vol"], r["page"]) for r in rows).values() if c >= 3),
        "by_pending_reason": dict(by_all),
    }
    if a.crops:
        summary["shape"] = dict(collections.Counter(r.get("shape", "") for r in rows))
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    cols = list(rows[0].keys()) if rows else []
    with open(out / "cells.tsv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    md = [f"# L01 体检（{a.text}）", "", f"- 待审 {pend} 格，L01 {len(rows)} 格（{summary['l01_share']:.1%}）" if pend else "- 没有待审格", ""]
    md += ["| 指标 | 值 |", "|---|---|"] + [f"| {k} | {json.dumps(v, ensure_ascii=False)} |" for k, v in summary.items()
                                           if k not in ("text", "by_pending_reason")]
    (out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
