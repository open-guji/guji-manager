"""pending-stats 非正文页（职名、表格）单列，不计入待审数与人审率。"""
from guji_manager.pending_stats import nonbody_of_yaml, summarize


def _rows():
    mk = lambda cell, kind: {"vol": "001", "cell": cell, "big": "Z", "sub": "Z1", "key": "k", "owner": "", "fix": "", "conc": "零散",
                             "cause": "", "pending_reason": "unknown", "slim": False, "kind": kind}   # noqa: E731
    return [mk("10:1:1", "body"), mk("39:1:1", "roster"), mk("40:2:1", "roster")]


def test_nonbody_of_yaml_new_and_old():
    raw = """
page_kinds:
  roster: ["39-41", 121]
  table: [1]
  cover: [2]
params:
  border_detect_gate: {table_pages: "5,7"}
"""
    nb = nonbody_of_yaml(raw)
    assert nb == {"39": "roster", "40": "roster", "41": "roster", "121": "roster", "1": "table", "2": "cover", "5": "table", "7": "table"}


def test_summarize_excludes_nonbody():
    s = summarize(_rows(), {"001": {}}, {"001": 100})
    assert s["n"] == 1 and s["n_nonbody"] == 2
    assert s["vols"]["001"]["n"] == 1 and s["vols"]["001"]["rate"] == 0.01 and s["vols"]["001"]["n_nonbody"] == 2


def test_analyse_marks_nonbody_by_vol_digits(monkeypatch):
    import guji_manager.pending_stats as ps
    monkeypatch.setattr(ps, "_group_of", lambda ch: None)
    lists = {"01.": {"cells": [{"cell": "39:1:1", "why": []}, {"cell": "10:1:1", "why": []}]}}
    rows = ps.analyse(lists, {}, nonbody={"001": {"39": "roster"}})
    assert [r["kind"] for r in rows] == ["roster", "body"]
