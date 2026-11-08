from guji_manager.review.sent_export import sent_export, sent_hash
from tests.opinions import booktext_fixture as F


def test_sent_export_basic():
    char, p, e = F.char(), F.punct(), F.entity()
    r = sent_export(char, p, e, pending_cells={"3:2:5"}, assumed_cells={"3:2:5"})
    assert len(r) == 1
    s = r[0]
    assert s["n"] == len(s["t"]) == len(s["cells"])
    assert s["h"] == sent_hash(s["t"], s["cells"])
    assert any(m["kind"] == "entity" and m["assumed"] for m in s["marks"])
    assert any(m["kind"] == "punct" and m["ch"] == "。" for m in s["marks"])
    assert sent_export(char, p, e, pending_cells={"zz"}) == []


def _mk(chars, puncts):
    cells = [{"a": f"1:1:{i+1}", "c": c} for i, c in enumerate(chars)]
    char = {"pages": [{"page": 1, "columns": [{"col": 1, "cells": cells}]}]}
    pj = {"punctuations": [({"mark": m, "pos": "before", "anchor": "1:1:1"} if i == 0 else
                            {"mark": m, "pos": "after", "anchor": f"1:1:{i}"}) for i, m in puncts]}
    return char, pj


def test_boundary_openers():
    # 「甲乙。」「丙丁。」 -> 两句，第二句的「在其句首 pos 0
    char, pj = _mk("甲乙丙丁", [(0, "「"), (2, "。"), (2, "」"), (2, "「"), (4, "。"), (4, "」")])
    r = sent_export(char, pj, None)
    assert len(r) == 2
    assert [(m["ch"], m["pos"]) for m in r[0]["marks"]] == [("「", 0), ("。", 2), ("」", 2)]
    assert [(m["ch"], m["pos"]) for m in r[1]["marks"]] == [("「", 0), ("。", 2), ("」", 2)]


def test_boundary_booktitle():
    # 甲乙。《丙》曰 -> 《 属第二句句首
    char, pj = _mk("甲乙丙曰", [(2, "。"), (2, "《"), (3, "》")])
    r = sent_export(char, pj, None)
    assert [m["ch"] for m in r[0]["marks"]] == ["。"]
    assert [(m["ch"], m["pos"]) for m in r[1]["marks"]][:2] == [("《", 0), ("》", 1)]
