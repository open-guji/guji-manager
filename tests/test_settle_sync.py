"""待审条目对账（review/settle_sync.py）：按 (书, 册, u) 配、复审格晚于复审开出才关、不碰非 open 条目。"""
import json

from guji_manager.review import pending_items as P
from guji_manager.review import settle_sync as S


def _it(i, u, cell, vol="046", state="open", recheck=False, at="2026-11-20T00:00:00Z"):
    return {"id": i, "u": u, "cell": cell, "state": state, "at": at, "_vol": vol, "doc": {"recheck": True} if recheck else {}}


def _ev(i, u, key, ts="2026-11-27T10:00:00Z"):
    return {"id": i, "u": u, "key": key, "ts": ts}


def test_norm_vol_and_key_is_cell():
    assert S.norm_vol("vol046") == "46" and S.norm_vol("046") == "46" and S.norm_vol("01") == "1"
    assert S.key_is_cell("01:11:6:10", "001", "11:6:10")
    assert S.key_is_cell("vol46:2:4:10", "046", "2:4:10")
    assert not S.key_is_cell("01:11:6:10", "002", "11:6:10")         # 别的册同号 u／同格号
    assert not S.key_is_cell("01:11:6:10", "001", "11:6:1")          # 后缀要在冒号处对齐
    assert not S.key_is_cell(None, "001", "1:1:1")


def test_plan_matches_book_vol_u_not_u_alone():
    # u=26933 在 26 册和 38 册都有；只有 26 册有裁定
    items = [_it("a", 26933, "146:8:8", vol="026"), _it("b", 26933, "146:8:8", vol="038")]
    out = S.plan(items, [_ev("e1", 26933, "26:146:8:8")])
    assert [o["item"]["id"] for o in out] == ["a"] and out[0]["event"]["id"] == "e1"


def test_plan_takes_latest_event_and_skips_non_open():
    items = [_it("a", 1, "1:1:1"), _it("b", 2, "1:1:2", state="withdrawn"), _it("c", 3, "1:1:3", state="resolved"),
             _it("d", None, "1:1:4")]
    evs = [_ev("old", 1, "46:1:1:1", "2026-11-01T00:00:00Z"), _ev("new", 1, "46:1:1:1", "2026-11-02T00:00:00Z"),
           _ev("x", 2, "46:1:1:2"), _ev("y", 3, "46:1:1:3")]
    out = S.plan(items, evs)
    assert [(o["item"]["id"], o["event"]["id"]) for o in out] == [("a", "new")]


def test_recheck_needs_ruling_later_than_recheck_opened():
    it = _it("r", 9, "5:1:1", recheck=True, at="2026-11-25T00:00:00Z")
    assert S.plan([it], [_ev("early", 9, "46:5:1:1", "2026-11-20T00:00:00Z")]) == []        # 裁定在复审之前：留着
    assert S.plan([it], [_ev("same", 9, "46:5:1:1", "2026-11-25T00:00:00Z")]) == []         # 同刻不算晚于
    out = S.plan([it], [_ev("late", 9, "46:5:1:1", "2026-11-26T00:00:00Z")])
    assert out[0]["recheck"] and out[0]["event"]["id"] == "late"


def test_recheck_since_uses_start_of_latest_open_recheck_run():
    h = [{"state": "open", "doc": {}, "at": "t1"},
         {"state": "open", "doc": {"recheck": True}, "at": "t2"},
         {"state": "open", "doc": {"recheck": True}, "at": "t3"}]       # 改字段不重置
    assert S.recheck_since(h) == "t2"
    h += [{"state": "resolved", "doc": {"recheck": True}, "at": "t4"}, {"state": "open", "doc": {"recheck": True}, "at": "t5"}]
    assert S.recheck_since(h) == "t5"                                      # 裁完又被重开：从重开起算
    assert S.recheck_since([{"state": "closed", "doc": {"recheck": True}, "at": "t"}]) is None


class _Conn:
    """把 load_events 的查询结果伪造成库里读出的行。"""
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params):
        return self

    def fetchall(self):
        return self.rows


def test_load_events_applies_manager_levels():
    rows = [("e_ok", 1, "2026-11-27T00:00:00Z", "confirm", "user", "H-x", "human", "46:1:1:1", "cell", "confirm", None, None),
            ("e_vis", 2, "2026-11-27T00:00:00Z", "confirm", "user", "H-x", "human", "46:1:1:2", "cell", "confirm", "vision", None),
            ("e_mach", 3, "2026-11-27T00:00:00Z", "confirm", "align", "H-x", "machine", "46:1:1:3", "cell", "confirm", None, "machine"),
            ("e_ai", 4, "2026-11-27T00:00:00Z", "confirm", "model", "SJ-ai~x", "ai", "46:1:1:4", "cell", "confirm", None, None),
            # AI 判字、人点按钮确认（actor=user、没写 level）：算人裁，不改判
            ("e_click", 5, "2026-11-27T00:00:00Z", "confirm", "user", "SJ-settle-1127-ai2", "human", "46:1:1:5", "cell", "confirm", None, None)]
    got = {e["id"] for e in S.load_events(_Conn(rows), "ws", [1, 2, 3, 4, 5])}
    assert got == {"e_ok", "e_ai", "e_click"}


def test_sync_workspace_apply_resolves_and_records_event(tmp_path):
    s = P.ItemStore.open(tmp_path, "bk", "046")
    a = s.add("1:1:1", {}, by="t", src="script:x", u=7)
    s.add("1:1:2", {}, by="t", src="script:x")
    s.save()
    conn = _Conn([("evt1", 7, "2026-11-27T00:00:00Z", "confirm", "user", "H-y", "human", "46:1:1:1", "cell", "confirm", None, None)])
    dry = S.sync_workspace(conn, "ws", tmp_path, apply=False)
    assert dry["resolved"] == 1 and dry["open"] == 2
    assert P.ItemStore.open(tmp_path, "bk", "046").counts()["open"] == 2          # 只算不写
    res = S.sync_workspace(conn, "ws", tmp_path, apply=True)
    assert res["resolved"] == 1 and res["rows"][0]["event"] == "evt1"
    s2 = P.ItemStore.open(tmp_path, "bk", "046")
    r = s2.items[a["id"]]
    assert r["state"] == "resolved" and r["event"] == "evt1" and r["by"] == S.BY and r["doc"]["review"] == "human"
    assert S.sync_workspace(conn, "ws", tmp_path, apply=True)["resolved"] == 0    # 幂等
