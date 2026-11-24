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
    assert out[:8] == ["land", "vol05", "-w", "/ws", "--text-id", "tid", "--apply", "--run"]
    assert out[8:] == ["main-pipe", "vol05", "-w", "/ws", "--force"]
