from guji_manager import ruling_anchor as RA
from guji_manager._cv import RulingStore
from guji_manager.swap import rulings_migrate as RM


def _store(tmp_path):
    store = RulingStore(tmp_path / "fb")
    store._batch = "llm-a"
    store.put("ry", "ry-l2-2", "甲乙", "丙丁", char="曰", conf="high", why="", model="m", cell="001:1:1:1")
    store.put("ry", "ry-l2-2", "子丑", "寅卯", char="日", conf="high", why="", model="m", cell="001:1:1:2")
    store.put("ry", "ry-l2-2", "天地", "玄黄", char="宇", conf="high", why="", model="m", cell="001:1:1:3")
    return store


def test_migrate_renumbered_and_same_cell(tmp_path, monkeypatch):
    monkeypatch.setattr(RA, "page_sha", lambda products, book, page: "NEW+P")
    store = _store(tmp_path)
    rows = [dict(old="1:1:1", new="1:1:5", oc="曰", nc="曰", kind="改号"),
            dict(old="1:1:2", new="1:1:2", oc="日", nc="日", kind="同格"),
            dict(old="1:1:3", new="1:1:3", oc="宇", nc="寓", kind="同格")]      # 字变了
    res = {x["old"]: x for x in RM.migrate(rows, "001", store, "llm-mig", tmp_path / "p", write=True)}
    assert res["1:1:1"]["结果"] == "迁" and res["1:1:2"]["结果"] == "迁"
    assert res["1:1:3"]["结果"] == "不迁" and "字变了" in res["1:1:3"]["原因"]
    s2 = RulingStore(tmp_path / "fb")
    got = {c: p for c, p in __import__("guji_manager.ruling_hits", fromlist=["x"])._rulings_by_cell_all(s2).items()}
    assert got["001:1:1:5"]["cells_sha"] == "NEW+P" and got["001:1:1:5"]["migrated_from"] == "001:1:1:1" and got["001:1:1:5"]["char"] == "曰"
    assert got["001:1:1:2"]["cells_sha"] == "NEW+P"
    assert "migrated_from" not in got["001:1:1:3"]


def test_dry_run_writes_nothing_and_skips_unchanged_page(tmp_path, monkeypatch):
    monkeypatch.setattr(RA, "page_sha", lambda products, book, page: "SAME")
    store = _store(tmp_path)
    store.put("ry", "ry-l2-2", "甲乙", "丙丁", char="曰", conf="high", why="", model="m", cell="001:1:1:1")
    rows = [dict(old="1:1:1", new="1:1:1", oc="曰", nc="曰", kind="同格")]
    assert RM.migrate(rows, "001", store, "llm-mig", tmp_path / "p", write=False)[0]["结果"] == "迁"
    assert not any("llm-mig" in e.batch for e in store.log.iter_all(raw=True))
