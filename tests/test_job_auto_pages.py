"""重跑缺省只跑受影响的页（11-20 痛点 D1）。"""
from types import SimpleNamespace as NS

import pytest

from guji_manager.jobs import auto_pages as AP


def test_compress():
    assert AP.compress([10, 1, 2, 3, 7, 9]) == "1-3,7,9-10"
    assert AP.compress([5]) == "5"


def test_why_not_default():
    ok = {"kind": "rerun", "book": "vol20", "cv": "v0.7.80", "steps": {"from": "seed_admit"}}
    assert AP.why_not_default(ok, "0.7.80") is None
    assert "cv" in AP.why_not_default(ok, "0.7.79")
    assert AP.why_not_default({**ok, "pages": "all"})
    assert AP.why_not_default({**ok, "steps": {"from": "glyph_match"}})
    assert AP.why_not_default({**ok, "book_overrides": {"corpus": 3}})
    assert AP.why_not_default({**ok, "kind": "ab"})


def _ev(ts, key, unit="cell", payload=None):
    return NS(ts=ts, target=NS(unit=unit, key=key), payload=payload or {})


def test_changed_pages():
    evs = [_ev("2026-11-20T10:00:00Z", "vol20:84:3:10"), _ev("2026-11-19T00:00:00Z", "vol20:5:1:1"),
           _ev("2026-11-20T10:00:00Z", "vol21:9:1:1"), _ev("2026-11-20T10:00:00Z", "vol20:7", unit="page")]
    rs = [_ev("2026-11-20T11:00:00Z", "x", payload={"cell": "vol20:12:2:3a"})]
    assert AP.changed_pages("vol20", "2026-11-20T00:00:00Z", evs, rs) == {84, 12}


def test_resolve_fills_pages(monkeypatch):
    monkeypatch.setattr(AP, "base_manifest", lambda b, base: {"label": "rev-9", "created": "2026-11-20T00:00:00Z",
                                                               "versions": {"cv": "0.7.80"}})
    monkeypatch.setattr(AP, "changed_pages", lambda b, since: {3, 4, 9})
    raw = {"book": "vol20", "cv": "v0.7.80", "steps": {"from": "seed_admit"}}
    AP.resolve(raw)
    assert raw["pages"] == "3-4,9"
    raw = {"book": "vol20", "cv": "v0.7.81", "steps": {"from": "seed_admit"}}
    AP.resolve(raw)                       # 换代码：整册
    assert "pages" not in raw
    raw = {"book": "vol20", "cv": "v0.7.81", "steps": {"from": "glyph_match"}, "pages": "auto"}
    AP.resolve(raw)                       # 显式 auto 照算
    assert raw["pages"] == "3-4,9"


def test_resolve_no_changes_refuses(monkeypatch):
    monkeypatch.setattr(AP, "base_manifest", lambda b, base: {"label": "rev-9", "created": "x", "versions": {"cv": "0.7.80"}})
    monkeypatch.setattr(AP, "changed_pages", lambda b, since: set())
    with pytest.raises(SystemExit):
        AP.resolve({"book": "vol20", "cv": "v0.7.80", "steps": {"from": "seed_admit"}})


def test_resolve_falls_back_when_no_pack(monkeypatch):
    def boom(b, base):
        raise RuntimeError("no r2")
    monkeypatch.setattr(AP, "base_manifest", boom)
    raw = {"book": "vol20", "cv": "v0.7.80", "steps": {"from": "seed_admit"}}
    AP.resolve(raw)
    assert "pages" not in raw
