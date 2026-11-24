"""guji land：待审条目对账（没变不动，变了就地覆盖）与 pipeline --land 路由。"""
import json

from guji_manager import land
from guji_manager.review import pending_items as P
from guji_manager.steps import land_argv


def _cell(cell, why="R01", c="字"):
    return {"cell": cell, "why": why, "review": "pending", "c": c}


def _store(tmp_path, cells):
    s = P.ItemStore(tmp_path / "pending" / "t" / "001.items.jsonl", "t", "001")
    P.reconcile(s, cells, src="seed")
    s.save()
    return P.ItemStore(s.path, "t", "001")


def test_unchanged_sheet_is_not_changed(tmp_path):
    st = _store(tmp_path, [_cell("1:1:1"), _cell("1:2:3")])
    res = land.plan_book(st, [_cell("1:1:1"), _cell("1:2:3")], src="land")
    assert not res["changed"] and res["不变"] == 2
    assert land.summarize(res).startswith("没变")


def test_changed_cell_overwritten_and_new_opened_missing_closed(tmp_path):
    st = _store(tmp_path, [_cell("1:1:1"), _cell("1:2:3"), _cell("2:1:1")])
    res = land.plan_book(st, [_cell("1:1:1"), _cell("1:2:3", why="R02"), _cell("9:9:9")], src="land")
    assert res["changed"]
    assert res["改"] == ["1:2:3"] and res["开"] == ["9:9:9"] and res["关"] == ["2:1:1"] and res["不变"] == 1
    assert len(st.pending) == 0          # plan 不动原 store


def test_resolved_not_reopened(tmp_path):
    st = _store(tmp_path, [_cell("1:1:1")])
    st.resolve("1:1:1", by="h")
    st.save()
    st = P.ItemStore(st.path, "t", "001")
    res = land.plan_book(st, [_cell("1:1:1")], src="land")
    assert not res["changed"] and res["保持已裁"] == ["1:1:1"]


def test_land_argv_routes_text_id_only_to_land():
    out = land_argv(["main-pipe", "vol05", "-w", "/ws", "--text-id", "tid", "--land", "--force"])
    assert out[:7] == ["land", "vol05", "-w", "/ws", "--text-id", "tid", "--run"]
    assert out[7:] == ["main-pipe", "vol05", "-w", "/ws", "--force"]


def test_land_skips_on_same_digest_and_flags_structural(tmp_path, monkeypatch):
    import guji_manager.datastore.workcopy as W
    monkeypatch.setattr(W, "data_dir", lambda ws: tmp_path / "data")
    ws = tmp_path / "ws"
    res = {"cells": [_cell("1:1:1")], "fps": {}, "digest": "d1"}
    r = land.land(ws, "vol05", text_id="t", chapter="005", res=res, apply=False, by="x", digest="d1")
    assert r["changed"] and "开" in r["summary"]                  # 条目是空的 → 新开
    f = land.landed_path(ws, "vol05")
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"digest": "d1"}), encoding="utf-8")
    r = land.land(ws, "vol05", text_id="t", chapter="005", res=res, apply=False, by="x", digest="d1")
    assert r["skipped"] == "digest" and not r["changed"]


def test_apply_not_open_yet(tmp_path, monkeypatch):
    import pytest
    import guji_manager.datastore.workcopy as W
    monkeypatch.setattr(W, "data_dir", lambda ws: tmp_path / "data")
    with pytest.raises(SystemExit):
        land.land(tmp_path / "ws", "vol05", text_id="t", chapter="005", res={"cells": [_cell("1:1:1")]}, apply=True, by="x")


def test_merge_recheck_and_read_recheck(tmp_path):
    from guji_manager import land_enrich as E
    f = tmp_path / "rc.tsv"
    f.write_text("格位\t说明\n# x\nvol05:1:1:1\t机器改判\tev1\t甲\t2026-11-01\n2:2:2\n", encoding="utf-8")
    rc = E.read_recheck(f, "vol05")
    assert rc["1:1:1"] == {"note": "机器改判", "prior": {"c": "甲", "id": "ev1", "ts": "2026-11-01"}}
    assert rc["2:2:2"] == {}
    out = E.merge_recheck([{"cell": "1:1:1"}, {"cell": "2:2:2"}, {"cell": "3:3:3"}], rc)
    assert out[0]["recheck"] and out[0]["note"] == "机器改判" and out[1]["recheck"] and "recheck" not in out[2]


def test_merge_cards_cv_keys_win():
    import pytest
    pytest.importorskip("cv2")
    from guji_manager import land_enrich as E
    out = E.merge_cards([{"cell": "1:1:1", "review": "pending", "img": {"s": "c1"}}],
                        {"1:1:1": {"cell": "1:1:1", "ctx": {"char": "甲", "margin": 0.5, "source": "x"}}})
    assert out[0]["img"] == {"s": "c1"} and out[0]["ctx"]["c"] == "甲"
