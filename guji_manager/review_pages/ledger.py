"""用时与改判台账：每用一次人审页记一行，按（页型，模板版本）统计，指导模板优化。

行：{ts, page_type, tpl_version, book, page, cells, secs, overturn, pre_wrong, by_kind}
- cells：这一页给人看的格（卡片页算样例格）；secs：人在页上的有效秒数；
- overturn：人改判数（选了与预选不同的答案，含标「不对」）；
- pre_wrong：预选错的格数（通常等于 overturn，卡片页另有跟随格抽检结果）；
- by_kind：{分歧类型: [格数, 改判数]}，用来看哪类预选错得多。
台账是 jsonl，追加写；放哪由调用者定（默认 $GUJI_REVIEW_LEDGER 或 ./review_ledger.jsonl）。
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from pathlib import Path

HINT_OVERTURN = 0.15      # 某类改判率超过这个数，提示改预选来源
HINT_SECS = 6.0           # 每格超过这个秒数，提示换页型或合卡


def default_path() -> Path:
    return Path(os.environ.get("GUJI_REVIEW_LEDGER", "review_ledger.jsonl"))


def record(path: Path, **row) -> dict:
    row.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
    for k in ("page_type", "tpl_version", "cells", "secs", "overturn"):
        if k not in row:
            raise ValueError(f"台账缺字段 {k}")
    row.setdefault("pre_wrong", row["overturn"])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def read(path: Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def from_result_docs(docs: list[dict], page_type: str, tpl_version: str, book: str | None = None) -> list[dict]:
    """把页面存回 db 的结果文档折成台账行（每页一行）。

    逐项文档（how=click/page_ok）按 page 归并，用时取同页的 secs 文档；旧按页文档（items 或 ok/bad）原样入账。
    未确认的项（没有文档）不入账。"""
    from . import results
    rows = []
    item_docs = [d for d in docs if d.get("how") in ("click", "page_ok") and "items" not in d and "id" in d]
    if item_docs:
        secs = results.secs_by_page(docs)
        by_page: dict = defaultdict(list)
        for d in results.flatten(item_docs).values():
            by_page[d.get("page")].append(d)
        for pg, its in sorted(by_page.items(), key=lambda kv: (kv[0] is None, kv[0])):
            kinds: dict[str, list[int]] = defaultdict(lambda: [0, 0])
            over = 0
            for i in its:
                o = int(i.get("pick") != i.get("pre")) if "pre" in i else int(bool(i.get("bad")))
                over += o
                k = i.get("kind") or "-"
                kinds[k][0] += 1; kinds[k][1] += o
            rows.append({"page_type": page_type, "tpl_version": its[0].get("tpl_version", tpl_version),
                         "book": its[0].get("book", book), "page": pg, "cells": len(its),
                         "secs": secs.get(pg, 0), "overturn": over, "pre_wrong": over, "by_kind": dict(kinds)})
    for d in docs:
        if results.is_secs(d) or d in item_docs:
            continue
        if "id" in d and "v" in d and "items" not in d:       # char_card 逐格文档，按页入账另有读法
            continue
        if "items" in d:
            items = d["items"]
            cells = len(items)
            over = sum(1 for i in items if i.get("pick") != i.get("pre"))
            kinds = defaultdict(lambda: [0, 0])
            for i in items:
                k = i.get("kind") or "-"
                kinds[k][0] += 1
                kinds[k][1] += int(i.get("pick") != i.get("pre"))
        elif "ok" in d or "bad" in d:                          # char_grid 旧按页文档
            cells = len(d.get("ok", [])) + len(d.get("bad", []))
            over = len(d.get("bad", []))
            kinds = {"-": [cells, over]}
        else:
            continue
        rows.append({"page_type": page_type, "tpl_version": d.get("tpl_version", tpl_version),
                     "book": d.get("book", book), "page": d.get("page"), "cells": cells,
                     "secs": d.get("secs", 0), "overturn": over, "pre_wrong": over,
                     "by_kind": dict(kinds)})
    return rows


def summarize(rows: list[dict]) -> list[dict]:
    g: dict[tuple, dict] = {}
    for r in rows:
        k = (r["page_type"], r["tpl_version"])
        s = g.setdefault(k, {"page_type": k[0], "tpl_version": k[1], "pages": 0, "cells": 0, "secs": 0.0,
                             "overturn": 0, "by_kind": defaultdict(lambda: [0, 0])})
        s["pages"] += 1
        s["cells"] += r["cells"]; s["secs"] += r["secs"]; s["overturn"] += r["overturn"]
        for kind, (n, o) in (r.get("by_kind") or {}).items():
            s["by_kind"][kind][0] += n; s["by_kind"][kind][1] += o
    out = []
    for s in g.values():
        c = s["cells"] or 1
        s["sec_per_cell"] = round(s["secs"] / c, 2)
        s["overturn_rate"] = round(s["overturn"] / c, 4)
        s["by_kind"] = {k: {"cells": n, "overturn": o, "rate": round(o / n, 3) if n else 0.0}
                        for k, (n, o) in s["by_kind"].items()}
        s["hints"] = hints(s)
        out.append(s)
    return sorted(out, key=lambda s: (s["page_type"], s["tpl_version"]))


def hints(s: dict) -> list[str]:
    h = []
    for k, v in s["by_kind"].items():
        if k != "-" and v["cells"] >= 20 and v["rate"] > HINT_OVERTURN:
            h.append(f"分歧类型 {k} 预选改判率 {v['rate']:.0%}（{v['overturn']}/{v['cells']}），改它的预选来源或排序")
    if s["sec_per_cell"] > HINT_SECS:
        h.append(f"每格 {s['sec_per_cell']} 秒偏慢，考虑合卡或换页型")
    return h
