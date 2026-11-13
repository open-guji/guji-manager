"""待审条目（一格一条）：reconcile、人工操作、导入、导出。"""
import json

from guji_manager.review import pending_items as P


def _store(tmp_path):
    return P.ItemStore.open(tmp_path, "96mid1ogzk", "004")


def _cells(*xs):
    return [{"cell": c, "review": "pending", "why": [w]} for c, w in xs]


def test_reconcile_only_touches_changed(tmp_path):
    s = _store(tmp_path)
    r = P.reconcile(s, _cells(("1:1:1", "lib_low"), ("1:1:2", "ref_conflict")), src="rev:004-r1",
                    fps={"1:1:1": "f1", "1:1:2": "f2"})
    assert len(r["开"]) == 2
    s.save()
    s = _store(tmp_path)
    ids = {x["cell"]: x["id"] for x in s.items.values()}
    # 第二轮：1:1:1 不变，1:1:2 原因变了，1:1:3 新出现
    r = P.reconcile(s, _cells(("1:1:1", "lib_low"), ("1:1:2", "lib_low"), ("1:1:3", "seg_defect")),
                    src="rev:004-r2", fps={"1:1:1": "f1", "1:1:2": "f2", "1:1:3": "f3"})
    assert r["不变"] == 1 and r["改"] == ["1:1:2"] and r["开"] == ["1:1:3"]
    assert s.items[ids["1:1:1"]]["ver"] == 1
    assert s.items[ids["1:1:2"]]["ver"] == 2
    # 第三轮：1:1:3 放行了 → 关
    r = P.reconcile(s, _cells(("1:1:1", "lib_low"), ("1:1:2", "lib_low")), src="rev:004-r3",
                    fps={"1:1:1": "f1", "1:1:2": "f2"})
    assert r["关"] == ["1:1:3"]


def test_reconcile_moves_by_fingerprint_and_flags_image_change(tmp_path):
    s = _store(tmp_path)
    P.reconcile(s, _cells(("1:1:1", "a"), ("1:1:2", "b")), src="r1", fps={"1:1:1": "f1", "1:1:2": "f2"})
    id1 = next(x["id"] for x in s.items.values() if x["cell"] == "1:1:1")
    id2 = next(x["id"] for x in s.items.values() if x["cell"] == "1:1:2")
    # 重切：f1 那块图挪到 1:1:5；1:1:2 格号还在、图变了
    r = P.reconcile(s, _cells(("1:1:5", "a"), ("1:1:2", "b")), src="r2", fps={"1:1:5": "f1", "1:1:2": "g2"})
    assert s.items[id1]["cell"] == "1:1:5" and r["挪格"] == ["1:1:1→1:1:5"]
    assert s.items[id2]["fp"] == "g2" and s.items[id2]["fp_prev"] == "f2" and s.items[id2]["fp_changed"]
    assert r["图变"] == ["1:1:2"]


def test_withdrawn_stays_withdrawn(tmp_path):
    s = _store(tmp_path)
    P.reconcile(s, _cells(("2:3:4", "a")), src="r1")
    s.withdraw("2:3:4", by="sheldon", why="不用看")
    r = P.reconcile(s, _cells(("2:3:4", "b")), src="r2")
    it = s.find("2:3:4")[0]
    assert it["state"] == "withdrawn" and it["doc"]["why"] == ["b"]
    assert r["撤下仍判待审"] == ["2:3:4"]
    s.restore(it["id"], by="sheldon")
    assert s.find("2:3:4")[0]["state"] == "open"


def test_note_add_resolve_and_export(tmp_path):
    s = _store(tmp_path)
    P.reconcile(s, _cells(("1:1:1", "a"), ("1:1:2", "b")), src="r1")
    s.note("1:1:1", "旧裁 山，新票 由", by="x")
    s.add("vol04:9:9:9", {"note": "撤库重审"}, by="x", src="script:evict")
    s.withdraw("1:1:2", by="x", why="重复")
    s.resolve("9:9:9", by="x", event="evt_1")
    s.save()
    s = _store(tmp_path)
    doc = P.export_sheet(s, {"rev": "004-r1", "cells": [{"cell": "old"}], "sprites": ["a.webp"]})
    assert doc["rev"] == "004-r1" and doc["sprites"] == ["a.webp"]
    cells = {c["cell"]: c for c in doc["cells"]}
    assert set(cells) == {"1:1:1", "9:9:9"}
    assert cells["1:1:1"]["note"] == "旧裁 山，新票 由" and cells["1:1:1"]["id"].startswith("pi_")
    assert cells["9:9:9"]["review"] == "human"
    assert [w["cell"] for w in doc["withdrawn"]] == ["1:1:2"]
    assert doc["items"]["n"]["open"] == 1


def test_import_sheet_is_idempotent_and_maps_old_rev(tmp_path):
    s = _store(tmp_path)
    sheet = {"rev": "004-r13", "cells": _cells(("1:1:1", "a"), ("1:1:2", "b")),
             "withdrawn": [{"cell": "1:1:3", "why": ["c"], "withdrawn": {"by": "s", "why": "w"}}]}
    r = P.import_sheet(s, sheet, by="A31")
    assert len(r["开"]) == 2 and r["撤下"] == ["1:1:3"]
    s.save()
    s = _store(tmp_path)
    r = P.import_sheet(s, sheet, by="A31")
    assert r["不变"] == 2 and not r["开"] and not s.pending
    m = P.rev_cell_map(s, "004-r13")
    assert m["1:1:1"] == s.find("1:1:1")[0]["id"]


