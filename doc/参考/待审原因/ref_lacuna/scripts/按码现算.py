#!/usr/bin/env python3
"""按新判法逐格现算待审原因，只留指定的码（A24 11-07，sheldon「每个会话按新码重新统计自己这个码」）。

和 pending-stats 的区别：pending-stats 读线上单上**出单时**写好的 pending_reason，改了 reasons.py 要等重出单才变；
这里每册拉 ★main 包，用本机 guji-manager 的 reasons.py 现算，改完判法马上能看。和 run3.py 的区别：接上待收字登记表
（中心库 config/pua/glyph_pending_codes.json）和殆知阁源回查私用码，R03 才算得出来；并且把指定码的格逐格写出来。

    pip install -e <guji-manager> -e <open-guji-cv>; pip install "psycopg[binary]" websockets
    export GUJI_DATA_TOKEN=$GUJI_DATA_TOKEN_READ      # 拉包；连库用 NEON_DATABASE_URL
    python3 按码现算.py --codes R01,R03 --out /tmp/r01 [--books siku,sj,qtw] [--vols vol20,vol21] [--dzg <殆知阁 0001–0005.jsonl 目录>]

每本书要一个工作区目录，里面只放 `.central.json`（{"ws": "<工作区 id>"}），本脚本缺了会自己建在 --ws-root 下。
输出：<out>/summary.json（每书每码格数）、<out>/cells-<码>.tsv（逐格）、<out>/res/（每册缓存，重跑跳过；删掉即重算）。
殆知阁源不给就不回查私用码（R03 记成 R01，和改前一样）；源文件可从 https://sikuquanshu.daizhige.net/data/000N.jsonl 下（curl）。
"""
import argparse, collections as C, csv, json, os, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BOOKS = {"siku": "siku-zongmu", "sj": "988g3f0wsu", "qtw": "995ejelvk0"}
LAYERS = ("seed_admit", "align_ref", "glyph_match", "cell_shrink")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", required=True, help="逗号分隔的分类码，如 R01,R03")
    ap.add_argument("--out", required=True)
    ap.add_argument("--books", default="siku,sj,qtw")
    ap.add_argument("--vols", help="只算这些册（逗号分隔，册名同中心库 books 表）")
    ap.add_argument("--ws-root", default=os.path.expanduser("~/guji-ws"))
    ap.add_argument("--packs", default=os.path.expanduser("~/guji-packs"), help="★main 包缓存（只留三步，约 50 MB/册）")
    ap.add_argument("--dzg", help="殆知阁源 0001–0005.jsonl 所在目录（殿本私用码回查）")
    ap.add_argument("--glyph-db", help="字形库 db（要分 L02/L03 时给）")
    ap.add_argument("-j", type=int, default=4)
    a = ap.parse_args()
    from guji_manager._cv import connect
    from guji_manager.review.pending_reason import specs
    from guji_manager.review.reasons import book_cells, reasons_for_pending
    from guji_manager.pending_stats import nonbody_of_yaml
    want = {c.strip() for c in a.codes.split(",") if c.strip()}
    enum_of = {sp.code: r.value for r, sp in specs().items()}
    names = {enum_of[c] for c in want}
    resolve = None
    if a.dzg:
        from open_guji_cv.utils.pua_lookup import PuaIndex, resolve_pua_code
        idx = PuaIndex.from_source(sorted(Path(a.dzg).glob("000[1-5].jsonl")))
        resolve = lambda l, r: resolve_pua_code(idx, l, r)  # noqa: E731
    books = [b for b in a.books.split(",") if b]
    with connect() as con:
        cur = con.cursor()
        cur.execute("select raw from files where ws='siku-zongmu' and src_path='config/pua/glyph_pending_codes.json'")
        row = cur.fetchone()
        gp = frozenset(json.loads(row[0]).get("codes") or []) if row else frozenset()
        vols = {}
        for k in books:
            cur.execute("select book, raw from books where ws=%s order by book", (BOOKS[k],))
            vols[k] = [(b, nonbody_of_yaml(r)) for b, r in cur.fetchall() if not a.vols or b in a.vols.split(",")]
    out = Path(a.out); (out / "res").mkdir(parents=True, exist_ok=True)

    def run(*x):
        return subprocess.run(x, capture_output=True, text=True)

    def one(job):
        k, v, nbp = job
        f = out / "res" / f"{k}-{v}.json"
        if f.exists():
            return
        wsd = Path(a.ws_root) / k
        wsd.mkdir(parents=True, exist_ok=True)
        if not (wsd / ".central.json").exists():
            (wsd / ".central.json").write_text(json.dumps({"ws": BOOKS[k]}))
        L = [l.split("\t") for l in run("guji", "products", "pack", "list", v, "-w", str(wsd)).stdout.splitlines() if l.lstrip().startswith("★")]
        if not L:
            f.write_text(json.dumps({"skip": "no main"})); return
        lab = L[0][0].split("/")[-1].strip()
        dst = Path(a.packs) / k / v / lab
        if not (dst / v / "seed_admit").is_dir():
            run("guji", "products", "pack", "fetch", v, "-w", str(wsd), "--label", lab, "--to", str(dst))
            for d in os.listdir(dst / v):
                if d not in LAYERS:
                    shutil.rmtree(dst / v / d, ignore_errors=True)
        cells = book_cells(dst, v)
        keys = [c for c in cells if c.split(":")[0].lstrip("0") not in (nbp or {})]
        rs = reasons_for_pending({"cells": [{"cell": c} for c in keys]}, dst, v, glyph_pending=gp,
                                 pua_resolve=resolve if (k == "siku" and resolve) else (lambda l, r: None), glyph_db=a.glyph_db)
        rows = []
        for c, (r, d) in rs.items():
            if r.value in names:
                X = cells[c]
                rows.append({"cell": c, "reason": r.value, "detail": d, "char": X.char, "ref": X.ref,
                             "top": " ".join(f"{x[0]}{float(x[1]):.3f}" for x in (X.cands or [])[:3]),
                             "doubts": ",".join(map(str, X.doubts or []))[:200], "L": X.ref_left[-8:], "R": X.ref_right[:8]})
        f.write_text(json.dumps({"label": lab, "by": C.Counter(r.value for r, _ in rs.values()), "pending": len(keys), "rows": rows},
                                ensure_ascii=False))
        print(k, v, len(rows), flush=True)

    jobs = [(k, v, nb) for k in books for v, nb in vols[k]]
    with ThreadPoolExecutor(a.j) as ex:
        list(ex.map(one, jobs))
    summ = C.defaultdict(C.Counter); per = C.defaultdict(list)
    for k, v, _ in jobs:
        d = json.loads((out / "res" / f"{k}-{v}.json").read_text())
        if "skip" in d:
            continue
        summ[k].update(d["by"]); summ[k]["_pending"] += d["pending"]; summ[k]["_vols"] += 1
        for r in d["rows"]:
            per[r["reason"]].append({"book": k, "vol": v, "label": d["label"], **r})
    (out / "summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1))
    for name, rows in per.items():
        with open(out / f"cells-{name}.tsv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter="\t"); w.writeheader(); w.writerows(rows)
    for k in books:
        print(k, {n: summ[k].get(n, 0) for n in sorted(names)}, "待审", summ[k]["_pending"], "册", summ[k]["_vols"])


if __name__ == "__main__":
    main()
