"""V01 深挖取数：逐册拉 ★main 包 → 待审格算原因，取 variant_pair 格的事实＋上下文＋异体对来源。输出 out/<book>-<vol>.json。"""
import json, os, subprocess, shutil, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from guji_manager.review.reasons import reasons_for_pending, book_cells, align_for_seed, _load_layer, _VARIANT, _default_are_variants

OUT = Path("/home/user/v01/out"); TMP = Path("/home/user/v01/tmp")
BOOKS = {"siku": "/home/user/ws/siku", "shiji": "/home/user/ws/shiji", "qtw": "/home/user/ws/qtw"}
GDH = "/home/user/gdh/main/%s/books"
WSID = {"siku": "siku-zongmu", "shiji": "988g3f0wsu", "qtw": "995ejelvk0"}
K = 8
AV = _default_are_variants()

def run(*a): return subprocess.run(a, capture_output=True, text=True)

def page_facts(root, f):
    seed = _load_layer(f, "seed_admit") or {}
    align = align_for_seed(seed, _load_layer(root / "align_ref" / f.name, "align_ref")) or {}
    ref = {c["id"]: c.get("align_char") for c in align.get("chars", [])}
    for c in align.get("coord") or []:
        if c.get("ref_char") and c["id"] not in ref:
            ref[c["id"]] = c["ref_char"]
    seq = []
    for col in seed.get("columns", []):
        block = []
        for ch in col.get("chars", []) + [None]:
            if ch is not None and "excluded" in (ch.get("doubts") or []): continue
            if ch is not None and ch.get("sub"):
                block.append(ch); continue
            if block:
                seq += [c for c in block if c.get("sub") == "a"] + [c for c in block if c.get("sub") != "a"]; block = []
            if ch is not None: seq.append(ch)
    return seq, ref

def one(job):
    k, v = job; wsdir = BOOKS[k]
    res = OUT / f"{k}-{v}.json"
    if res.exists(): return
    L = [l.split("\t") for l in run("guji", "products", "pack", "list", v, "-w", wsdir).stdout.splitlines() if l.lstrip().startswith("★")]
    if not L:
        res.write_text(json.dumps({"vol": v, "skip": "no main"})); return
    lab = L[0][0].split("/")[-1].strip()
    tmp = TMP / f"{k}-{v}"; shutil.rmtree(tmp, ignore_errors=True)
    run("guji", "products", "pack", "fetch", v, "-w", wsdir, "--label", lab, "--to", str(tmp))
    root = tmp if (tmp / v / "seed_admit").is_dir() else tmp.parent
    if not (root / v / "seed_admit").is_dir():
        res.write_text(json.dumps({"vol": v, "skip": "fetch failed", "label": lab})); return
    cells = book_cells(root, v)
    doc = {"cells": [{"cell": c} for c in cells]}
    rs = reasons_for_pending(doc, root, v)
    vp = {c for c, (r, _) in rs.items() if r.value == "variant_pair"}
    rows = []
    for f in sorted((root / v / "seed_admit").glob("p*.json")):
        seq, ref = page_facts(root / v, f)
        txt = [(ch.get("char") if ch.get("admit") else None) or ref.get(ch["id"]) or "□" for ch in seq]
        for i, ch in enumerate(seq):
            cid = ch["id"]; key = cid.split(":", 1)[1]
            if key not in vp: continue
            c = cells[key]
            codes = sorted(c.codes & _VARIANT)
            vpairs = []
            if c.has_ref and c.top and c.top != c.ref:
                vpairs = [x for x, *_ in c.cands[:5] if x and x != c.ref and AV and AV(c.ref, x)]
            g = c.group or {}
            rows.append({"vol": v, "cell": key, "page": key.split(":")[0], "char": c.char, "ref": c.ref, "ref_op": c.ref_op,
                         "cands": [[x[0], round(x[1], 3)] for x in c.cands[:5]], "codes": codes, "vpairs": vpairs,
                         "doubts": [d if isinstance(d, str) else str(d) for d in c.doubts][:6],
                         "group": g.get("id"), "g_why": g.get("why"), "g_dec": g.get("decision"),
                         "g_solvers": [(s.get("name"), s.get("char")) for s in g.get("solvers") or []],
                         "left": "".join(txt[max(0, i - K):i]), "right": "".join(txt[i + 1:i + 1 + K]),
                         "seed_char": ch.get("char"), "channel": ch.get("channel")})
    res.write_text(json.dumps({"vol": v, "label": lab, "n_pending": len(cells), "v01": rows}, ensure_ascii=False))
    shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    jobs = []
    for k in BOOKS:
        for p in sorted(Path(GDH % WSID[k]).glob("*.yaml")):
            jobs.append((k, p.stem))
    only = os.environ.get("ONLY")
    if only: jobs = [j for j in jobs if j[0] == only]
    if os.environ.get("VOLS"):
        vs = set(os.environ["VOLS"].split(",")); jobs = [j for j in jobs if j[1] in vs]
    print(len(jobs), flush=True)
    def go(j):
        try: one(j)
        except Exception as e: print("ERR", j, e, flush=True)
        print(j, flush=True)
    with ThreadPoolExecutor(int(os.environ.get("J", "4"))) as ex: list(ex.map(go, jobs))
