"""出页：选页型 → 填模板 → 单文件 HTML（用 Artifact 发布，要 db 能力）。

输入统一用 items（jsonl 或 json 列表），每项字段按页型：
  char_card / char_grid：{id, pre(预选字), pre_conf?, kind?, img(图文件路径或 data URI), cov?}
    img 用 crop.py 按 cell_shrink 字框裁（不要按 row_segment 的 quad 裁，会带进边框线）
  pair_whitelist：{key, label?, pre?(选项之一), n?(全组格数), hint?, tiles:[[格号, 图, 说明?, {left,right,ref_char}?]]}
    tile 带上下文时逐格点同字/不同字/看不清，每组页尾显示同字率（pair.py 的 sample_groups 按组各抽 30 格出这个格式）
  codepoint：{key, chars:[字…], pre?(unify:X|other:X|split_follow|split_distinct), hint?,
             glyphs?:{字:图}（字体缺字时候选的字形图，如私用码）,
             rows:{字:{adm?, kr?, img?(同 glyphs), tiles:[[格号, 图]…]}}}（见 codepoint.py）
  seg_cause：{key, vol, page, cause, cause_name, advice, detail, flags, pre, cells[{id, reason, img}]}（seg_causes.build_cards 出）
  near_pair：{key, a, b, ex_a:[[实例号, 图]…], ex_b:[…], diff?(差异区高亮图), cells:[{id, img, ctx?, sa?, sb?, inst?(是库里的刻例), cur?(现标的字)}]}
  lib_audit：{char, tiles:[{id, img, ctx?, prov?, score?}]}（id 是库里的实例号）
  gold_sample：{id, pre, left, right, cands:{字:[来源…]}, img?, kind?(pending_reason，页内可筛选), fact?, pilot?,
               ref_char?(整理本字，上下文里标【】), strip?[图…](横向邻格条), strip_at?(目标格下标，红框)}
  closeout：{id, label, n, rate?, examples?[…], pre?(人审底|留后|精校待办|再处理)}
  glyph_quality：{id, book?, char?, end?, ctx?, ref?, crops:[{key, sha, img}]}，或 dataset 金标信封（expected.crops.{off,on}，
             图路径相对 root）；--exclude 里的格号撤整格、sha 撤单块（见 glyph_quality.py）
图一律内嵌（缩略图由调用者准备好；这里只做 base64，不依赖 cv2/PIL）。
"""
from __future__ import annotations

import base64
import json
import mimetypes
from importlib import resources
from pathlib import Path

from . import cards as cards_mod
from . import pair_audit
from . import codepoint as cp_mod
from . import glyph_quality as gq_mod
from .preselect import KINDS
from .registry import PageType, get

KIND_NAMES = {"ref_vs_lib": "参校≠库", "ref_missing": "参校缺", "lib_missing": "库没有",
              "indep_dissent": "独立识读不同", "no_indep": "无独立识读", "weak_glyph": "字形分不足"}
_TPL = resources.files(__package__)


def embed(img: str | None) -> str:
    """文件路径 → data URI；已是 data URI/空串原样返回。"""
    if not img or img.startswith("data:"):
        return img or ""
    p = Path(img)
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def read_items(path) -> list[dict]:
    t = Path(path).read_text(encoding="utf-8").strip()
    if t.startswith("["):
        return json.loads(t)
    return [json.loads(l) for l in t.splitlines() if l.strip()]


def _read(name: str) -> str:
    return _TPL.joinpath("templates", name).read_text(encoding="utf-8")


def render(pt: PageType, data: dict, title: str | None = None) -> str:
    if pt.template is None:
        raise SystemExit(f"页型 {pt.key} 还没有模板")
    data = {"page_type": pt.key, "tpl_version": pt.version, "coll": pt.doc_prefix,
            "kind_names": KIND_NAMES, **data}
    html = _read(pt.template)
    html = html.replace("/*SHELL*/", _read("_shell.html").replace("/*TITLE*/", title or pt.title)) if "/*SHELL*/" in html else html
    html = html.replace("/*PAGER_JS*/", _read("_pager.js")).replace("/*STORE_JS*/", _read("_store.js"))
    html = html.replace("/*COMMON_CSS*/", _read("_common.css")).replace("/*COMMON_JS*/", _read("_common.js"))
    return html.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False))


