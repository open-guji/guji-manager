"""ops/rename_volume：cv 内部册名改名（11-27）——产物、缓存、数据目录按册文件，备份与还原。"""
import hashlib
import json

from guji_manager.ops.rename_volume import Rewriter, apply, build_plan, rollback


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _setup(tmp_path):
    prod, cache, data = tmp_path / "products", tmp_path / "cache", tmp_path / "data"
    cells = prod / "01" / "cell_shrink" / "p0010.json"
    cells.parent.mkdir(parents=True)
    cells.write_text(json.dumps({"book": "01", "cells": [{"id": "01:10:1:2a", "match": "v2:01:9:1:1"}],
                                 "key": "cols:01:10"}, sort_keys=True), encoding="utf-8")
    old_sha = _sha(cells)
    (prod / "01" / "cell_shrink" / "manifest.json").write_text(
        json.dumps({"p0010": {"sha256": old_sha}}), encoding="utf-8")
    st = cache / "01" / "char_patch" / "_stamps.json"
    st.parent.mkdir(parents=True)
    st.write_text(json.dumps({"p0010": old_sha}), encoding="utf-8")
    (data / "books").mkdir(parents=True)
    (data / "books" / "01.yaml").write_text('id: "01"\nraw_dir: data_full/01\nskip: ["01:10:1:2"]\n', encoding="utf-8")
    (data / "feedback" / "uid").mkdir(parents=True)
    (data / "feedback" / "uid" / "01.jsonl").write_text(
        json.dumps({"book": "01", "page": 10, "cells_sha": f"x+{old_sha}", "map": {"01:10:1:2a": 7}}) + "\n", encoding="utf-8")
    (data / "feedback" / "anchors").mkdir(parents=True)
    (data / "feedback" / "anchors" / "01.jsonl").write_text('{"event": "e1", "key": "01:10:1:2"}\n', encoding="utf-8")
    (data / "feedback" / "events").mkdir(parents=True)
    (data / "feedback" / "events" / "a.jsonl").write_text('{"target": {"book": "01", "key": "01:10:1:2"}}\n', encoding="utf-8")
    (data / "feedback" / "lists" / "pending" / "mai").mkdir(parents=True)
    (data / "feedback" / "lists" / "pending" / "mai" / "01.items.jsonl").write_text('{"cell": "01:10:1:2"}\n', encoding="utf-8")
    return prod, cache, data, old_sha


def test_rewriter_keeps_instance_ids_and_times():
    rw = Rewriter({"01": "1", "vol01": "01"})
    t, n = rw.json_text('{"a": "01:2:3:4", "b": "v2:01:2:3:4", "c": "cols:vol01:5", "book": "vol01", "t": "01:30"}')
    assert json.loads(t) == {"a": "1:2:3:4", "b": "v2:01:2:3:4", "c": "cols:01:5", "book": "01", "t": "01:30"}
    assert n == 3
    assert json.loads(rw.json_text('{"k": "vol01/50:7:21"}')[0]) == {"k": "01/50:7:21"}


def test_apply_and_rollback(tmp_path):
    prod, cache, data, old_sha = _setup(tmp_path)
    plan = build_plan({"01": "1"}, data, prod, cache)
    assert not plan.conflicts
    assert any("pending/mai/01.items.jsonl" in x for x in plan.leftovers)     # 只报不改
    snap = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    bk = tmp_path / "bk"
    apply(plan, bk)
    cells = prod / "1" / "cell_shrink" / "p0010.json"
    d = json.loads(cells.read_text(encoding="utf-8"))
    assert d["book"] == "1" and d["cells"][0]["id"] == "1:10:1:2a" and d["key"] == "cols:1:10"
    assert d["cells"][0]["match"] == "v2:01:9:1:1"                            # 实例 id 不改
    new_sha = _sha(cells)
    assert json.loads((prod / "1" / "cell_shrink" / "manifest.json").read_text())["p0010"]["sha256"] == new_sha
    assert json.loads((cache / "1" / "char_patch" / "_stamps.json").read_text())["p0010"] == new_sha
    y = (data / "books" / "1.yaml").read_text(encoding="utf-8")
    assert 'id: "1"' in y and 'aliases: ["01"]' in y and '"1:10:1:2"' in y and "raw_dir: data_full/01" in y
    u = json.loads((data / "feedback" / "uid" / "1.jsonl").read_text(encoding="utf-8"))
    assert u["book"] == "1" and u["map"] == {"1:10:1:2a": 7} and u["cells_sha"] == f"x+{new_sha}"
    assert (data / "feedback" / "anchors" / "1.jsonl").exists()
    assert '"01:10:1:2"' in (data / "feedback" / "events" / "a.jsonl").read_text(encoding="utf-8")   # 事件不改写
    rollback(bk)
    after = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file() and bk not in p.parents}
    assert after == snap


def test_conflict_when_new_exists(tmp_path):
    prod, cache, data, _ = _setup(tmp_path)
    (prod / "1").mkdir()
    assert build_plan({"01": "1"}, data, prod, cache).conflicts
