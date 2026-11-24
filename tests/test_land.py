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
    f.parent.mkdir(parents=True, exist_ok=True)
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


def test_land_apply_route_flag():
    out = land_argv(["p", "vol05", "-w", "/ws", "--text-id", "t", "--land-apply"])
    assert "--apply" in out and out.index("--apply") < out.index("--run")


def test_apply_seg_and_added_cells():
    from guji_manager import land_enrich as E
    rows = [{"格号": "1:1:1", "seg_kind": "clipped", "特征": "f1", "放行": "是", "通道": "machine"},
            {"格号": "2:2:2", "seg_kind": "clipped", "特征": "f2", "放行": "是", "通道": "human"},
            {"格号": "3:3:3", "seg_kind": "other", "特征": "", "放行": "是", "通道": "machine"},
            {"格号": "9:9:9", "seg_kind": "clipped", "特征": "f9", "放行": "否", "通道": "machine"}]
    kinds = ["clipped"]
    assert E.seg_added_cells(rows, kinds, {"9:9:9"}) == ["1:1:1"]
    out, tagged = E.apply_seg([{"cell": "1:1:1", "why": ["x"]}, {"cell": "9:9:9"}], rows, kinds, {"1:1:1"})
    assert out[0]["why"] == ["x", "seg_defect"] and out[0]["seg_kind"] == "clipped" and out[0]["src"] == "seg_selfcheck"
    assert out[1]["selfcheck_kind"] == "clipped" and tagged == 1


def test_alt_glyph_images_content_addressed(tmp_path):
    import numpy as np
    from guji_manager import land_enrich as E
    def render(ch):
        a = np.full((256, 256), 255, dtype="uint8")
        a[60:200, 60:200] = 0 if ch == "甲" else 128
        return a
    cells = [{"cell": "1:1:1", "alt": [{"c": "甲"}, {"c": "乙"}, {"c": "丙"}]}, {"cell": "2:2:2", "alt": [{"c": "甲", "g": {"s": "old"}}]}]
    out, sprites = E.alt_glyph_images(cells, tmp_path, render=lambda ch: None if ch == "丙" else render(ch))
    assert len(sprites) == 2 and all(s["name"].startswith("a") and (tmp_path / s["name"]).exists() for s in sprites)
    assert out[0]["alt"][0]["g"]["s"] == out[1]["alt"][0]["g"]["s"]        # 同字同图
    assert "g" not in out[0]["alt"][2]                                         # 没字形的不出图


def test_attach_sprites_and_sheet_rev_unchanged(tmp_path):
    st = _store(tmp_path, [{**_cell("1:1:1"), "img": {"s": "c1.webp"}}])
    n = land.attach_sprites(st, [{"name": "c1.webp", "sha256": "ab", "md5": "cd", "bytes": 1}])
    assert n == 1
    head = {"rev": "001-r3", "cv_version": "0.9.0"}
    sheet = P.export_sheet(st, head)
    assert sheet["rev"] == "001-r3" and sheet["sprites"][0]["name"] == "c1.webp" and len(sheet["cells"]) == 1


def test_move_guard_blocks_when_rev_votes_exist(tmp_path):
    import pytest
    pytest.importorskip("cv2")
    st = _store(tmp_path, [_cell("1:1:1")])
    plan = land.plan_book(st, [_cell("1:1:2")], src="land", fps={})
    plan["挪格"] = ["1:1:1→1:1:2"]
    assert land.move_guard({**plan, "挪格": []}, "t", "001-r3", fetch=lambda: []) is None
    assert land.move_guard(plan, "t", None) is not None
    rows = [{"key": "cr:001-r3:t:1:1:1", "value": {"v": 1}, "deleted": False}]
    import guji_manager.feedback.web_inbox as WI
    WI_live = WI.live_rows
    try:
        WI.live_rows = lambda r: r
        g = land.move_guard(plan, "t", "001-r3", fetch=lambda: rows)
    finally:
        WI.live_rows = WI_live
    assert g and g["rev_votes"] == 1


def test_hand_added_cells_not_closed_and_detail(tmp_path):
    s = P.ItemStore(tmp_path / "pending" / "t" / "001.items.jsonl", "t", "001")
    P.reconcile(s, [_cell("1:1:1")], src="pack:x")
    s.add("9:9:9", {"note": "手加"}, by="u", src="human:u")
    s.save()
    st = P.ItemStore(s.path, "t", "001")
    plan = land.plan_book(st, [_cell("1:1:1", why="R02")], src="land")
    assert "9:9:9" not in plan["关"] and plan["改"] == ["1:1:1"]
    rows = land.detail_rows(st, plan["_store"])
    assert [r["cell"] for r in rows] == ["1:1:1"] and rows[0]["doc_keys"] == "why"
    f = land.write_detail(tmp_path / "ws", "vol01", rows)
    assert f.read_text(encoding="utf-8").splitlines()[0].startswith("cell\taction")


def test_human_deduct_only_for_cells_without_item(tmp_path):
    st = _store(tmp_path, [_cell("1:1:1")])
    keep, drop = land.human_deduct(st, [_cell("1:1:1"), _cell("2:2:2"), {**_cell("3:3:3"), "recheck": True}], {"1:1:1", "2:2:2", "3:3:3"})
    assert [c["cell"] for c in keep] == ["1:1:1", "3:3:3"] and drop == ["2:2:2"]


def test_human_src_doc_untouched(tmp_path):
    s = P.ItemStore(tmp_path / "pending" / "t" / "001.items.jsonl", "t", "001")
    s.add("5:5:5", {"note": "人写的备注"}, by="u", src="human:qtw-web")
    s.save()
    st = P.ItemStore(s.path, "t", "001")
    plan = land.plan_book(st, [{**_cell("5:5:5"), "note": "机器想改", "pending_reason": "R01"}], src="land")
    doc = plan["_store"].find("5:5:5")[0]["doc"]
    assert doc == {"note": "人写的备注"} or doc.get("note") == "人写的备注"
    assert "pending_reason" not in doc and plan["改"] == []


def test_resolved_reopen_on_image_change_marks_recheck(tmp_path):
    st = _store(tmp_path, [{**_cell("1:1:1")}])
    st2 = P.ItemStore(st.path, "t", "001")
    P.reconcile(st2, [_cell("1:1:1")], src="x", fps={"1:1:1": "aaa"})
    st2.resolve("1:1:1", by="h", event="ev9")
    st2.save()
    st3 = P.ItemStore(st.path, "t", "001")
    plan = land.plan_book(st3, [_cell("1:1:1")], src="land", fps={"1:1:1": "bbb"})
    assert plan["重开"] == [] and not plan["changed"]       # 指纹变不算图变：已裁保持已裁
    assert plan["_store"].find("1:1:1")[0]["state"] == "resolved"
    # 机器明确要求复审（recheck）才重开，带上原人裁
    plan = land.plan_book(st3, [{**_cell("1:1:1"), "recheck": True}], src="land", fps={"1:1:1": "bbb"})
    assert plan["重开"] == ["1:1:1"]
    d = plan["_store"].find("1:1:1")[0]["doc"]
    assert d["recheck"] is True
