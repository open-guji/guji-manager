"""guji seg check 的汇总（seg_check.aggregate／parse_skip／recall）：只用自造的筛查行。"""
from __future__ import annotations

import json

from guji_manager import seg_check as sc


def test_parse_skip_and_book_keys():
    sk = sc.parse_skip("01:39-41,01:54,04:124")
    assert sk == {"01": {39, 40, 41, 54}, "04": {124}}
    assert sc._skip_for("vol01", sk) == {39, 40, 41, 54} and sc._skip_for("01", sk) == {39, 40, 41, 54}
    assert sc._skip_for("4", sk) == {124}


def test_aggregate_dispositions():
    rows = {
        "pin_slots": [("b", 5, 1, "", "钉子有产物无 3；产物有钉子无 -")],
        "layout_slots": [("b", 5, 2, "", "异数：…")],
        "orphan": [("b", 5, 3, 0.8, "mid 墨 900px bbox [0, 1, 2, 3]")],
        "cell_flags": [("b", 5, 4, "FOR", "7 fr 0.1"), ("b", 5, 6, "JZW", "3a")],
        "edge_ink": [], "edge_frame_only": [],
    }
    causes = {(5, 7): [("2", "A3", True)], (5, 8): [("4", "A1", False)]}
    out = {r["列"]: r["处置"] for r in sc.aggregate("b", rows, {(5, 1), (5, 6), (5, 9)}, causes, skip=set())}
    assert out == {"b:5:1": "格号不符", "b:5:2": "版式不符", "b:5:3": "需钉子", "b:5:4": "公用清格",
                   "b:5:6": "已钉·复核", "b:5:7": "对位（○）", "b:5:8": "原因码·看图", "b:5:9": "已钉"}
    out = {r["列"]: r["处置"] for r in sc.aggregate("b", rows, set(), {}, skip={5})}
    assert out["b:5:3"] == "点名跳过" and out["b:5:2"] == "点名跳过"
    assert {r["处置"] for r in sc.aggregate("b", rows, set(), {}, skip=set(), head_pages=5)} == {"卷首页", "格号不符"}  # 格号不符照样先报


def test_recall_only_counts_fixes_after_products(tmp_path):
    d = tmp_path / "b" / "row_segment"
    d.mkdir(parents=True)
    (d / "_manifest.jsonl").write_text(
        json.dumps({"key": "p0005", "ts": 1_800_000_000}) + "\n", encoding="utf-8")
    ruler = [{"book": "b", "page": 5, "col": 3, "ts": "2027-12-01T00:00:00Z"},       # 产物之后修的：量
             {"book": "b", "page": 5, "col": 4, "ts": "2027-12-01T00:00:00Z"},
             {"book": "b", "page": 5, "col": 9, "ts": "2020-01-01T00:00:00Z"}]       # 产物之前修的：不量
    rows = {"orphan": [("b", 5, 3, 0.8, "mid")], "edge_ink": []}
    rc = sc.recall(ruler, rows, tmp_path, ["b"], None, {})
    assert rc["n"] == 2 and rc["already_fixed"] == 1 and rc["any"] == 1 and rc["missed"] == ["b:5:4"]


def test_recall_manual_cells_by_pin_stale(tmp_path):
    ruler = [{"book": "b", "page": 5, "col": 3, "source": "manual-cells", "ts": "2020-01-01T00:00:00Z"},
             {"book": "b", "page": 5, "col": 4, "source": "manual-cells", "ts": "2030-01-01T00:00:00Z"}]
    rows = {"pin_stale": [("b", 5, 3, "", "")], "orphan": [("b", 5, 3, 0.8, "mid")]}
    rc = sc.recall(ruler, rows, tmp_path, ["b"], None, {})
    assert rc["n"] == 1 and rc["any"] == 1 and rc["already_fixed"] == 1
    agg = {r["列"]: r["处置"] for r in sc.aggregate("b", rows, set(), {}, skip=set())}
    assert agg["b:5:3"] == "钉子未生效"
