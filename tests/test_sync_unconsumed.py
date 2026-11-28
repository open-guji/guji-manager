"""db sync 报近期没被消费的人裁事件（11-20 痛点 K2／K7）。"""
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import guji_manager._cv as C
from guji_manager import cli_db


def test_unconsumed_report_groups_by_batch_and_consumer(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    evs = [NS(id="a", ts=now, batch="H-unrec-1113a"), NS(id="b", ts=now, batch="H-unrec-1113a"),
           NS(id="c", ts="2020-01-01T00:00:00+00:00", batch="old")]

    class Log:
        root = tmp_path
        def __init__(self, *_): pass
        def iter_all(self): return iter(evs)
        def consumed_ids(self, c): return frozenset({"a"}) if c == "glyphdb_admit" else frozenset()

    class Table:
        @staticmethod
        def load(_): return Table()
        def destinations(self, e): return [NS(consumer="glyphdb_admit"), NS(consumer="crop_exclude")]

    monkeypatch.setattr(C, "EventLog", Log, raising=False)
    monkeypatch.setattr(C, "RouteTable", Table, raising=False)
    monkeypatch.setattr(C, "CONSUMERS", {"glyphdb_admit": None, "crop_exclude": None, "gold_add": None}, raising=False)
    monkeypatch.setattr(C, "feedback_root", lambda: tmp_path, raising=False)
    rep = cli_db.unconsumed_report(tmp_path)
    assert rep == {("H-unrec-1113a", "glyphdb_admit"): 1, ("H-unrec-1113a", "crop_exclude"): 2}
    w = cli_db.unconsumed_warning(tmp_path)
    assert "crop_exclude" in w and "guji events route" in w and "old" not in w


def test_unconsumed_report_never_raises(tmp_path, monkeypatch):
    def boom(): raise RuntimeError("no data")
    monkeypatch.setattr(C, "feedback_root", boom, raising=False)
    assert cli_db.unconsumed_report(tmp_path) == {}
    assert cli_db.unconsumed_warning(tmp_path) is None


def test_unconsumed_report_skips_backfill_batches(tmp_path, monkeypatch):
    """放行格回库的机器 confirm 只进 glyphdb_admit，别的去处故意不走，不报漏（汉书 01，GM2 11-28）。"""
    now = datetime.now(timezone.utc).isoformat()
    bf = {"v": "confirm", "source": "auto", "backfill": True}
    evs = [NS(id="a", ts=now, batch="x-auto-backfill", kind="confirm", payload=bf),
           NS(id="b", ts=now, batch="H-1", kind="confirm", payload={"v": "confirm"})]

    class Log:
        root = tmp_path
        def __init__(self, *_): pass
        def iter_all(self): return iter(evs)
        def consumed_ids(self, c): return frozenset({"a"}) if c == "glyphdb_admit" else frozenset()

    class Table:
        @staticmethod
        def load(_): return Table()
        def destinations(self, e): return [NS(consumer="glyphdb_admit"), NS(consumer="product_invalidate")]

    monkeypatch.setattr(C, "EventLog", Log, raising=False)
    monkeypatch.setattr(C, "RouteTable", Table, raising=False)
    monkeypatch.setattr(C, "CONSUMERS", {"glyphdb_admit": None, "product_invalidate": None}, raising=False)
    monkeypatch.setattr(C, "feedback_root", lambda: tmp_path, raising=False)
    assert cli_db.unconsumed_report(tmp_path) == {("H-1", "glyphdb_admit"): 1, ("H-1", "product_invalidate"): 1}