def read_ids(paths) -> set[str]:
    """已录入格号：json 列表 / jsonl（每行有 id）/ 每行一个格号的文本，可给多个文件。"""
    ids: set[str] = set()
    for p in paths or []:
        t = Path(p).read_text(encoding="utf-8").strip()
        if not t:
            continue
        if t.startswith("["):
            ids |= {x if isinstance(x, str) else x.get("sha") or x["id"] for x in json.loads(t)}
            continue
        for l in t.splitlines():
            l = l.strip()
            if l:
                o = json.loads(l) if l.startswith("{") else None   # 带 sha 的行（字块质量结果）按字块撤
                ids.add((o.get("sha") or o["id"]) if o else l.split("\t")[0])
    return ids


def build(page_type: str, items: list[dict], book: str, out, per_page: int | None = None, k: int = 5,
          hint: str | None = None, exclude: set[str] | None = None, mode: str | None = None, root=None,
          include_labeled: bool = False, box: int | None = None, rest_ok: bool = True,
          title: str | None = None) -> dict:
    """exclude：已录入的格号，出页时撤掉（点过即录入、不再上页）。
    rest_ok=False（char_card）：难认字页，没有「本页其余都对」，没点的格不算对，只存点过、改过的格。
    title：页头标题，缺省用页型名；char_card 难认字页缺省「一字一卡（疑难格审定）」。"""
    pt = get(page_type)
    n0 = len(items)
    excluded_n = None
    if page_type == "glyph_quality":
        items = gq_mod.normalize(items, root, include_labeled)
        n0 = len(items)
        if exclude:
            items = [dict(r, crops=[c for c in r["crops"] if c["sha"] not in exclude])
                     for r in items if r["id"] not in exclude]
            items = [r for r in items if r["crops"]]
    elif exclude and page_type in ("near_pair", "lib_audit"):
        # 这两个页型的「格」在组里面：撤掉已录入的格/刻例，组空了整组撤
        sub = "cells" if page_type == "near_pair" else "tiles"
        before = sum(len(g.get(sub, [])) for g in items)
        items = [dict(g, **{sub: [x for x in g.get(sub, []) if (x["id"] if isinstance(x, dict) else x[0]) not in exclude]})
                 for g in items]
        items = [g for g in items if g[sub]]
        excluded_n = before - sum(len(g[sub]) for g in items)
    elif exclude:
        items = [r for r in items if r.get("id", r.get("key")) not in exclude]
    if page_type == "char_card":
        rows = [dict(r, img=embed(r.get("img"))) for r in items]
        cs = cards_mod.build_cards(rows, k, solo=not rest_ok)
        pp = per_page or 8
        data = {"book": book, "per_page": pp, "cards": cs, "n_cells": sum(c["n"] for c in cs), "rest_ok": rest_ok,
                "n_excluded": n0 - len(items)}
        stat = {"cards": len(cs), "cells": data["n_cells"], "shown": sum(len(c["samples"]) for c in cs),
                "pages": -(-len(cs) // pp)}
        (Path(out).with_suffix(".cards.json")).write_text(json.dumps(cs, ensure_ascii=False), encoding="utf-8")
    elif page_type == "char_grid":
        pp = per_page or 30
        tiles = [[r["id"], r["pre"], float(r.get("cov") or 0), embed(r.get("img")), r.get("n", 1)] for r in items]
        chars = {t[1] for t in tiles}
        data = {"book": book, "per_page": pp, "n_chars": len(chars),
                "n_cells": sum(t[4] for t in tiles), "tiles": tiles}
        stat = {"tiles": len(tiles), "chars": len(chars), "pages": -(-len(tiles) // pp)}
    elif page_type == "codepoint":
        pp = per_page or 8
        gs = []
        for g in items:
            if g.get("pre"):
                cp_mod.parse_pick(g["pre"])
            rows = {c: dict(r, tiles=[[t[0], embed(t[1])] for t in r.get("tiles", [])])
                    for c, r in (g.get("rows") or {}).items()}
            gl = {c: embed(u) for c, u in (g.get("glyphs") or {}).items()}
            rows = {c: (dict(r, img=embed(r["img"])) if r.get("img") else r) for c, r in rows.items()}
            gs.append(dict(g, rows=rows, **({"glyphs": gl} if gl else {})))
        data = {"book": book, "per_page": pp, "groups": gs, "hint": hint}
        stat = {"groups": len(gs), "pages": -(-len(gs) // pp),
                "tiles": sum(len(r["tiles"]) for g in gs for r in g["rows"].values())}
    elif page_type in ("pair_whitelist", "seg_cause"):
        pp = per_page or 6
        gs = [dict(g, tiles=[[t[0], embed(t[1]), *t[2:]] for t in g.get("tiles", [])],
                   **({"cells": [dict(c, img=embed(c.get("img"))) for c in g["cells"]]} if "cells" in g else {})) for g in items]
        data = {"book": book, "per_page": pp, "groups": gs, "options": list(pt.options), "hint": hint}
        stat = {"groups": len(gs), "pages": -(-len(gs) // pp)}
    elif page_type == "near_pair":
        pp = per_page or 4
        gs = [dict(g, ex_a=[[t[0], embed(t[1])] for t in g.get("ex_a", [])],
                   ex_b=[[t[0], embed(t[1])] for t in g.get("ex_b", [])], diff=embed(g.get("diff")),
                   cells=[dict(c, img=embed(c.get("img"))) for c in g.get("cells", [])]) for g in items]
        data = {"book": book, "per_page": pp, "pairs": gs, "hint": hint,
                "n_cells": sum(len(g["cells"]) for g in gs)}
        stat = {"pairs": len(gs), "cells": data["n_cells"], "pages": -(-len(gs) // pp)}
        Path(out).with_suffix(".items.json").write_text(
            json.dumps(pair_audit.strip_images(items), ensure_ascii=False), encoding="utf-8")
    elif page_type == "lib_audit":
        pp = per_page or 6
        gs = [dict(g, tiles=[dict(t, img=embed(t.get("img"))) for t in g.get("tiles", [])]) for g in items]
        data = {"book": book, "per_page": pp, "groups": gs, "hint": hint,
                "n_tiles": sum(len(g["tiles"]) for g in gs)}
        stat = {"groups": len(gs), "tiles": data["n_tiles"], "pages": -(-len(gs) // pp)}
        Path(out).with_suffix(".items.json").write_text(
            json.dumps(pair_audit.strip_images(items), ensure_ascii=False), encoding="utf-8")
    elif page_type == "glyph_quality":
        pp = per_page or 24
        its = [dict(r, ctx=embed(r["ctx"]), ref=embed(r["ref"]),
                    crops=[dict(c, img=embed(c["img"])) for c in r["crops"]]) for r in items]
        data = {"book": book, "per_page": pp, "items": its, "hint": hint, "box": box,
                "options": [[o, gq_mod.LABEL_NAMES[o]] for o in pt.options], "n_excluded": n0 - len(items)}
        stat = {"items": len(its), "crops": sum(len(r["crops"]) for r in its), "pages": -(-len(its) // pp)}
    elif page_type == "gold_sample":
        pp = per_page or 10
        its = [dict(r, img=embed(r.get("img")), **({"strip": [embed(x) for x in r["strip"]]} if r.get("strip") else {}))
               for r in items]
        data = {"book": book, "per_page": pp, "items": its, "hint": hint, "mode": mode}
        stat = {"items": len(its), "pages": -(-len(its) // pp)}
    elif page_type == "closeout":
        pp = per_page or 12
        data = {"book": book, "per_page": pp, "items": list(items), "options": list(pt.options), "hint": hint}
        stat = {"items": len(items), "pages": -(-len(items) // pp)}
    else:
        raise SystemExit(f"页型 {page_type} 还没有模板")
    if title is None and pt.key == "char_card" and not rest_ok:
        title = "一字一卡（疑难格审定）"
    Path(out).write_text(render(pt, data, title), encoding="utf-8")
    stat["excluded"] = excluded_n if excluded_n is not None else n0 - len(items)
    stat["bytes"] = Path(out).stat().st_size
    stat["page_type"], stat["tpl_version"] = pt.key, pt.version
    return stat