def test_log_is_append_only(tmp_path):
    s = _store(tmp_path)
    P.reconcile(s, _cells(("1:1:1", "a")), src="r1")
    s.save()
    s.note("1:1:1", "x", by="y")
    s.save()
    lines = s.path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["ver"] for x in lines] == [1, 2]


def test_cli_import_withdraw_export(tmp_path, capsys):
    from guji_manager.commands import run
    sheet = P.sheet_path(tmp_path, "bk", "004")
    sheet.parent.mkdir(parents=True)
    sheet.write_text(json.dumps({"rev": "004-r2", "cells": _cells(("1:1:1", "a"), ("1:1:2", "b"))}), encoding="utf-8")
    base = ["--data", str(tmp_path), "--text-id", "bk", "--chapter", "004"]
    run(["pending", "import", "vol04", *base])
    run(["pending", "withdraw", "vol04", "1:1:2", "--why", "不用看", "--by", "sheldon", *base])
    doc = json.loads(sheet.read_text(encoding="utf-8"))
    assert [c["cell"] for c in doc["cells"]] == ["1:1:1"] and doc["withdrawn"][0]["cell"] == "1:1:2"
    run(["pending", "ls", "vol04", "--state", "all", *base])
    assert "withdrawn" in capsys.readouterr().out


def test_cellvotes_item_votes_map_to_current_cell(tmp_path, monkeypatch):
    import argparse
    from guji_manager import cli_cellvotes as CV
    monkeypatch.setenv("GUJI_FEEDBACK_DIR", str(tmp_path / "feedback"))
    s = P.ItemStore.open(tmp_path, "bk", "004")
    P.reconcile(s, _cells(("1:1:1", "a")), src="r1", fps={"1:1:1": "f1"})
    P.reconcile(s, _cells(("1:1:5", "a")), src="r2", fps={"1:1:5": "f1"})   # 重切后挪到 1:1:5
    s.save()
    iid = s.find("1:1:5")[0]["id"]
    snap = tmp_path / "feedback" / "lists" / "web" / "bk" / "items.jsonl"
    snap.parent.mkdir(parents=True)
    vote = {"v": 1, "book": "bk", "vol": "004", "a": "1:1:1", "rev": "004-r1", "item": iid, "ver": 1,
            "choice": "char", "char": "於", "voter": "aa", "ts": 1}
    other = {**vote, "item": "pi_ffffffffffff", "voter": "bb"}
    snap.write_text(json.dumps(vote) + "\n" + json.dumps(other) + "\n", encoding="utf-8")
    args = argparse.Namespace(items=True, from_kv=False, from_file=None, site_book="bk", rev="004-r2", token_env="X")
    votes, where = CV._votes(args)
    assert [(v["a"], v["rev"]) for v in votes] == [("1:1:5", "004-r2")]
    assert "1 条找不到条目" in where


def test_item_sprites_merge_into_sheet(tmp_path):
    s = _store(tmp_path)
    e = {"name": "c0123456789abcdef.webp", "sha256": "a" * 64, "md5": "b" * 32, "bytes": 10}
    s.add("5:5:5", {"img": {"s": e["name"], "x": 0, "y": 0, "w": 40, "h": 40}}, by="x", src="human:x", sprites=[e])
    doc = P.export_sheet(s, {"rev": "004-r1", "sprites": [{"name": "p1.webp", "sha256": "c" * 64, "md5": "d" * 32, "bytes": 5}]})
    assert [x["name"] for x in doc["sprites"]] == ["c0123456789abcdef.webp", "p1.webp"]


def test_resolved_not_reopened_when_image_unchanged(tmp_path):
    """r18 出单：刚落的人裁，图没变、机器又判待审（含锚点类）→ 保持已裁；复审格或图真变了才重开。"""
    s = P.ItemStore(tmp_path / "x" / "001.items.jsonl")
    P.reconcile(s, _cells(("1:1:1", "a"), ("1:1:2", "a"), ("1:1:3", "a"), ("1:1:4", "a")), src="r1",
                fps={"1:1:1": "f1", "1:1:2": "f2", "1:1:3": "f3", "1:1:4": ""})
    for c in ("1:1:1", "1:1:2", "1:1:3", "1:1:4"):
        s.resolve(c, by="web")
    cells = _cells(("1:1:1", "anchor_miss"), ("1:1:2", "b"), ("1:1:3", "b"), ("1:1:4", "b"))
    cells[1]["recheck"] = True
    r = P.reconcile(s, cells, src="r2", fps={"1:1:1": "f1", "1:1:2": "f2", "1:1:3": "g3", "1:1:4": "f4"})
    st = {x["cell"]: x["state"] for x in s.items.values()}
    assert st == {"1:1:1": "resolved", "1:1:2": "open", "1:1:3": "open", "1:1:4": "resolved"}
    assert sorted(r["保持已裁"]) == ["1:1:1", "1:1:4"] and sorted(r["重开"]) == ["1:1:2", "1:1:3"]
    assert all(x["doc"]["review"] == "human" for x in s.items.values() if x["state"] == "resolved")
