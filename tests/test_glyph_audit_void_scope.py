"""体检撤库／改标作废人裁事件的范围：只作废「把这格定成旧字」的人裁（殿本 vol01，2026-11-18）。"""
from types import SimpleNamespace as NS

from guji_manager.feedback import glyph_audit as GA


def _res():
    return NS(errors=[])


def test_void_only_when_latest_human_verdict_is_the_old_char(monkeypatch):
    voided = []
    monkeypatch.setattr(GA, "_void_human_event", lambda iid, why: voided.append(iid) or iid[3:])
    e = NS(id="evt_x_000001")
    # 这格现行人裁定的是另一个字（库例挂旧格号／文本人裁本来就对）：不作废
    rec = {"old_char": "日"}
    GA._void_or_report(_res(), rec, e, "v2:vol01:8:9:12", "glyph_audit evict", {"vol01:8:9:12": "曰"})
    assert voided == [] and rec["kept_human_event"] == "曰" and "voided_human_event" not in rec
    # 现行人裁定的就是被撤的旧字：作废
    rec = {"old_char": "日"}
    GA._void_or_report(_res(), rec, e, "v2:vol01:8:9:13", "glyph_audit evict", {"vol01:8:9:13": "日"})
    assert voided == ["v2:vol01:8:9:13"] and rec["voided_human_event"] == "vol01:8:9:13"
    # 查不到这格的人裁事件（很老的数据）：照旧作废
    rec = {"old_char": "日"}
    GA._void_or_report(_res(), rec, e, "v2:vol01:8:9:14", "glyph_audit relabel", {})
    assert voided[-1] == "v2:vol01:8:9:14"


def test_latest_human_shapes_takes_last_confirm(monkeypatch):
    def ev(key, ts, shape, kind="confirm", seq=1):
        return NS(kind=kind, ts=ts, batch="b", seq=seq, target=NS(key=key), payload={"shape": shape})
    evs = [ev("v:1:1:1", "2026-11-01T00:00:00Z", "日"), ev("v:1:1:1", "2026-11-05T00:00:00Z", "曰", seq=2),
           ev("v:1:1:2", "2026-11-05T00:00:00Z", "口"), ev("v:1:1:1", "2026-11-09T00:00:00Z", "x", kind="glyph_audit", seq=3)]
    import guji_manager._cv as CV
    monkeypatch.setattr(CV, "EventLog", lambda root=None: NS(iter_all_cached=lambda: iter(evs)), raising=False)
    monkeypatch.setattr(CV, "feedback_root", lambda: None, raising=False)
    assert GA._latest_human_shapes(["v2:v:1:1:1", "v:1:1:9"]) == {"v:1:1:1": "曰"}
