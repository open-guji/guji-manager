# -*- coding: utf-8 -*-
"""write_events：裁定事件（confirm、unit=cell）顶层册必填、来源三字段兜底（清理计划 2.3／2.4，2026-11-27）。"""
import pytest

from guji_manager.review.event_write import cell_book, fill_provenance, write_events
from guji_manager._cv import BadRequest


def test_cell_book_numeric_prefix():
    ids = cell_book("01:11:6:10a", {})
    assert ids == {"book": "01", "page": 11, "col": 6, "slot": 10}


def test_cell_book_keeps_parsed():
    assert cell_book("vol02:3:4:5", {"book": "vol02", "page": 3}) == {"book": "vol02", "page": 3}


def test_cell_book_not_a_cell():
    assert cell_book("cols:vol02:171", {}) == {}


def test_fallback_console():
    p = fill_provenance({"v": "confirm"}, reviewer="a@x.com", kind="confirm", unit="cell")
    assert (p["level"], p["by"], p["channel"]) == ("human", "a@x.com", "console")


def test_caller_channel_wins():
    p = fill_provenance({"v": "confirm", "channel": "web_vote", "by": "abc"}, reviewer="a@x.com", kind="confirm", unit="cell")
    assert (p["level"], p["by"], p["channel"]) == ("human", "abc", "web_vote")


def test_ai_level_kept():
    p = fill_provenance({"level": "ai", "by": "claude"}, reviewer=None, kind="confirm", unit="cell")
    assert p["level"] == "ai" and p["channel"] == "console"


def test_missing_by_rejected():
    with pytest.raises(BadRequest):
        fill_provenance({"v": "confirm"}, reviewer=None, kind="confirm", unit="cell")


def test_bad_enum_rejected():
    with pytest.raises(BadRequest):
        fill_provenance({"channel": "carrier-pigeon"}, reviewer="x", kind="confirm", unit="cell")


def test_non_ruling_untouched():
    p = {"x": 1}
    assert fill_provenance(p, reviewer=None, kind="cutline", unit="page") is p
    assert fill_provenance(p, reviewer=None, kind="confirm", unit="page") is p


def test_write_events_end_to_end(tmp_path):
    from guji_manager._cv import BatchStore, EventLog, GoldStore, ProductStore
    log = EventLog(tmp_path / "fb")
    res = write_events(log, BatchStore(tmp_path / "b"), GoldStore(tmp_path / "v"), ProductStore(tmp_path / "p"),
                       batch="H-t", step="seed_admit", unit="cell", kind="confirm", consume=False,
                       events=[{"id": "01:11:6:10", "v": "confirm", "char": "x"}], reviewer="a@x.com")
    assert res["appended"] == 1
    (e,) = log.read("H-t")
    assert e.target.book == "01" and (e.target.page, e.target.col, e.target.slot) == (11, 6, 10)
    assert (e.payload["level"], e.payload["by"], e.payload["channel"]) == ("human", "a@x.com", "console")
