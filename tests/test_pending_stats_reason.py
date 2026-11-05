"""pending-stats 按待审原因 pending_reason 统计：缺字段记 unknown，报告有「零」节，cells.tsv 带该列。"""
import json

from guji_manager import pending_stats


def test_reason_counts_and_report(tmp_path):
    d = tmp_path / "lists"
    d.mkdir()
    doc = {"rev": "r1", "cells": [
        {"cell": "1:1:1", "pending_reason": "hard_pair", "why": []},
        {"cell": "1:1:2", "pending_reason": "hard_pair", "why": []},
        {"cell": "1:1:3", "why": []},
    ]}
    (d / "020.pending.json").write_text(json.dumps(doc), encoding="utf-8")
    out = tmp_path / "out"
    pending_stats._group_of = lambda ch: None
    assert pending_stats.main(["--from-dir", str(d), "--out", str(out)]) == 0
    s = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert s["by_reason"] == {"hard_pair": 2, "unknown": 1}
    rep = (out / "report.md").read_text(encoding="utf-8")
    assert "零、按待审原因" in rep and "`hard_pair`" in rep and "`unknown`" in rep
    head = (out / "cells.tsv").read_text(encoding="utf-8").splitlines()[0].split("\t")
    assert head[2] == "pending_reason"


def test_src_selfcheck_counted(tmp_path):
    d = tmp_path / "lists"
    d.mkdir()
    doc = {"rev": "r1", "cells": [
        {"cell": "1:1:1", "pending_reason": "seg_defect", "src": "seg_selfcheck", "why": []},
        {"cell": "1:1:2", "pending_reason": "seg_defect", "why": []},
        {"cell": "1:1:3", "pending_reason": "ref_lacuna", "pending_reason_detail": "glyph_pending:U+F1001", "why": []},
    ]}
    (d / "020.pending.json").write_text(json.dumps(doc), encoding="utf-8")
    out = tmp_path / "out"
    pending_stats._group_of = lambda ch: None
    assert pending_stats.main(["--from-dir", str(d), "--out", str(out)]) == 0
    s = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert s["by_src"] == {"seg_selfcheck": 1, "glyph_pending": 1}
    assert "同字对照自检（seg_selfcheck） 1" in (out / "report.md").read_text(encoding="utf-8") and "待收字（glyph_pending） 1" in (out / "report.md").read_text(encoding="utf-8")
