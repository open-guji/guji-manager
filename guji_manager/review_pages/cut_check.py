"""逐格切线审查页（cut_check）：一格一张小图，上下各带半个邻格，标出这格的上、下切线，人点哪条切线不准。

用途：切字 benchmark（CV2 cut-bench）L2 层——字与字之间的切点准不准（字连在一起处切进了邻字、切掉了本字笔画）。
只看字与字之间：列首字的上切线、列尾字的下切线（字与边框之间）不画、不审；左右宽窄也不审。
输入（一格一行）：{id(格号，如 qtw:053:76:3:5), vol, page, col, slot?, img(图，调用者裁好：上到上一格中线、下到下一格中线),
  top:y|null, bottom:y|null(切线在图里的 y 像素；列首／列尾那条给 null), kind?, note?, noline?(true＝不画平均线，线已烧在图里，如折线；点图上／下半的点击区仍按 top/bottom 分；1.1.0), screen?(分屏键，缺省按 vol/page/col)}
poly?([[x,y]…] 图内像素，从右到左；给了就在图上画可改的折线：拖点、加点、删点，改过记 label=fix 并存 poly；1.3.0)。
页面级：build `--box N` 定卡片图高（px，缺省 220；1.2.0）。
同一屏的格按输入顺序（列内从上到下）排开。
结果文档：{page_type:"cut_check", cell(格号), label: ok|bad|unsure|fix, bad:["top"|"bottom"…], poly?(label=fix 时，图内像素), how, t}。
how=page_ok 是「本屏其余都对」一键补的。
"""
from __future__ import annotations

from .col_check import png_size

LABELS = ("ok", "bad", "unsure", "fix")


def normalize(items: list[dict], root=None) -> list[dict]:
    from pathlib import Path
    out, screens = [], {}
    for r in items:
        p = Path(r["img"])
        if root and not p.exists():
            p = Path(root) / p.name
        if not p.exists():
            raise SystemExit(f"{r['id']}：格图找不到 {r['img']}")
        w, h = png_size(p)
        top = None if r.get("top") is None else float(r["top"])
        bottom = None if r.get("bottom") is None else float(r["bottom"])
        if top is None and bottom is None and not r.get("poly"):
            continue      # 一列只有一格：没有字与字之间的切线
        key = r.get("screen") or f"{r.get('vol')}:{r.get('page')}:{r.get('col')}"
        out.append({"id": r["id"], "vol": r.get("vol"), "page": r.get("page"), "col": r.get("col"), "slot": r.get("slot"),
                    "img": str(p), "iw": w, "ih": h, "top": top, "bottom": bottom, "kind": r.get("kind"), "noline": bool(r.get("noline")),
                    "note": r.get("note"),
                    **({"poly": [[float(x), float(y)] for x, y in r["poly"]]} if r.get("poly") else {}), "screen": screens.setdefault(key, len(screens))})
    return out


def labels_from_docs(docs: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for d in docs:
        if d.get("page_type") != "cut_check" or d.get("how") not in ("click", "page_ok") or d.get("label") not in LABELS:
            continue
        cell = d.get("cell") or d.get("id")
        if cell not in out or (d.get("t") or 0) >= (out[cell].get("t") or 0):
            out[cell] = d
    return out


def label_rows(labels: dict) -> list[dict]:
    return [{"id": i, "label": d["label"], "bad": d.get("bad") or [], "how": d.get("how"), "t": d.get("t"),
             **({"poly": d["poly"]} if d.get("poly") else {})}
            for i, d in sorted(labels.items())]
