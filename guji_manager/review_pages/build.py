"""出页：选页型 → 填模板 → 单文件 HTML（用 Artifact 发布，要 db 能力）。

输入统一用 items（jsonl 或 json 列表），每项字段按页型：
  char_card / char_grid：{id, pre(预选字), pre_conf?, kind?, img(图文件路径或 data URI), cov?}
    img 用 crop.py 按 cell_shrink 字框裁（不要按 row_segment 的 quad 裁，会带进边框线）
    ref_img?/ref_label?（char_card 1.5）：标准字形图（如维基 SKQS 僻字图）与本书切图并排，label 默认「标准」
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
  closeout：{id, label, n, rate?, examples?[格号 或 {id, img, note?}…], pre?(放行|留人审|算法再处理)}；img 按 cell_shrink 字框裁
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
from . import seg_cut as sc_mod
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
    html = _read(pt.template).replace("/*FONT_CSS*/", data.pop("font_css", ""))
    html = html.replace("/*SHELL*/", _read("_shell.html").replace("/*TITLE*/", pt.title)) if "/*SHELL*/" in html else html
    html = html.replace("/*PAGER_JS*/", _read("_pager.js")).replace("/*STORE_JS*/", _read("_store.js"))
    html = html.replace("/*COMMON_CSS*/", _read("_common.css")).replace("/*COMMON_JS*/", _read("_common.js"))
    return html.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False))


FONT_NAMES = ["I.Ming-8.10.ttf", "Jigmo.ttf", "Jigmo2.ttf", "Jigmo3.ttf"]   # cv fonts/ 下：I.Ming(IPA)、Jigmo(CC0)，按此顺序补字


def default_fonts(font_dir) -> list[str]:
    out = []
    for n in FONT_NAMES:
        for sub in ("iming", "jigmo", ""):
            p = Path(font_dir) / sub / n
            if p.exists():
                out.append(str(p)); break
    return out


def _bundled_fonts() -> list[str]:
    """本包自带 Jigmo3 20250912（CC0，补到 Unicode 17 扩展 J，如 U+32A39）；排在最后，只补前面字体没有的字。"""
    p = Path(__file__).parent / "fonts" / "Jigmo3-20250912.ttf"
    return [str(p)] if p.exists() else []


def auto_fonts() -> list[str]:
    """没显式给 --font/--font-dir 时自动找字体：环境变量 GUJI_FONT_DIR，或已装 open_guji_cv 旁的 fonts/（Jigmo CC0 覆盖到扩展 H、I.Ming）。
    找不到返回空表（页上缺字改显码位，不会空白）。"""
    import os
    cands = [os.environ.get("GUJI_FONT_DIR")]
    try:
        import open_guji_cv
        cands.append(str(Path(open_guji_cv.__file__).resolve().parent.parent / "fonts"))
    except ImportError:
        pass
    for d in cands:
        if d and Path(d).is_dir():
            fs = default_fonts(d)
            if fs:
                return fs + _bundled_fonts()
    return _bundled_fonts()


def _strings(o):
    if isinstance(o, str):
        if not o.startswith("data:"):
            yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            if k not in ("img", "ref_img", "strip", "col_img", "nb_imgs"):
                yield from _strings(k); yield from _strings(v)
    elif isinstance(o, (list, tuple)):
        for v in o:
            yield from _strings(v)


def font_subset_css(data: dict, fonts: list[str]) -> tuple[str, list[str]]:
    """本页用到的字（候选、说明、上下文、预选字）按给定字体顺序子集化成 woff2，base64 内嵌，排在 --font-glyph 最前。
    返回（CSS，所有字体都没有的字）；没有 fonttools/brotli 时返回空 CSS 并把缺字当作全部（页上改显码位）。"""
    import base64, io
    chars = sorted({c for t in _strings(data) for c in t if ord(c) >= 0x2E80 and not 0xE000 <= ord(c) <= 0xF8FF
                    and not 0xF0000 <= ord(c) <= 0x10FFFF and not 0xFE00 <= ord(c) <= 0xFE0F})
    try:
        from fontTools.ttLib import TTFont
        from fontTools import subset as ftsub
    except ImportError:
        return "", chars
    try:
        import brotli  # noqa: F401
        flavor, mime = "woff2", "font/woff2"
    except ImportError:          # 没装 brotli 就用 woff（zlib），体积略大但不报错
        flavor, mime = "woff", "font/woff"
    left, css, fam = set(chars), [], []
    for i, fp in enumerate(fonts):
        if not left:
            break
        f = TTFont(fp, lazy=True)
        cm = f.getBestCmap()
        have = sorted(c for c in left if ord(c) in cm)
        if not have:
            continue
        opt = ftsub.Options(); opt.flavor = flavor; opt.layout_features = ["*"]; opt.notdef_outline = False
        sub = ftsub.Subsetter(opt); sub.populate(text="".join(have)); sub.subset(f)
        buf = io.BytesIO(); f.flavor = flavor; f.save(buf)
        css.append("@font-face{font-family:GujiSub%d;src:url(data:%s;base64,%s) format('%s')}" % (i, mime, base64.b64encode(buf.getvalue()).decode(), flavor))
        fam.append("GujiSub%d" % i)
        left -= set(have)
    if fam:
        css.append(":root{--font-glyph:%s,\"Noto Serif SC\",\"Songti SC\",\"SimSun\",serif}" % ",".join(fam))
    return "".join(css), sorted(left)


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
          fonts: list[str] | None = None) -> dict:
    """exclude：已录入的格号，出页时撤掉（点过即录入、不再上页）。
    rest_ok=False（char_card）：难认字页，没有「本页其余都对」，没点的格不算对，只存点过、改过的格。"""
    pt = get(page_type)
    if fonts is None and page_type in ("char_card", "char_grid"):
        fonts = auto_fonts()      # 1.3/1.7：扩展 G/H 等字系统字体常缺，默认内嵌子集（Jigmo）
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
        def _row(r):
            x = dict(r, img=embed(r.get("img")))
            if r.get("ref_img"):
                x["ref_img"] = embed(r["ref_img"])
            if r.get("col_img"):      # 1.6：整列图（本格红框）
                x["col_img"] = embed(r["col_img"])
            if r.get("nb_imgs"):      # 1.6：左右邻列图 [{img,label}]
                x["nb_imgs"] = [dict(n, img=embed(n["img"])) for n in r["nb_imgs"] if n.get("img")]
            return x
        rows = [_row(r) for r in items]
        cs = cards_mod.build_cards(rows, k, solo=not rest_ok)
        pp = per_page or (24 if not rest_ok else 8)
        data = {"book": book, "per_page": pp, "cards": cs, "n_cells": sum(c["n"] for c in cs), "rest_ok": rest_ok,
                "n_excluded": n0 - len(items)}
        if fonts:   # 本页用到的字子集化内嵌（1.5.1）；字体都没有的字页上显示码位，不留空白
            font_css, nofont = font_subset_css({"cards": cs}, fonts)
            data["font_css"], data["nofont"] = font_css, nofont
        stat = {"cards": len(cs), "cells": data["n_cells"], "shown": sum(len(c["samples"]) for c in cs),
                "pages": -(-len(cs) // pp)}
        (Path(out).with_suffix(".cards.json")).write_text(json.dumps(cs, ensure_ascii=False), encoding="utf-8")
    elif page_type == "char_grid":
        pp = per_page or 30
        tiles = [[r["id"], r["pre"], float(r.get("cov") or 0), embed(r.get("img")), r.get("n", 1)] for r in items]
        chars = {t[1] for t in tiles}
        data = {"book": book, "per_page": pp, "n_chars": len(chars),
                "n_cells": sum(t[4] for t in tiles), "tiles": tiles}
        if fonts:   # 页上字（字头）子集化内嵌；字体都没有的字页上显示码位
            font_css, nofont = font_subset_css({"chars": sorted(chars)}, fonts)
            data["font_css"], data["nofont"] = font_css, nofont
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
    elif page_type == "seg_cut":
        pp = per_page or 6
        its = [dict(r, img=embed(r["img"])) for r in sc_mod.normalize(items, root)]
        data = {"book": book, "per_page": pp, "items": its, "hint": hint,
                "options": [[o, n] for o, n in zip(pt.options, ("要切", "不切", "看不出"))]}
        stat = {"items": len(its), "pages": -(-len(its) // pp)}
    elif page_type in ("gold_sample", "ref_check"):
        if page_type == "ref_check":
            mode = "check"
            hint = hint or ("看图和上下文（专名、书名、套语最快）判整理本字对不对：对→点「对」；库首位对→点「改作 X」；都不对→点「错（填字）」；"
                            "看不准→「看不清」，不要硬改。疑整理本错的格排在最前。每点一下就存。")
        pp = per_page or 10
        its = [dict(r, img=embed(r.get("img")), **({"strip": [embed(x) for x in r["strip"]]} if r.get("strip") else {}))
               for r in items]
        data = {"book": book, "per_page": pp, "items": its, "hint": hint, "mode": mode}
        stat = {"items": len(its), "pages": -(-len(its) // pp)}
    elif page_type == "closeout":
        pp = per_page or 12
        # examples 的元素可以是格号字串，也可以是 {id, img(路径或 data URI), note?}（img 按 cell_shrink 字框裁）
        its = [dict(r, examples=[dict(e, img=embed(e.get("img"))) if isinstance(e, dict) else e
                                 for e in r.get("examples", [])]) for r in items]
        data = {"book": book, "per_page": pp, "items": its, "options": list(pt.options), "hint": hint}
        stat = {"items": len(items), "pages": -(-len(items) // pp)}
    else:
        raise SystemExit(f"页型 {page_type} 还没有模板")
    Path(out).write_text(render(pt, data), encoding="utf-8")
    stat["excluded"] = excluded_n if excluded_n is not None else n0 - len(items)
    stat["bytes"] = Path(out).stat().st_size
    stat["page_type"], stat["tpl_version"] = pt.key, pt.version
    return stat
