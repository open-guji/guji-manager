"""形近字对比卡（`near_pair`）与库内刻例审阅卡（`lib_audit`）：结果 → 逐格决定 → 人裁事件。

两个页型都是「字形库里的字对不对」这一类问题，结果最后都落成 `glyph_audit` / `confirm` 事件：

- `near_pair`：一对形近字（畫/書、全/今…）各摆库里 3–5 个人裁刻例，待审格放中间，选 A / B / 都不是 /
  看不清 / 切分有问题。每格一份逐项文档（`makeStore`，`i_<格号>`）：`{id, pair, v, pick?, how, t}`，`v` ∈ a | b | neither | unclear | seg。
- `lib_audit`：按字头列出库里该字的刻例，点哪个标「这条标错」并填应为的字。每例一份逐项文档：
  `{id, char, v, to?, how, t}`，`v` ∈ relabel（`to` 是应为的字）| evict（撤库）| near_form（两个都没错，只是形近）。

事件口径与体检卡一致（`feedback/glyph_audit.py`）：库里已有的刻例 → `glyph_audit` relabel / evict / near_form；
还没进库的待审格 → `confirm`（`step=seed_admit`，同 `char_review ingest`）。写事件只追加本机日志，
推中心库、出新 g 仍要用户点头。
"""
from __future__ import annotations

import json
from pathlib import Path


def strip_images(items: list[dict]) -> list[dict]:
    """sidecar 不存图，只存结果展开要用的字段。"""
    out = []
    for g in items:
        g = dict(g)
        if "cells" in g:
            g["cells"] = [{k: v for k, v in c.items() if k != "img"} for c in g["cells"]]
        if "tiles" in g and g["tiles"] and isinstance(g["tiles"][0], dict):
            g["tiles"] = [{k: v for k, v in t.items() if k != "img"} for t in g["tiles"]]
        for k in ("ex_a", "ex_b", "diff"):
            g.pop(k, None)
        out.append(g)
    return out


def near_pair_decisions(items: list[dict], docs: list[dict]) -> list[dict]:
    """items：build 写的 `<out>.items.json`；docs：结果文档（只认 `id`+`v`+`pair`，同一格后写覆盖，按 `t`）。
    返回逐格决定 `{id, pair, status, char?, inst, cur}`：status = pick（定了某字）| neither | unclear | seg。"""
    by_id = {}
    for g in items:
        for c in g.get("cells", []):
            by_id[c["id"]] = (g, c)
    from . import results
    last = {i: d for i, d in results.flatten(docs).items()                 # 只认点过的（how），同格 t 新的为准
            if i in by_id and d.get("v") and d.get("pair") in (None, by_id[i][0]["key"])}
    out = []
    for i, d in last.items():
        g, c = by_id[i]
        v = d["v"]
        base = {"id": i, "pair": g["key"], "inst": bool(c.get("inst")), "cur": c.get("cur")}
        if v in ("a", "b"):
            out.append(base | {"status": "pick", "char": g[v]})
        elif v == "neither" and d.get("pick"):
            out.append(base | {"status": "pick", "char": d["pick"]})
        elif v in ("neither", "unclear", "seg"):
            out.append(base | {"status": v})
    return sorted(out, key=lambda r: r["id"])


def lib_audit_decisions(items: list[dict], docs: list[dict]) -> list[dict]:
    known = {t["id"]: g["char"] for g in items for t in g.get("tiles", [])}
    from . import results
    last = {i: d for i, d in results.flatten(docs).items() if i in known and d.get("v")}
    out = []
    for i, d in sorted(last.items()):
        cur, v = known[i], d["v"]
        if v == "relabel":
            to = (d.get("to") or "").strip()
            if len(to) == 1 and to != cur:
                out.append({"id": i, "cur": cur, "status": "relabel", "char": to})
        elif v in ("evict", "near_form"):
            out.append({"id": i, "cur": cur, "status": v, "peer": (d.get("to") or "").strip() or None})
    return out


def to_specs(decisions: list[dict], book: str, source: str) -> list[dict]:
    """逐格决定 → 事件说明（kind/key/book/payload），不依赖 cv，可直接写 jsonl 复核。
    定的字等于库里现标的字：不出事件（只是认同）。"""
    specs = []
    for r in decisions:
        st = r["status"]
        if st == "pick":
            if r.get("cur") == r["char"]:
                continue
            if r.get("inst"):
                specs.append({"kind": "glyph_audit", "step": "glyph_audit", "key": r["id"], "book": book,
                              "payload": {"v": "relabel", "char": r["char"], "instance_id": r["id"], "source": source}})
            else:
                specs.append({"kind": "confirm", "step": "seed_admit", "key": r["id"], "book": book,
                              "payload": {"v": "confirm", "shape": r["char"], "source": source}})
        elif st == "relabel":
            specs.append({"kind": "glyph_audit", "step": "glyph_audit", "key": r["id"], "book": book,
                          "payload": {"v": "relabel", "char": r["char"], "instance_id": r["id"], "source": source}})
        elif st == "evict":
            specs.append({"kind": "glyph_audit", "step": "glyph_audit", "key": r["id"], "book": book,
                          "payload": {"v": "evict", "instance_id": r["id"], "source": source}})
        elif st == "near_form":
            p = {"v": "near_form", "instance_id": r["id"], "char_self": r.get("cur"), "source": source}
            if r.get("peer"):
                p["peer_char"] = r["peer"]
            specs.append({"kind": "glyph_audit", "step": "glyph_audit", "key": r["id"], "book": book, "payload": p})
    return specs


def read_docs(d) -> list[dict]:
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(Path(d).rglob("*.json"))]
