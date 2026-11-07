"""Z03 group_conflict 取数：逐册拉 ★main 包，reasons_for_pending 取 group_conflict 格，记 group 证据（solvers 轨迹、why、
demoted_from）、整理本字、库候选、前后文、cell_shrink 坐标；同时统计各册各字组复核（mode=review）的 decision 分布。
输出 /home/user/z02/out/<book>-<vol>.json。环境：GUJI_DATA_HOME、GUJI_DATA_TOKEN=READ 已设；ws/<k> 是假工作区。"""
import json, os, subprocess, sys, shutil, collections
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from guji_manager._cv import connect
from guji_manager.review.reasons import reasons_for_pending, book_cells, align_for_seed, _load_layer
from guji_manager.pending_stats import nonbody_of_yaml

OUT = Path("/home/user/z02/out_new"); TMP = Path("/home/user/z02/tmp3")
WS = {"siku": ("siku-zongmu", "/home/user/ws/siku"), "sj": ("988g3f0wsu", "/home/user/ws/sj"), "qtw": ("995ejelvk0", "/home/user/ws/qtw")}
G = "/home/user/venv/bin/guji"; K = 8
def run(*a): return subprocess.run(a, capture_output=True, text=True)

def page_facts(root, f):
    seed = _load_layer(f, "seed_admit") or {}
    align = align_for_seed(seed, _load_layer(root / "align_ref" / f.name, "align_ref")) or {}
    ref = {c["id"]: c.get("align_char") for c in align.get("chars", [])}
    coord = {c["id"]: c["ref_char"] for c in align.get("coord") or [] if c.get("ref_char")}
    cs = _load_layer(root / "cell_shrink" / f.name, "char_index") or {}
    box = {}
    for key in ("columns", "alt_columns"):
        for col in cs.get(key, []) or []:
            for ch in col.get("chars", []):
                box.setdefault(ch["id"], {k: ch.get(k) for k in ("width", "height", "bbox_page", "cell_type")})
    seq = []
    for col in seed.get("columns", []):
        for ch in col.get("chars", []):
            if "excluded" in (ch.get("doubts") or []): continue
            seq.append(ch)
    return seq, ref, coord, box, seed

def one(job):
    k, v = job; ws, wsdir = WS[k]
    res = OUT / f"{k}-{v}.json"
    if res.exists(): return
    L = [l.split("\t") for l in run(G, "products", "pack", "list", v, "-w", wsdir).stdout.splitlines() if l.lstrip().startswith("★")]
    if not L: res.write_text(json.dumps({"vol": v, "skip": "no main"})); return
    lab = L[0][0].split("/")[-1].strip()
    tmp = TMP / f"{k}-{v}"; shutil.rmtree(tmp, ignore_errors=True)
    run(G, "products", "pack", "fetch", v, "-w", wsdir, "--label", lab, "--to", str(tmp))
    root = tmp if (tmp / v / "seed_admit").is_dir() else tmp.parent
    if not (root / v / "seed_admit").is_dir():
        res.write_text(json.dumps({"vol": v, "skip": "fetch failed", "label": lab})); return
    gdb = wsdir + "/output/glyph.db"
    nbp = NB[k].get(v) or {}
    cells = book_cells(root, v)
    keys = [c for c in cells if c.split(":")[0].lstrip("0") not in nbp]
    rs = reasons_for_pending({"cells": [{"cell": c} for c in keys]}, root, v, glyph_db=gdb)
    cnt = collections.Counter(r.value for r, _ in rs.values())
    want = {c for c, (r, _) in rs.items() if r.value == "group_conflict"}
    rows = []; dec = collections.Counter(); chg = collections.Counter()
    for f in sorted((root / v / "seed_admit").glob("p*.json")):
        seq, ref, coord, box, seed = page_facts(root / v, f)
        txt = [(ch.get("char") if ch.get("admit") else None) or ref.get(ch["id"]) or coord.get(ch["id"]) or "□" for ch in seq]
        for i, ch in enumerate(seq):
            key = ch["id"].split(":", 1)[1]
            g = (ch.get("evidence") or {}).get("group")
            if g and g.get("mode") == "review":
                dec[f'{g.get("id")}|{g.get("decision")}'] += 1
            if key not in want: continue
            c = cells[key]; r, detail = rs[key]
            rows.append(dict(vol=v, cell=key, page=f.name, detail=detail, ref=c.ref, ref_op=c.ref_op, char=c.char, top=c.top,
                             cands=c.cands[:5], doubts=c.doubts, group=c.group,
                             demoted_from=(c.evidence or {}).get("demoted_from"),
                             evk=sorted((c.evidence or {}).keys()),
                             coord=coord.get(ch["id"]), cur=ref.get(ch["id"]), box=box.get(ch["id"]),
                             left="".join(txt[max(0, i-K):i]), right="".join(txt[i+1:i+1+K])))
    res.write_text(json.dumps({"vol": v, "label": lab, "n_pending": len(keys), "by": cnt, "review_dec": dec, "z02": rows}, ensure_ascii=False))
    shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True); TMP.mkdir(parents=True, exist_ok=True)
    NB = {}; vols = {}
    with connect() as con:
        cur = con.cursor()
        for k, (ws, _) in WS.items():
            cur.execute("select book, raw from books where ws=%s order by book", (ws,))
            rows = cur.fetchall(); vols[k] = [b for b, _ in rows]; NB[k] = {b: nonbody_of_yaml(r) for b, r in rows}
    jobs = [(k, v) for k in WS for v in vols[k] if not os.environ.get("ONLY") or k == os.environ["ONLY"]]
    if os.environ.get("VOLS"): jobs = [j for j in jobs if j[1] in os.environ["VOLS"].split(",")]
    print(len(jobs), {k: len(x) for k, x in vols.items()}, flush=True)
    def go(j):
        try: one(j)
        except Exception as e: print("ERR", j, repr(e), flush=True)
        print(j, flush=True)
    with ThreadPoolExecutor(int(os.environ.get("J", "4"))) as ex: list(ex.map(go, jobs))
