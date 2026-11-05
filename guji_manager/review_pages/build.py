"""出页：选页型 → 填模板 → 单文件 HTML（用 Artifact 发布，要 db 能力）。

输入统一用 items（jsonl 或 json 列表），每项字段按页型：
  char_card / char_grid：{id, pre(预选字), pre_conf?, kind?, img(图文件路径或 data URI), cov?}
  pair_whitelist：{key, label?, pre(选项之一), n?, hint?, tiles:[[格号, 图, 说明?]]}
  codepoint：{key, chars:[字…], pre?(unify:X|other:X|split_follow|split_distinct), hint?,
             rows:{字:{adm?, kr?, tiles:[[格号, 图]…]}}}（见 codepoint.py）
  name_register / punct_check：同上，tiles 可省；lines:[文字行…] 放出处语句/带标点段落
  gold_sample / name_pick：{id, pre, left, right, cands:{字:[来源…]}, img?, kind?, fact?, pilot?}
图一律内嵌（缩略图由调用者准备好；这里只做 base64，不依赖 cv2/PIL）。
"""
from __future__ import annotations

import base64
import json
import mimetypes
from importlib import resources
from pathlib import Path

from . import cards as cards_mod
from . import codepoint as cp_mod
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


def render(pt: PageType, data: dict) -> str:
    if pt.template is None:
        raise SystemExit(f"页型 {pt.key} 还没有模板")
    data = {"page_type": pt.key, "tpl_version": pt.version, "coll": pt.doc_prefix,
            "kind_names": KIND_NAMES, **data}
    html = _read(pt.template)
    html = html.replace("/*SHELL*/", _read("_shell.html").replace("/*TITLE*/", pt.title)) if "/*SHELL*/" in html else html
    html = html.replace("/*COMMON_CSS*/", _read("_common.css")).replace("/*COMMON_JS*/", _read("_common.js"))
    return html.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False))


def build(page_type: str, items: list[dict], book: str, out, per_page: int | None = None, k: int = 5,
          hint: str | None = None) -> dict:
    pt = get(page_type)
    if page_type == "char_card":
        rows = [dict(r, img=embed(r.get("img"))) for r in items]
        cs = cards_mod.build_cards(rows, k)
        pp = per_page or 8
        data = {"book": book, "per_page": pp, "cards": cs, "n_cells": sum(c["n"] for c in cs)}
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
            gs.append(dict(g, rows=rows))
        data = {"book": book, "per_page": pp, "groups": gs, "hint": hint}
        stat = {"groups": len(gs), "pages": -(-len(gs) // pp),
                "tiles": sum(len(r["tiles"]) for g in gs for r in g["rows"].values())}
    elif page_type in ("pair_whitelist", "name_register", "punct_check"):
        pp = per_page or 6
        gs = [dict(g, tiles=[[t[0], embed(t[1]), *t[2:]] for t in g.get("tiles", [])]) for g in items]
        data = {"book": book, "per_page": pp, "groups": gs, "options": list(pt.options), "hint": hint}
        stat = {"groups": len(gs), "pages": -(-len(gs) // pp)}
    elif page_type in ("gold_sample", "name_pick"):
        pp = per_page or 10
        its = [dict(r, img=embed(r.get("img"))) for r in items]
        data = {"book": book, "per_page": pp, "items": its, "hint": hint}
        stat = {"items": len(its), "pages": -(-len(its) // pp)}
    else:
        raise SystemExit(f"页型 {page_type} 还没有模板")
    Path(out).write_text(render(pt, data), encoding="utf-8")
    stat["bytes"] = Path(out).stat().st_size
    stat["page_type"], stat["tpl_version"] = pt.key, pt.version
    return stat
