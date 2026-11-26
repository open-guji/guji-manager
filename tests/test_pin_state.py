"""钉状态流写入口（GM4 11-26）。"""
import json

import pytest

from guji_manager import pin_state as P
from guji_manager.datastore import scope


def test_build_and_append(tmp_path):
    rec = P.build("vol01", "removed", "pin-vol01-char-3140", events=["evt_a"], reason="human_correction",
                  level="human", by="GM4", u=3140, at="2026-11-26T23:00:00Z")
    assert rec["payload"]["events"] == ["evt_a"] and rec["kind"] == "pin_state" and rec["target"] == {"book": "vol01"}
    p = P.append(tmp_path, "vol01", rec)
    P.append(tmp_path, "vol01", rec)          # 同 id 不重复写
    assert p == tmp_path / "feedback/pins/vol01.state.jsonl"
    assert len(p.read_text(encoding="utf-8").splitlines()) == 1
    assert json.loads(p.read_text(encoding="utf-8"))["payload"]["pin_id"] == "pin-vol01-char-3140"


@pytest.mark.parametrize("kw", [
    dict(events=[], reason="human_correction", level="human"),          # removed 要 events
    dict(events=["e"], reason="superseded", level="human"),             # superseded 要 by_event
    dict(events=["e"], reason="human_correction", level="machine"),     # level 只用 human／ai
    dict(events=["e"], reason="乱写", level="human"),
])
def test_build_rejects(kw):
    with pytest.raises(ValueError):
        P.build("vol01", "removed", "p", by="x", **kw)


def test_reactivate_needs_no_events():
    rec = P.build("vol01", "reactivated", "p", events=[], reason="human_correction", level="human", by="x")
    assert rec["payload"]["v"] == "reactivated"


def test_scope_routes_state_to_events():
    assert scope.classify("feedback/pins/vol01.state.jsonl") == "events"
    assert scope.classify("feedback/pins/vol01.jsonl") is None      # 钉表由 guji pin build 编出，暂不入库
    rec = P.build("vol01", "removed", "p", events=["e"], reason="u_void", level="ai", by="x")
    key, cols = scope._events(rec, "feedback/pins/vol01.state.jsonl", 1)
    assert cols["stream"] == "pin_state" and cols["book"] == "vol01" and key[1] == rec["id"]
