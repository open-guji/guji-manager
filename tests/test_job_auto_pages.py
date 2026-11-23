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


def test_base_rev():
    assert AP.base_rev({"versions": {"db_rev": 90, "db_revs": {"80": 5, "85": 2}}}) == 80
    assert AP.base_rev({"versions": {"db_rev": 90}}) == 90
    assert AP.base_rev({"versions": {"db_rev": 90, "db_revs": {"80": 5, "未记": 2}}}) is None   # 有页没记 rev：不信
    assert AP.base_rev({"versions": {}}) is None
    assert AP.base_rev({}) is None


def test_changed_pages_by_rev():
    rows = [({"unit": "cell", "key": "vol20:84:3:10"}, {}),
            ({"unit": "cell", "key": "vol21:9:1:1"}, {}),
            ({"unit": "page", "key": "vol20:7"}, {}),
            ({}, {"cell": "vol20:12:2:3a"})]
    assert AP.changed_pages("vol20", 5, rows) == {84, 12}


def _man(**v):
    return {"label": "rev-9", "created": "2026-11-20T00:00:00Z", "versions": {"cv": "0.7.80", **v}}


def test_resolve_default_on(monkeypatch):
    monkeypatch.setattr(AP, "base_manifest", lambda b, base: _man(db_rev=100))
    seen = {}
    monkeypatch.setattr(AP, "changed_pages", lambda b, rev, rows=None, since_ts=None: seen.setdefault("rev", rev) and {3, 4, 9})
    raw = {"book": "vol20", "cv": "v0.7.80", "steps": {"from": "seed_admit"}}
    AP.resolve(raw)                       # 缺省按页（11-23 起按入库 rev，不再漏页）
    assert raw["pages"] == "3-4,9" and seen["rev"] == 100
    raw = {"book": "vol20", "cv": "v0.7.81", "steps": {"from": "seed_admit"}}
    AP.resolve(raw)                       # 换代码：整册
    assert "pages" not in raw
    raw = {"book": "vol20", "cv": "v0.7.81", "steps": {"from": "glyph_match"}, "pages": "auto"}
    AP.resolve(raw)                       # 显式 auto 照算
    assert raw["pages"] == "3-4,9"
    raw = {"book": "vol20", "cv": "v0.7.81", "steps": {"from": "glyph_match"}, "pages": "auto:50"}
    AP.resolve(raw)
    assert seen["rev"] == 100             # setdefault 只记首次；下面单独验 auto:rev
    monkeypatch.setattr(AP, "changed_pages", lambda b, rev, rows=None, since_ts=None: {rev})
    raw = {"book": "vol20", "cv": "v0.7.81", "steps": {"from": "glyph_match"}, "pages": "auto:50"}
    AP.resolve(raw)
    assert raw["pages"] == "50"


def test_resolve_old_pack_no_rev(monkeypatch):
    monkeypatch.setattr(AP, "base_manifest", lambda b, base: _man())
    seen = {}
    monkeypatch.setattr(AP, "changed_pages", lambda b, rev, rows=None, since_ts=None: seen.update(rev=rev, ts=since_ts) or {7})
    raw = {"book": "vol20", "cv": "v0.7.80", "steps": {"from": "seed_admit"}}
    AP.resolve(raw)
    assert raw["pages"] == "7" and seen == {"rev": None, "ts": "2026-11-20T00:00:00Z"}   # 老包：按入库时间
    m = _man(); m.pop("created")
    monkeypatch.setattr(AP, "base_manifest", lambda b, base: m)
    raw = {"book": "vol20", "cv": "v0.7.80", "steps": {"from": "seed_admit"}}
    AP.resolve(raw)
    assert "pages" not in raw             # 连生成时间都没有：整册
    with pytest.raises(SystemExit):
        AP.resolve({"book": "vol20", "cv": "v0.7.80", "steps": {"from": "seed_admit"}, "pages": "auto"})


def test_resolve_no_changes_refuses(monkeypatch):
    monkeypatch.setattr(AP, "base_manifest", lambda b, base: _man(db_rev=100))
    monkeypatch.setattr(AP, "changed_pages", lambda b, rev, rows=None, since_ts=None: set())
    with pytest.raises(SystemExit):
        AP.resolve({"book": "vol20", "cv": "v0.7.80", "steps": {"from": "seed_admit"}, "pages": "auto"})


def test_resolve_falls_back_when_no_pack(monkeypatch):
    def boom(b, base):
        raise RuntimeError("no r2")
    monkeypatch.setattr(AP, "base_manifest", boom)
    raw = {"book": "vol20", "cv": "v0.7.80", "steps": {"from": "seed_admit"}}
    AP.resolve(raw)
    assert "pages" not in raw
