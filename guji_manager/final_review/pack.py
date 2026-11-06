"""从产物包取每格的上下文窗口与候选（原 build.py／finalize.py 的窗口部分）。

产物包布局：`<pkg>/<册>/<步>/pNNNN.json`（步＝seed_admit／align_ref／glyph_match）。
cv 的读序（sort_by_reading）和字组表（GROUPS）由调用方传入，测试可换假的。
"""
from __future__ import annotations

import glob
import json
import os
from types import SimpleNamespace as NS


def default_cv():
    """→ (sort_by_reading, GROUPS, ctx_hash, WIDTH)；惰性取，没装 cv 的环境只有这里会报错。"""
    try:
        from . import _cvx as c; ctx_hash, WIDTH, sort_by_reading, GROUPS = c.ctx_hash, c.WIDTH, c.sort_by_reading, c.GROUPS
    except ImportError as e:   # pragma: no cover
        raise SystemExit(f"需要装 open-guji-cv（pipeline）：{e}")
    return sort_by_reading, GROUPS, ctx_hash, WIDTH


def _pageno(f):
    return int(os.path.basename(f)[1:5])


def _load_steps(pkg, vol):
    seed = {_pageno(f): json.load(open(f, encoding="utf-8"))["seed_admit"] for f in glob.glob(f"{pkg}/{vol}/seed_admit/p*.json")}
    align, anchored = {}, {}
    for f in glob.glob(f"{pkg}/{vol}/align_ref/p*.json"):
        ar = json.load(open(f, encoding="utf-8"))["align_ref"]
        anchored[_pageno(f)] = {c["id"]: c.get("align_char") for c in ar.get("chars", [])} if ar.get("anchored") else {}
        for c in ar.get("chars", []):
            align[c["id"]] = c
    gm = {}
    for f in glob.glob(f"{pkg}/{vol}/glyph_match/p*.json"):
        for col in json.load(open(f, encoding="utf-8"))["glyph_match"]["columns"]:
            for c in col.get("chars", []):
                gm[c["id"]] = c
    return seed, align, anchored, gm


def _reading(seed_page, sort_fn):
    for col in sorted(seed_page["columns"], key=lambda c: c["col"]):
        recs = [NS(**{k: c[k] for k in ("slot", "sub")}, raw=c) for c in col.get("chars", [])]
        for r in sort_fn(recs):
            yield r.raw


def build_cells(pkg, sel: list[dict], sort_fn, groups, width=20):
    """→ [{id, cls, group, left, right, ref_char, machine_char, cands{字:[来源]}, group_members, guard, doubts}]"""
    byvol: dict[str, list[dict]] = {}
    for r in sel:
        byvol.setdefault(r["id"].split(":")[0], []).append(r)
    out = []
    for vol, lst in sorted(byvol.items()):
        seed, align, _, gm = _load_steps(pkg, vol)
        stream, info = [], {}
        for pg in sorted(seed):
            for c in _reading(seed[pg], sort_fn):
                a = align.get(c["id"])
                if c.get("admit") and c.get("char"):
                    t = c["char"]
                elif a and a.get("align_char"):
                    t = a["align_char"]
                elif c.get("char"):
                    t = c["char"]
                else:
                    t = "□"
                stream.append((c["id"], t))
                info[c["id"]] = c
        idx = {i: n for n, (i, _) in enumerate(stream)}
        for r in lst:
            cid = r["id"]
            if cid not in idx:
                out.append({"id": cid, "cls": r["cls"], "error": "not in stream"})
                continue
            n = idx[cid]
            left = "".join(t for _, t in stream[max(0, n - width):n])
            right = "".join(t for _, t in stream[n + 1:n + 1 + width])
            c = info[cid]
            a, g = align.get(cid, {}), gm.get(cid, {})
            ev = c.get("evidence", {})
            grp = ev.get("group") or {}
            spec = groups.get(r["group"]) if r["group"] else None
            members = "".join(sorted(spec.members)) if spec else None
            cands: dict[str, list[str]] = {}

            def add(ch, s):
                if ch:
                    cands.setdefault(ch, []).append(s)
            ref_char = a.get("align_char") or r.get("ref") or None   # 坐标对位给的格没有 align_char，退回 cells.tsv 的 ref 列
            add(ref_char, "参校本")
            add(c.get("char"), "机器识别")
            for x in g.get("candidates", [])[:5]:
                ch, sc = (x.get("char"), x.get("score", x.get("sim"))) if isinstance(x, dict) else (x[0], x[1])
                add(ch, f"字形库前五({sc:.2f})" if isinstance(sc, (int, float)) else "字形库前五")
            for s in grp.get("solvers", []):
                if s.get("char"):
                    add(s["char"], "解法:" + str(s.get("solver")))
            for ch in (members or ""):
                if ch in cands or r["cls"] == "Z":
                    add(ch, "组成员")
            gd = ev.get("guard") or g.get("guard")
            if gd:
                for ch in (gd if isinstance(gd, str) else json.dumps(gd, ensure_ascii=False)):
                    if ch in cands:
                        cands[ch].append("护栏对")
            out.append({"id": cid, "cls": r["cls"], "reason": r["reason"], "group": r["group"] or None, "left": left, "right": right,
                        "ref_char": ref_char, "machine_char": c.get("char"), "cands": cands,
                        "group_members": members, "guard": gd, "doubts": c.get("doubts"),
                        "glyph_cands": [(x.get("char"), x.get("score", x.get("sim"))) if isinstance(x, dict) else (x[0], x[1])
                                        for x in g.get("candidates", [])[:5]]})
    return out


def key_windows(pkg, cell_ids, sort_fn, width):
    """按管线 `_clf_ctx` 的口径算裁定键窗口（当页、邻格已放行字/参校本字/□；排除 excluded），重切后仍命中。→ {id: (left, right, ref)}"""
    byvol: dict[str, set[int]] = {}
    for i in cell_ids:
        v, p = i.split(":")[:2]
        byvol.setdefault(v, set()).add(int(p))
    want = set(cell_ids)
    win = {}
    for vol, pages in byvol.items():
        seed, align, anchored, _ = _load_steps(pkg, vol)
        for pg in pages:
            if pg not in seed:
                continue
            amap = anchored.get(pg) or {}
            seq = [c for c in _reading(seed[pg], sort_fn) if "excluded" not in (c.get("doubts") or [])]

            def t(c):
                return (c["char"] if c.get("admit") and c.get("char") else None) or amap.get(c["id"]) or "□"
            for i, c in enumerate(seq):
                if c["id"] in want:
                    win[c["id"]] = ("".join(t(x) for x in seq[max(0, i - width):i]), "".join(t(x) for x in seq[i + 1:i + 1 + width]), amap.get(c["id"]) or "")
    return win
