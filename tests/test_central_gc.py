"""中心库清理（产物包保留规则）：不连库，假数据。"""

from datetime import datetime, timezone

from guji_manager import central_gc as G


def _p(book, label, created, commit=None):
    p = G.Pack("w", book, label, bytes=10, keys=[f"products/w/{book}/{label}/manifest.json"])
    p.created, p.cv_commit = created, commit
    return p


def test_plan_keeps_by_rules():
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    old = "2026-10-20T00:00:00Z"
    ps = [_p("vol01", "a", old), _p("vol01", "b", old), _p("vol01", "c", old), _p("vol01", "d", old, "abc"),
          _p("vol01", "freeze-1.0", old), _p("vol01", "e", old), _p("vol01", "new", "2026-11-19T00:00:00Z"),
          _p("vol01", "job", old)]
    packs = {(p.ws, p.book, p.label): p for p in ps}
    mains = {("w", "vol01"): ["a", "b", "c"]}
    refs = {"freeze": {"products/w/vol01/e"}, "online": {("w", "001"): "abc"}, "jobs": {("vol01", "job")}}
    drop = G.plan(packs, mains, refs, keep_days=7, keep_mains=1, now=now)
    assert [p.label for p in drop] == ["a"]
    assert packs[("w", "vol01", "c")].keep == ["现行 main"]
    assert packs[("w", "vol01", "b")].keep == ["上一份 main"]
    assert "线上单所用版本" in packs[("w", "vol01", "d")].keep
    assert "冻结" in packs[("w", "vol01", "freeze-1.0")].keep and "冻结" in packs[("w", "vol01", "e")].keep
    assert packs[("w", "vol01", "job")].keep == ["排队任务要用"]


def test_unknown_created_is_kept():
    p = _p("vol02", "x", None)
    drop = G.plan({("w", "vol02", "x"): p}, {}, {"freeze": set(), "online": {}, "jobs": set()})
    assert drop == [] and p.keep == ["不知存于何时"]
