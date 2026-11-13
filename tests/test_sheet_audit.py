"""待审单体检：不该进判字单的格（11-13 ZM）。"""
from guji_manager.review import sheet_audit as SA


def _codes(doc, norm=None):
    return sorted((f.code, f.cell) for f in SA.audit_sheet(doc, norm))


def test_machine_blank_is_not_overturn():
    doc = {"cells": [{"cell": "1:1:1", "recheck": True, "pending_reason": "machine_changed",
                      "note": "机器改判「撰」→「□」，推翻人裁，请核"}]}
    assert _codes(doc) == [("overturn_empty", "1:1:1")]


def test_untrusted_prior_is_not_overturned():
    doc = {"cells": [{"cell": "1:9:9", "recheck": True, "pending_reason": "machine_changed",
                      "note": "机器改判「入」→「人」，推翻人裁，请核", "stale": {"c": "入", "state": "unanchored"}},
                     {"cell": "1:9:10", "recheck": True, "pending_reason": "machine_changed",
                      "note": "机器改判「入」→「人」，推翻人裁，请核", "stale": {"c": "入", "state": "valid"}}]}
    assert _codes(doc) == [("overturn_untrusted", "1:9:9")]


def test_same_after_norm():
    doc = {"cells": [{"cell": "60:9:14", "recheck": True, "pending_reason": "machine_changed",
                      "note": "机器改判「賛」→「贊」，推翻人裁，请核"}]}
    assert _codes(doc) == []
    assert _codes(doc, {"賛": "贊"}) == [("overturn_same", "60:9:14")]


def test_anchor_only_and_dups_and_warn():
    doc = {"cells": [{"cell": "5:1:1", "pending_reason": "anchor_miss", "src": "closeout_anchor"},
                     {"cell": "6:1:1", "pending_reason": "group_abstain"},
                     {"cell": "6:1:1", "pending_reason": "group_abstain"},
                     {"cell": "7:1:1"}],
           "anchor_cells": [{"cell": "8:1:1", "pending_reason": "add_del", "src": "closeout_anchor"}]}
    fs = SA.audit_sheet(doc)
    assert sorted((f.code, f.cell) for f in fs) == [("anchor_only_in_cells", "5:1:1"), ("dup_cell", "6:1:1"), ("no_reason", "7:1:1")]
    assert [f.block for f in fs if f.code == "no_reason"] == [False]


def test_clean_sheet():
    doc = {"cells": [{"cell": "1:1:1", "pending_reason": "hard_pair"},
                     {"cell": "1:1:2", "recheck": True, "note": "撤库重审", "pending_reason": "evicted"}]}
    assert _codes(doc) == []


def test_resolved_anchor_only_cell_not_flagged():
    """已人审（review: human）的锚点类条目留在单上显示结果，不报 anchor_only_in_cells。"""
    doc = {"cells": [{"cell": "103:5:13", "pending_reason": "anchor_miss", "src": "closeout_anchor", "review": "human"}]}
    assert SA.audit_sheet(doc) == []
