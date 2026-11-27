"""切分 A/B 整列抽查 items（col_ab）：只收切法变了的列，框＝新切法，旧线被换掉的画红线。"""
import json

from PIL import Image

from guji_manager.review_pages import col_ab


def _rs(path, cols):
    """cols：{列号: ([(y0, y1)…], flags)}；格宽 x 100–160（右上原点）。"""
    path.mkdir(parents=True, exist_ok=True)
    columns = [{"col": k, "flags": fl, "cells": [
        {"slot": i + 1, "kind": "char", "quad_page": [[100, a], [160, a], [160, b], [100, b]]}
        for i, (a, b) in enumerate(ys)]} for k, (ys, fl) in cols.items()]
    (path / "p0005.json").write_text(json.dumps({"cells": {"columns": columns}}), encoding="utf-8")


def test_ab_items_only_changed_columns(tmp_path):
    old, new, pages = tmp_path / "old" / "42", tmp_path / "new" / "42", tmp_path / "pages"
    same = [(10, 100), (100, 200), (200, 300)]
    _rs(old / "row_segment", {1: (same, []), 2: (same, [])})
    _rs(new / "row_segment", {1: (same, []), 2: ([(10, 100), (100, 230), (230, 300)], ["boundary_net：200→230"])})
    pages.mkdir()
    Image.new("L", (400, 400), 255).save(pages / "5.png")
    for flag in ("boundary_net", None):
        its = col_ab.build_items(old, new, pages, tmp_path / f"out{flag}", flag=flag)
        assert [r["id"] for r in its] == ["42:5:2"]
        r = its[0]
        assert [c["key"] for c in r["cells"]] == ["42:5:2:1", "42:5:2:2", "42:5:2:3"]
        assert "（1 条）" in r["note"]              # 旧线 200 被换掉
        assert (tmp_path / f"out{flag}" / "items.jsonl").read_text(encoding="utf-8").count("\n") == 1
