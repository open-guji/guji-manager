"""事件级别口径（2026-11-26，GM4 批量规则）：与 cv `events.event_level` 同表。"""
from types import SimpleNamespace

from guji_manager.feedback.levels import HUMAN_MODEL_BATCHES, counts_as_human, counts_as_pin, event_level


def _ev(batch, actor="model", kind="confirm", **p):
    return SimpleNamespace(kind=kind, actor=actor, batch=batch, payload={"v": "confirm", "shape": "公", **p})


def test_levels():
    assert len(HUMAN_MODEL_BATCHES) == 9
    assert event_level(_ev("r52-ctx2-2rounds")) == "ai"
    assert event_level(_ev("r77-重绑")) == event_level(_ev("SJ-歲暫歸一-1125~u")) == "human"
    assert event_level(_ev("r52-ctx2-2rounds", level="human")) == "human"
    assert event_level(_ev("r77-重绑", level="ai")) == "ai"
    assert event_level(_ev("x", actor="user")) == "human"
    assert event_level(_ev("x", source="vision")) is None and event_level(_ev("x", source="auto")) is None
    assert event_level(_ev("x", kind="vision_check", actor="user")) is None
    a = _ev("r59-ctx2")
    assert counts_as_pin(a) and not counts_as_human(a)


def test_dict_events():
    d = {"kind": "confirm", "actor": "model", "batch": "r79-v01~u", "payload": {"v": "confirm"}}
    assert event_level(d) == "human"
    assert event_level({**d, "batch": "qtw-backfill-audit-d2"}) == "ai"


def test_same_table_as_cv():
    """cv 有同一张表时必须一致（cv dev 2026-11-26 起有；patch 线 cv 没有就跳过）。"""
    import pytest
    ev = pytest.importorskip("open_guji_cv.feedback.events")
    if not hasattr(ev, "HUMAN_MODEL_BATCHES"):
        pytest.skip("cv 版本还没有 event_level")
    assert ev.HUMAN_MODEL_BATCHES == HUMAN_MODEL_BATCHES
    assert ev.MODEL_JUDGMENT_SOURCES == __import__("guji_manager.feedback.levels", fromlist=["x"]).MODEL_JUDGMENT_SOURCES
