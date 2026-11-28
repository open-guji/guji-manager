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
    (prod / "01" / "cell_shrink" / "_manifest.jsonl").write_text(
        json.dumps({"key": "p0010", "sha256": old_sha, "upstream": {"row_segment": old_sha}}) + "\n", encoding="utf-8")
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
    m = json.loads((prod / "1" / "cell_shrink" / "_manifest.jsonl").read_text())
    assert m["sha256"] == new_sha and m["upstream"] == {"row_segment": old_sha}   # upstream 不动
    mk = json.loads((prod / "1" / "_renamed.json").read_text())
    assert mk["from"] == "01" and mk["shamap"] == {old_sha: new_sha}
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


def _extra(data, old_sha):
    (data / "feedback" / "rulings").mkdir(parents=True)
    (data / "feedback" / "rulings" / "llm-1.jsonl").write_text(
        json.dumps({"payload": {"cell": "01:10:1:2", "cells_sha": f"{old_sha}+x"}}) + "\n", encoding="utf-8")
    (data / "feedback" / "anchors" / "01.jsonl").write_text(
        json.dumps({"key": "01:10:1:2", "anchor": {"cells_sha": f"{old_sha}+x"}}) + "\n", encoding="utf-8")
    (data / "feedback" / "anchor_patches" / "01" / "ab").mkdir(parents=True)
    (data / "feedback" / "anchor_patches" / "01" / "ab" / "abc.png").write_bytes(b"png")
    (data / "corpus").mkdir()
    (data / "corpus" / "alt.jsonl").write_text('{"vol": "01", "cell": "01:10:1:2"}\n', encoding="utf-8")


def test_rulings_anchor_patches_and_shas(tmp_path):
    """11-28 殿本演练：rulings、groups 等原先只报不改；anchors 的 cells_sha、anchor_patches 目录也要跟着换。"""
    prod, cache, data, old_sha = _setup(tmp_path)
    _extra(data, old_sha)
    plan = build_plan({"01": "1"}, data, prod, cache)
    assert any(x.startswith("corpus/alt.jsonl") for x in plan.leftovers)            # 钉 sha 的语料只报
    assert any("pending/mai/01.items.jsonl" in x for x in plan.leftovers)
    assert not any("rulings" in x for x in plan.leftovers)
    snap = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    bk = tmp_path / "bk"
    apply(plan, bk)
    new_sha = _sha(prod / "1" / "cell_shrink" / "p0010.json")
    r = json.loads((data / "feedback" / "rulings" / "llm-1.jsonl").read_text(encoding="utf-8"))
    assert r["payload"] == {"cell": "1:10:1:2", "cells_sha": f"{new_sha}+x"}
    a = json.loads((data / "feedback" / "anchors" / "1.jsonl").read_text(encoding="utf-8"))
    assert a["key"] == "1:10:1:2" and a["anchor"]["cells_sha"] == f"{new_sha}+x"
    assert (data / "feedback" / "anchor_patches" / "1" / "ab" / "abc.png").exists()
    assert '"01:10:1:2"' in (data / "corpus" / "alt.jsonl").read_text(encoding="utf-8")
    rollback(bk)
    after = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file() and bk not in p.parents}
    assert after == snap


def test_repair_after_old_tool(tmp_path):
    """旧版工具改过名的书：--repair 按备份补改 rulings、anchors 的 sha、anchor_patches 目录。"""
    from guji_manager.ops.rename_volume import main
    prod, cache, data, old_sha = _setup(tmp_path)
    _extra(data, old_sha)
    bk = tmp_path / "bk"
    # 模拟旧版：只做产物与按册文件，然后把新加的几类恢复成旧样子
    plan = build_plan({"01": "1"}, data, prod, cache)
    apply(plan, bk)
    (data / "feedback" / "rulings" / "llm-1.jsonl").write_text(
        json.dumps({"payload": {"cell": "01:10:1:2", "cells_sha": f"{old_sha}+x"}}) + "\n", encoding="utf-8")
    (data / "feedback" / "anchors" / "1.jsonl").write_text(
        json.dumps({"key": "1:10:1:2", "anchor": {"cells_sha": f"{old_sha}+x"}}) + "\n", encoding="utf-8")
    (data / "feedback" / "anchor_patches" / "1").rename(data / "feedback" / "anchor_patches" / "01")
    assert main(["--repair", str(bk), "--data-dir", str(data)]) == 0               # 只出清单
    assert main(["--repair", str(bk), "--data-dir", str(data), "--apply"]) == 0
    new_sha = _sha(prod / "1" / "cell_shrink" / "p0010.json")
    r = json.loads((data / "feedback" / "rulings" / "llm-1.jsonl").read_text(encoding="utf-8"))
    assert r["payload"] == {"cell": "1:10:1:2", "cells_sha": f"{new_sha}+x"}
    a = json.loads((data / "feedback" / "anchors" / "1.jsonl").read_text(encoding="utf-8"))
    assert a["anchor"]["cells_sha"] == f"{new_sha}+x"
    assert (data / "feedback" / "anchor_patches" / "1" / "ab" / "abc.png").exists()
    assert len(list(bk.glob("repair-*"))) == 1


def test_corpus_pins_moved_and_vol_layer_refused(tmp_path):
    """11-28 殿本 vol01 演练：语料钉子账 pins/<册>.json 没跟着挪，cv 语料指纹退回 corpus-vN，align_ref 起整串误判过期。"""
    prod, cache, data, _ = _setup(tmp_path)
    pins = data / "config" / "corpus-pack" / "pins"
    pins.mkdir(parents=True)
    body = json.dumps({"rows": [{"n": 9, "global": None, "book": 9, "vol": None}]})
    (pins / "01.json").write_text(body, encoding="utf-8")
    plan = build_plan({"01": "1"}, data, prod, cache)
    assert not plan.conflicts
    apply(plan, tmp_path / "bk")
    assert not (pins / "01.json").exists()
    assert (pins / "1.json").read_text(encoding="utf-8") == body          # 只挪不改
    (data / "config" / "corpus-vol" / "1").mkdir(parents=True)
    plan2 = build_plan({"1": "01"}, data, prod / "none", None)
    assert any("corpus-vol/1/" in c for c in plan2.conflicts)
