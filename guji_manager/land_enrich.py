"""收尾里把 cv ``pending_cells`` 的最小单格（cell/review/img）并成网站要的完整条目 doc（CV4 11-24 样例与合并要求）。

次序（同 cv scripts/zhengli/republish.py prep 现行做法，逻辑都在 manager 的 review/ 下，这里只编排）：

1. ``proof_fields.pending_fields(card)``：why、c、candidates、alt、prior…（卡来自 ``guji audit alt``，复审格走 ``--extra``）
2. 复审格：``recheck: true`` ＋ 说明／旧人投票 id／旧字（``read_recheck``）
3. 同字对照自检 ``seg_kind``／``seg_feature``，``why`` 与 ``seg_defect`` 合并（**还没接**，见 ``PENDING_STEPS``）
4. ``add_causes``：``pending_reason``、``pending_reason_cause(_detail)``、``grp``、``refc``
5. 锚点原因 ``pending_reason_also``（A01–A03，book-text 定稿后算，**还没接**）
6. ``alt[].g`` 字形图改按内容寻址（**还没接**）

``PENDING_STEPS`` 非空时 ``guji land --apply`` 不开放（见 ``land.APPLY_READY``）。
"""
from __future__ import annotations

import json
from pathlib import Path

PENDING_STEPS = ("seg_selfcheck", "anchor_reasons", "alt_glyph_content_addressed")


def read_recheck(path: Path, book: str) -> dict[str, dict]:
    """复审清单：``格号[\\t说明[\\t旧人裁 id[\\t旧人裁的字[\\t旧人裁时间]]]]``（同 cv pending_list.read_recheck）。"""
    out: dict[str, dict] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [x.strip() for x in line.split("\t")]
        cell = parts[0].removeprefix(f"{book}:")
        if cell in ("格位", "格号", "cell"):
            continue
        note, pid, pc, pts = (parts[1:] + ["", "", "", ""])[:4]
        info: dict = {}
        if note:
            info["note"] = note
        if pc:
            info["prior"] = {"c": pc, **({"id": pid} if pid else {}), **({"ts": pts} if pts else {})}
        out.setdefault(cell, {}).update(info)
    return out


def merge_cards(cells: list[dict], cards: dict[str, dict]) -> list[dict]:
    """第 1 步：每格并入 ``pending_fields(card)``；卡里没有的格只带 cv 给的 cell/review/img。cv 给的键优先（img 是按内容寻址的单格图）。"""
    from .review.proof_fields import pending_fields
    out = []
    for c in cells:
        card = cards.get(c["cell"])
        extra = pending_fields(card) if card else {}
        out.append({**extra, **c})
    return out


def merge_recheck(cells: list[dict], rc: dict[str, dict]) -> list[dict]:
    """第 2 步：复审格。cv 的 ``extra`` 里没给说明的格也要标 recheck。"""
    out = []
    for c in cells:
        info = rc.get(c["cell"])
        out.append({**c, "recheck": True, **info} if info is not None else c)
    return out


def add_causes(cells: list[dict], products: Path, book: str, glyph_db: Path | None = None) -> list[dict]:
    """第 4 步：待审原因与成因码细分（同 cv republish.add_causes，只是在内存 doc 上做）。"""
    from .review.causes import book_causes
    from .review.reasons import reasons_for_pending, stamp
    res = book_causes(products, book)
    doc = {"cells": [dict(c) for c in cells]}
    stamp(doc, reasons_for_pending(doc, products, book, glyph_db=glyph_db))
    for c in doc["cells"]:
        r = res.get(c["cell"])
        if not r:
            continue
        c.pop("cause", None)
        c.pop("cause_detail", None)
        c["pending_reason_cause"] = r["cause"]
        if r.get("detail"):
            c["pending_reason_cause_detail"] = r["detail"]
        for k in ("grp", "refc"):
            if r.get(k):
                c[k] = r[k]
    return doc["cells"]


def load_cards(ws: Path, book: str) -> dict[str, dict]:
    """``guji audit alt <册>`` 写的 ``reports/<册>/<册>.cards.alt.json`` → {格号: 卡}。"""
    f = Path(ws) / "reports" / book / f"{book}.cards.alt.json"
    if not f.exists():
        return {}
    doc = json.loads(f.read_text(encoding="utf-8"))
    cards = doc["cards"] if isinstance(doc, dict) else doc
    return {str(c.get("cell") or c.get("a")): c for c in cards if c.get("cell") or c.get("a")}


def enrich(cells: list[dict], *, ws: Path, book: str, products: Path, recheck: Path | None = None,
           glyph_db: Path | None = None) -> list[dict]:
    out = merge_cards(cells, load_cards(ws, book))
    if recheck and Path(recheck).exists():
        out = merge_recheck(out, read_recheck(recheck, book))
    return add_causes(out, products, book, glyph_db)
