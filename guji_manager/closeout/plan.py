"""出单（cv `republish.py prep`）调用：把 A01–A03 现算后写进待审单。

出单时新 char 在导出目录、标点／专名还在 book-text 的版本目录里，所以 A01（锚点指向不存在的格或校验字不符）
和 A02（给了格级对照表时）可以在这里算；A03 要比对 book-text 里 char 的新旧两版（`check_anchor_drift`），
新 char 还没进 book-text 时算不出，留到文本推 dev 后再现算（`guji closeout derive`）。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import anchors, derive


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def stamp_pending(pending: Path, export_char: Path, text_vdir: Path, chapter: str, rows=None) -> dict:
    """读 `export_char`（新 char）和 `text_vdir/<chapter>.punct|entity.json`，现算锚点类原因，写进 `pending`（就地）。
    没有标点也没有专名文件就什么都不写。返回计数（`anchors.stamp` 的 Counter 转 dict，加 items 条数）。"""
    if not pending.is_file():
        return {}
    punct = _load(text_vdir / f"{chapter}.punct.json")
    entity = _load(text_vdir / f"{chapter}.entity.json")
    if punct is None and entity is None:
        return {}
    char = _load(export_char)
    if char is None:
        raise FileNotFoundError(export_char)
    items = derive.derive(char, punct, entity, rows)
    doc = json.loads(pending.read_text(encoding="utf-8"))
    n = anchors.stamp(doc, items)
    pending.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"items": len(items), "appended": n["appended"], "new": n["new"],
            **{r.value: n[r.value] for r in anchors.ANCHOR_REASONS}}
