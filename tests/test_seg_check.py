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


def test_geo_ref_ok_is_hint_not_structural():
    """cv geo_ref_ok（格高离群但参校字证实）降成提示列：列出来供抽看，不算结构、不进闸；同列另有结构 flag 照报需钉子。"""
    rows = {"geo_ref_ok": [("b", 5, 1, "cell_size", "6×0.2"), ("b", 5, 2, "half_width", "3a×0.69")],
            "cell_size": [("b", 5, 2, "short", "8×0.3")]}
    out = {r["列"]: (r["类"], r["处置"]) for r in sc.aggregate("b", rows, set(), {}, skip=set())}
    assert out == {"b:5:1": ("提示", "格高·参校证实"), "b:5:2": ("结构", "需钉子")}


def test_align_drift_is_structural_even_with_ref_gap_codes():
    """cv align_drift（R017 对位串错）算结构「需钉子」；列里带 A6／A9 也照报（劈出来那格整理本本来就没字）。"""
    rows = {"align_drift": [("b", 5, 1, "split,unsettled", "bnObOOb"), ("b", 5, 2, "run", "OObbbOO")]}
    causes = {(5, 2): [("3", "A6", False)]}
    out = {r["列"]: r["处置"] for r in sc.aggregate("b", rows, set(), causes, skip=set())}
    assert out["b:5:1"] == "需钉子" and out["b:5:2"] == "需钉子"


def test_align_drift_whole_page_is_hint():
    """同页报出 ≥3 列（cv 在 value 加 page）是整页的事（透印、版式），降成提示，不进闸。"""
    rows = {"align_drift": [("b", 7, 1, "pair,page", "ObbbOO"), ("b", 7, 2, "run,page", "OBbBBO")]}
    out = {r["列"]: (r["类"], r["处置"], r["结构分"]) for r in sc.aggregate("b", rows, set(), {}, skip=set())}
    assert out == {"b:7:1": ("提示", "对位串错·整页", 0), "b:7:2": ("提示", "对位串错·整页", 0)}


def test_cell_size_is_structural():
    rows = {"cell_size": [("b", 5, 2, "tall", "18×1.88")]}
    assert [r["处置"] for r in sc.aggregate("b", rows, set(), {}, skip=set())] == ["需钉子"]


def test_defect_and_uniform_rows():
    rows = {"seg_defect": [("b", 3, 1, "clipped", "21 同字墨高 0.77"), ("b", 3, 2, "frame_residue", "1 同字… 重"),
                           ("b", 3, 3, "bleed", "5 edge_blob")],
            "page_pitch": [("b", 4, 1, 0.85, " 本页格高 100px")],
            "half_width": [("b", 4, 2, 1, "6ab 差0.6 本册半格宽 50px")]}
    agg = {r["列"]: r["处置"] for r in sc.aggregate("b", rows, set(), {}, skip=set())}
    assert agg == {"b:3:1": "需钉子", "b:3:2": "公用清格", "b:3:3": "公用清格", "b:4:1": "需钉子", "b:4:2": "需钉子"}


def test_cut_through_is_structural():
    rows = {"cut_through": [("b", 27, 6, "中", "8|9 切割量 747px，挪 +31px 可降到 0px，裁判 0.91→0.99 分歧 653→112px")]}
    (r,) = sc.aggregate("b", rows, set(), {}, skip=set())
    assert (r["列"], r["处置"], r["结构分"]) == ("b:27:6", "需钉子", 2)
    assert r["例格"].startswith("劈字中 8|9 切割量 747px")


def test_cut_through_weak_is_hint():
    """cv 弱档（挪不到 1/3 格高，多是上下字笔画相触）只当提示，不算结构。"""
    rows = {"cut_through": [("b", 27, 6, "弱", "8|9 切割量 400px，挪 +20px 可降到 0px")]}
    (r,) = sc.aggregate("b", rows, set(), {}, skip=set())
    assert (r["类"], r["处置"], r["结构分"]) == ("提示", "劈字弱·笔画相触", 0)


def test_block_tall_book_hint():
    """史記写本 BLOCK 只当提示（书级口径）；同列另有劈字等结构旗照样需钉子；殿本缺省不变。"""
    rows = {"block_tall": [("b", 5, 1, 1.5, "3 字块高 180px 格高 120px"), ("b", 5, 2, 1.4, "4 …")],
            "cut_through": [("b", 5, 2, "中", "4|5 切割量 600px")]}
    out = {r["列"]: (r["类"], r["处置"]) for r in sc.aggregate("b", rows, set(), {}, skip=set(), hint_flags=("BLOCK",))}
    assert out == {"b:5:1": ("提示", "书级提示"), "b:5:2": ("结构", "需钉子")}
    out = {r["列"]: r["处置"] for r in sc.aggregate("b", rows, set(), {}, skip=set())}
    assert out == {"b:5:1": "需钉子", "b:5:2": "需钉子"}


def test_book_hint_flags_config(tmp_path):
    """认书读 workspace.yaml 的 id；写了 seg_check.hint_flags 以它为准。"""
    (tmp_path / "workspace.yaml").write_text("id: 988g3f0wsu\n", encoding="utf-8")
    assert sc.book_hint_flags(tmp_path) == ("BLOCK",)
    (tmp_path / "workspace.yaml").write_text("id: 988g3f0wsu\nseg_check:\n  hint_flags: []\n", encoding="utf-8")
    assert sc.book_hint_flags(tmp_path) == ()
    (tmp_path / "workspace.yaml").write_text("id: 96mid1ogzk\n", encoding="utf-8")
    assert sc.book_hint_flags(tmp_path) == () and sc.book_hint_flags(None) == ()


def test_job_text_puts_counts_last():
    rep = "\n".join(["# 切分核查 016", "", "- 处置计数（按列）：需钉子 1", "- 逐格 flags：CLIP 1", "",
                     "## 钉子未生效／格号不符／版式不符／需钉子／已钉复核／原因码看图", "", "- 016:66:9 需钉子：22CLIP",
                     "", "## ○对位（不归切分，交对位／参校）", "", "- 016:1:2：x", "- 016:3:4：y", "",
                     "结论：有 1 列要处理（钉子未生效、格号不符、版式不符或需钉子）", ""])
    out = sc.job_text(rep).splitlines()
    assert out[0] == "- 016:66:9 需钉子：22CLIP"
    assert "- ○对位（不归切分）2 列，明细见 report.md" in out
    assert out[-3:] == ["- 处置计数（按列）：需钉子 1", "- 逐格 flags：CLIP 1",
                        "结论：有 1 列要处理（钉子未生效、格号不符、版式不符或需钉子）"]


def test_block_tall_is_structural_even_with_lv():
    # 殿本 vol06 147:3:3：格线对、字块连上长竖线；旧版只有 Lv 判「公用清格」，现在字块过高要进「需钉子」
    rows = {"cell_flags": [("b", 147, 3, "Lv", "3 fr 0.000 foreign 0 cut 10")],
            "block_tall": [("b", 147, 3, 3.34, "3 字块高 427px 格高 128px boundary_ink")]}
    (r,) = sc.aggregate("b", rows, set(), {}, skip=set())
    assert (r["列"], r["处置"], r["结构分"]) == ("b:147:3", "需钉子", 3)
    assert r["例格"].startswith("字块过高×3.34")
