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
    from ..admit_names import final_dir, page_body
    seed = {_pageno(f): page_body(json.load(open(f, encoding="utf-8"))) for f in glob.glob(f"{final_dir(f'{pkg}/{vol}')}/p*.json")}
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
            # 组内全部字：产物带 evidence.group.members（cv #1921）就用它，旧产物退回字组注册表
            ev_members = grp.get("members")
            ev_members = ev_members if isinstance(ev_members, str) else "".join(ev_members or ())
            members = ev_members or ("".join(sorted(spec.members)) if spec else None)
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
                if ch in cands or r["cls"] == "Z" or ev_members:   # 产物带全组时每个组员都出按钮
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


# seed_admit 5c `_vis_ruling_pass` 之后才放行／降审的遍。产物是整遍跑完的状态，算裁定键要退回 5c 当时：
# 这些遍放行的邻格当时还没放（取整理本字或 □），这些遍降审的邻格当时还是放行字（A33 11-20，全唐文 027:59:4:7）。
# 次序见 cv `steps/seed_admit.py` 5c 之后各遍；cv 加了遍要同步这里（产物有 `evidence.vis_ctx` 时直接用那个，不靠这张表）。
LATE_ADMIT = frozenset({"vis_ruling", "symbol_ref_blank", "textlayer_ref", "consensus_lib"})
LATE_DEMOTE = frozenset({"src_code_conflict", "symbol_review", "symbol_ref_blank", "stroke_veto", "human_unbound",
                         "evict_review", "jiazhu_uneven"})


def _g(c, k):
    return c.get(k) if isinstance(c, dict) else getattr(c, k, None)


def _late_admit(channel, ev: dict) -> bool:
    return channel in LATE_ADMIT or (channel == "near_knn" and (ev.get("near_knn") or {}).get("via") == "near_gap")


def vis_time_char(c, amap: dict) -> str:
    """邻格在 5c 时的窗口字：那时已放行用放行字，否则用整理本对位字，再没有记 □（同 cv `_clf_ctx`）。"""
    ev = _g(c, "evidence") or {}
    if _g(c, "admit"):
        adm = not _late_admit(_g(c, "channel"), ev)
    else:
        d = ev.get("demoted_from") or {}
        adm = d.get("by") in LATE_DEMOTE and not _late_admit(d.get("channel"), ev)
    return (_g(c, "char") if adm else None) or amap.get(_g(c, "id")) or "□"


def vis_windows(seq: list, amap: dict, width: int, want=None) -> dict:
    """读序格列（已去 excluded）→ {id: (left, right, ref)}，按 5c 时的状态。
    格自己的产物带 `evidence.vis_ctx`（cv 在 5c 当场记下的窗口）时直接用它。"""
    txt = None
    out = {}
    for i, c in enumerate(seq):
        cid = _g(c, "id")
        if want is not None and cid not in want:
            continue
        vc = (_g(c, "evidence") or {}).get("vis_ctx")
        if isinstance(vc, dict) and "left" in vc and "right" in vc:
            out[cid] = (vc["left"], vc["right"], vc.get("ref") if vc.get("ref") is not None else (amap.get(cid) or ""))
            continue
        if txt is None:
            txt = [vis_time_char(x, amap) for x in seq]
        out[cid] = ("".join(txt[max(0, i - width):i]), "".join(txt[i + 1:i + 1 + width]), amap.get(cid) or "")
    return out


def window_diff(a: str, b: str, side: str) -> str:
    """两个窗口串差在哪几个字（左窗从格往左数、右窗往右数）→ 如「左1 撫→播」。"""
    if side == "左":
        a, b = a[::-1], b[::-1]
    n = max(len(a), len(b))
    d = [f"{side}{k + 1} {a[k] if k < len(a) else '∅'}→{b[k] if k < len(b) else '∅'}"
         for k in range(n) if (a[k:k + 1] or None) != (b[k:k + 1] or None)]
    return "、".join(d[:4]) + ("…" if len(d) > 4 else "")


def key_windows(pkg, cell_ids, sort_fn, width):
    """按管线 5c `_vis_ruling_pass` 当时的口径算裁定键窗口（当页、邻格当时已放行字/参校本字/□；排除 excluded），
    重切后仍命中。产物带 `evidence.vis_ctx` 的格直接用它。→ {id: (left, right, ref)}"""
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
            win.update(vis_windows(seq, amap, width, want))
    return win
