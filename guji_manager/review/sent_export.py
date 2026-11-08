# -*- coding: utf-8 -*-
"""精校待审单 pending.json 的 `sent` 字段导出（纯函数，不读写文件、不碰网络）。

格式（A32/A33/A31 2026-11-08 定稿）：
  sent: [{"t": 句文本(不含标点,一字一格), "at": "page:col:cell"(句首格), "n": 字数,
          "cells": [每字格号, 长度 n], "h": sent_hash(t, cells),
          "assumed_cells": [...可选],
          "marks": [{"kind":"punct","ch":"，","pos":k}   # pos=标记前字数 0..n，可表达开引号/书名号左半
                    {"kind":"entity","type":..,"start":s,"end":e,"entity_id":..|None,"status":..,
                     "targets":[..]可选,"coarse":..可选,"assumed":bool}]}]
偏移全部句内、以字为单位；实体 [start,end) 左闭右开。只收含待审格的句子；>80 字再按「；」「：」断。
"""
from __future__ import annotations

import hashlib

TERMINALS = set("。！？")
OPENERS = set("「『（“‘《〈")
SOFT_SPLIT = set("；：")
MAX_LEN = 80


def sent_hash(t: str, cells: list[str]) -> str:
    """h = sha1(t + "\\x00" + ",".join(cells)) 取前 12 位十六进制（A32 口径，出单侧与测试共用）。"""
    return hashlib.sha1((t + "\x00" + ",".join(cells)).encode("utf-8")).hexdigest()[:12]


def flatten_cells(char: dict) -> list[tuple[str, str]]:
    """char.json → [(锚点, 字)]，按读序（页→列→格）。"""
    out = []
    for pg in char.get("pages", []):
        for col in pg.get("columns", []):
            for c in col.get("cells", []):
                out.append((c["a"], c["c"]))
    return out


def _split(flat, punct_at: dict[int, list[str]]) -> list[tuple[int, int]]:
    """按 。！？（连同紧随其后的闭引号）切句；超长句再按 ；： 断。返回 [(start,end)) 全局格序。"""
    n = len(flat)
    bounds, start = [], 0
    for g in range(1, n + 1):
        marks = punct_at.get(g, [])
        if g == n or any(m in TERMINALS for m in marks):
            bounds.append((start, g)); start = g
    out = []
    for s, e in bounds:
        if e - s <= MAX_LEN:
            out.append((s, e)); continue
        cut = s
        for g in range(s + 1, e + 1):
            if any(m in SOFT_SPLIT for m in punct_at.get(g, [])) and g - cut >= 1 and g < e:
                out.append((cut, g)); cut = g
        out.append((cut, e))
    return [(s, e) for s, e in out if e > s]


def sent_export(char: dict, punct: dict | None, entity: dict | None, *,
                pending_cells: set[str] | None = None,
                assumed_cells: set[str] | None = None) -> list[dict]:
    flat = flatten_cells(char)
    idx = {a: i for i, (a, _) in enumerate(flat)}
    assumed_cells = assumed_cells or set()

    marks_g: list[tuple[int, str]] = []          # (全局位置 = 标记前字数, 标点)
    for p in (punct or {}).get("punctuations", []):
        if p.get("kind") in ("break", "heading"):
            continue
        i = idx.get(p.get("anchor"))
        if i is None:
            continue
        marks_g.append((i + 1 if p.get("pos", "after") == "after" else i, p["mark"]))
    punct_at: dict[int, list[str]] = {}
    for g, m in marks_g:
        punct_at.setdefault(g, []).append(m)

    ents = []
    for e in (entity or {}).get("entities", []):
        a = e.get("anchor") or {}
        s, en = idx.get(a.get("start")), idx.get(a.get("end"))
        if s is None or en is None or en < s:
            continue
        ents.append((s, en + 1, e))

    out = []
    for s, e in _split(flat, punct_at):
        cells = [flat[i][0] for i in range(s, e)]
        if pending_cells is not None and not (set(cells) & pending_cells):
            continue
        t = "".join(flat[i][1] for i in range(s, e))
        bad = [c for c in cells if c in assumed_cells]
        marks = []
        for g, m in marks_g:
            if s < g <= e or (g == s and m in OPENERS):
                marks.append((g - s, 0, {"kind": "punct", "ch": m, "pos": g - s}))
        for es, ee, ent in ents:
            if es >= s and ee <= e:
                tg = ent.get("target") or {}
                d = {"kind": "entity", "type": ent.get("type"), "start": es - s, "end": ee - s,
                     "entity_id": tg.get("entity_id"), "status": tg.get("status", "new_candidate"),
                     "assumed": bool(bad)}
                if tg.get("targets"):
                    d["targets"] = tg["targets"]
                if tg.get("coarse"):
                    d["coarse"] = tg["coarse"]
                marks.append((es - s, 1, d))
        marks.sort(key=lambda x: (x[0], x[1]))
        rec = {"t": t, "at": cells[0], "n": len(cells), "cells": cells, "h": sent_hash(t, cells),
               "marks": [m[2] for m in marks]}
        if bad:
            rec["assumed_cells"] = bad
        out.append(rec)
    return out
