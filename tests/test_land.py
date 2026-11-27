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


def test_sheet_conflict_rederives_from_merged_items(tmp_path, monkeypatch):
    """现行单两边都改（SyncConflict）：以库为准重派生——拉库里的单、推条目（追加合并）、用合并后的条目重导单再推。"""
    data = tmp_path / "data"
    items_p = P.items_path(data, "t", "001")
    sheet_p = P.sheet_path(data, "t", "001")
    sheet_p.parent.mkdir(parents=True)
    sheet_p.write_text(json.dumps({"rev": "001-r1", "cells": []}), encoding="utf-8")
    items_p.parent.mkdir(parents=True)
    st = P.ItemStore(items_p, "t", "001")
    P.reconcile(st, [_cell("1:1:1")], src="seed")
    calls = []

    def fake(ws, verb, paths, force=False):
        calls.append((verb, tuple(p.rsplit("/", 1)[-1] for p in paths), force))
        if verb == "sync" and len(paths) == 2 and calls.count(calls[-1]) == 1:
            return 1                                    # 第一次整体推：现行单冲突
        if verb == "sync" and len(paths) == 1:          # 条目文件合并推上去：库里同时多了一条新条目
            extra = P.ItemStore(items_p, "t", "001")
            P.reconcile(extra, [_cell("1:1:1"), _cell("7:7:7")], src="inbox", close_missing=False)
            extra.save()
        return 0
    monkeypatch.setattr(land, "db_only", fake)
    out = land.apply_changes(tmp_path, "vol01", data=data, text_id="t", chapter="001", work=st, sprites=[], files_dir=None)
    assert out["synced"] and out["rederived"]
    assert [c[0] for c in calls] == ["sync", "pull", "sync", "sync"] and calls[1][2] is True
    cells = {c["cell"] for c in json.loads(sheet_p.read_text(encoding="utf-8"))["cells"]}
    assert cells == {"1:1:1", "7:7:7"}


def test_alt_added_counts_as_change_and_digest_not_skipped(tmp_path, monkeypatch):
    """出单时没有相似字（空）→ 补了 audit alt（有）：doc 级改动里 alt 要算有变、要写；digest 不同不被整册跳过。"""
    st = _store(tmp_path, [_cell("1:1:1")])
    alt = [{"c": "柳", "s": 0.9}]
    plan = land.plan_book(st, [{**_cell("1:1:1"), "alt": alt}], src="land")
    assert plan["改"] == ["1:1:1"]
    assert land.alt_changed(st, plan["_store"], plan["改"]) == ["1:1:1"]
    # 没变 alt 时不算
    st2 = _store(tmp_path / "b", [{**_cell("1:1:1"), "alt": alt}])
    plan2 = land.plan_book(st2, [{**_cell("1:1:1"), "alt": alt, "why": "R02"}], src="land")
    assert land.alt_changed(st2, plan2["_store"], plan2["改"]) == []


def _char(cells):
    return {"version": "1", "pages": [{"page": 1, "columns": [{"cells": [{"a": a, "c": c, **({"lacuna": True} if c == "□" else {})} for a, c in cells]}]}]}


def test_text_plan_fills_blank_from_pack_and_keeps_human(tmp_path, monkeypatch):
    """包放行（含人裁放行）的字补进 book-text 的 □；人裁字与包冲突时保人裁；没变的不进计划。"""
    from guji_manager import land_text as T
    from guji_manager.swap import booktext as B
    old = _char([("1:1:1", "□"), ("1:1:2", "甲"), ("1:1:3", "乙")])
    new = _char([("1:1:1", "巿"), ("1:1:2", "甲"), ("1:1:3", "丙")])
    exp = tmp_path / "exp"
    exp.mkdir()
    (exp / "001.char.json").write_text(json.dumps(new), encoding="utf-8")
    monkeypatch.setattr(B, "_git", lambda *a, **k: "")
    monkeypatch.setattr(B, "_bt_dir", lambda repo, tid: tmp_path / "bt" / tid)
    monkeypatch.setattr(T, "_show_dev", lambda src, rel: old if rel.endswith(".char.json") else None)
    monkeypatch.setattr(B, "load_human", lambda book: {"1:1:3": "乙"})
    (tmp_path / "bt" / "t").mkdir(parents=True)
    plan = T.text_plan(tmp_path, "vol01", text_id="t", book_text=tmp_path / "bt", pending={}, export=exp)
    got = {c[0]: c for c in plan["changes"]}
    assert got["1:1:1"][3] == "巿"                      # □ 补包字
    assert "1:1:2" not in got                           # 没变
    assert "1:1:3" not in got or got["1:1:3"][3] == "乙"   # 人裁最高，不被包改


def test_hand_cell_gets_alt_but_nothing_else(tmp_path):
    """手加格没有候选字：补 alt；doc 里别的键一律不碰（机器的 note／原因不覆盖）。"""
    s = P.ItemStore(tmp_path / "pending" / "t" / "001.items.jsonl", "t", "001")
    s.add("5:5:5", {"note": "人写的备注"}, by="u", src="human:qtw-web")
    s.save()
    st = P.ItemStore(s.path, "t", "001")
    alt = [{"c": "柳", "s": 0.9}]
    plan = land.plan_book(st, [{**_cell("5:5:5"), "note": "机器想改", "alt": alt}], src="land")
    doc = plan["_store"].find("5:5:5")[0]["doc"]
    assert doc["alt"] == alt and doc["note"] == "人写的备注" and "pending_reason" not in doc
    assert land.alt_changed(st, plan["_store"], plan["改"]) == ["5:5:5"]


def test_load_cards_keys_by_bare_cell_and_old_alt_kept(tmp_path):
    """review.cards 出的卡只有 id（册:格号）：按裸格号存，land 才找得到；新判没算出 alt 就保留条目里原有的，不冲掉。"""
    from guji_manager import land_enrich as E
    d = tmp_path / "reports" / "vol19"
    d.mkdir(parents=True)
    (d / "vol19.cards.alt.json").write_text(json.dumps([{"id": "vol19:86:8:19", "alt": [{"c": "柳"}]}, {"id": "vol19:1:1:1", "cell": "1:1:1"}]), encoding="utf-8")
    cards = E.load_cards(tmp_path, "vol19")
    assert set(cards) == {"86:8:19", "1:1:1"}
    alt = [{"c": "柳", "s": 0.9}]
    st = _store(tmp_path, [{**_cell("1:1:1"), "alt": alt}])
    kept = land.keep_old_alt(st, [_cell("1:1:1")])
    assert kept[0]["alt"] == alt
    plan = land.plan_book(st, kept, src="land")
    assert not plan["改"]                                  # alt 没被冲掉：没变


def test_clean_book_cache_and_products(tmp_path):
    for d in ("cache/b1", "products/b1", "_packs/x/b1"):
        (tmp_path / d).mkdir(parents=True)
        (tmp_path / d / "f").write_bytes(b"1")
    land.clean_book(tmp_path, "b1")
    assert not (tmp_path / "cache/b1").exists() and not (tmp_path / "_packs/x/b1").exists()
    assert (tmp_path / "products/b1").exists()          # 默认不动 products
    land.clean_book(tmp_path, "b1", products=True)
    assert not (tmp_path / "products/b1").exists()


def test_alt_pending_bypasses_digest_skip(tmp_path, monkeypatch):
    monkeypatch.setattr(land, "hand_without_alt", lambda *a, **k: ["1:2:3"])
    res = {"cells": [{"cell": "1:2:3", "alt": ["x"]}]}
    assert land.alt_pending(tmp_path, "b", "t", "001", res)
    assert not land.alt_pending(tmp_path, "b", "t", "001", {"cells": [{"cell": "1:2:3"}]})


def test_ensure_alt_cards_reruns_for_card_without_alt(tmp_path, monkeypatch):
    ws = tmp_path
    f = ws / "reports" / "b" / "b.cards.alt.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps([{"id": "b:1:2:3", "admit": True}]), encoding="utf-8")
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "audit" in cmd:                                   # 第二次（补拉后）才算出 alt
            if sum("audit" in c for c in calls) >= 2:
                f.write_text(json.dumps([{"id": "b:1:2:3", "admit": True, "alt": [{"c": "字"}]}]), encoding="utf-8")
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(land.subprocess, "run", fake_run)
    monkeypatch.setattr(land, "run_killing", lambda cmd, env, timeout: (calls.append(cmd), True)[1])
    land.ensure_alt_cards(ws, "b", ["1:2:3"], None, need_alt=["1:2:3"])
    assert sum("audit" in c for c in calls) == 2 and any("source" in c for c in calls)
    assert land._E.load_cards(ws, "b")["1:2:3"].get("alt")
    calls.clear()
    land.ensure_alt_cards(ws, "b", ["1:2:3"], None, need_alt=["1:2:3"])   # 已有 alt：不再跑
    assert not calls


def test_resolved_recheck_cell_gets_alt_only(tmp_path):
    s = P.ItemStore(tmp_path / "pending" / "t" / "001.items.jsonl", "t", "001")
    r = s.put(None, op="open", by="x", at="2026-11-01", id="pi_1", cell="1:2:3", fp="f", state="resolved",
              doc={"recheck": True, "review": "human"}, src="import:r11")
    s.save()
    s = P.ItemStore(s.path, "t", "001")
    out = P.reconcile(s, [{"cell": "1:2:3", "review": "pending", "alt": [{"c": "字"}]}], src="land:b", fps={"1:2:3": "f"})
    assert out["改"] == ["1:2:3"] and out["保持已裁"] == ["1:2:3"]
    it = s.find("1:2:3")[0]
    assert it["state"] == "resolved" and it["doc"]["alt"] and it["doc"]["review"] == "human"


def test_hand_resolved_recheck_not_reopened_and_restored(tmp_path):
    s = P.ItemStore(tmp_path / "pending" / "t" / "001.items.jsonl", "t", "001")
    s.put(None, op="open", by="x", at="2026-11-01", id="pi_1", cell="1:2:3", fp="f", state="resolved",
          doc={"recheck": True, "review": "human"}, src="human:qtw-web")
    s.put(None, op="machine:doc+reopen", by="x", at="2026-11-01", id="pi_2", cell="1:2:4", fp="g", state="open",
          doc={"recheck": True, "review": "human"}, src="human:qtw-web")
    s.save()
    s = P.ItemStore(s.path, "t", "001")
    out = P.reconcile(s, [{"cell": "1:2:3", "review": "pending", "alt": [{"c": "字"}]}], src="land:b",
                      fps={"1:2:3": "f"}, keep_src=land.HAND_SRC, fp_reopen=False)
    assert out["重开"] == [] and s.find("1:2:3")[0]["state"] == "resolved"
    assert land.repair_reopened(s) == ["1:2:4"] and s.find("1:2:4")[0]["state"] == "resolved"


def test_sheet_stale_detects_missing_alt(tmp_path):
    s = _store(tmp_path, [_cell("1:2:3")])
    it = s.find("1:2:3")[0]
    s.put(it, op="machine:doc", doc={**it["doc"], "alt": [{"c": "柳"}]})
    sh = P.sheet_path(tmp_path, "t", "001")
    sh.parent.mkdir(parents=True)
    sh.write_text(json.dumps({"cells": [{"id": it["id"], "cell": "1:2:3"}]}), encoding="utf-8")
    assert land.sheet_stale(tmp_path, "t", "001", s) == ["1:2:3"]


def test_zero_byte_state_files_are_ignored(tmp_path):
    f = tmp_path / "x" / "alt-tried.json"
    f.parent.mkdir()
    f.write_text("", encoding="utf-8")
    assert land.read_json(f, []) == []
    land.atomic_write(f, "[1]")
    assert land.read_json(f) == [1] and not list(f.parent.glob("*.tmp"))
    c = tmp_path / "reports" / "b" / "b.cards.alt.json"
    c.parent.mkdir(parents=True)
    c.write_text("", encoding="utf-8")
    assert land._E.load_cards(tmp_path, "b") == {}


def test_ensure_alt_cards_low_disk_and_warm_timeout(tmp_path, monkeypatch, capsys):
    f = tmp_path / "reports" / "b" / "b.cards.alt.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps([{"id": "b:7:2:3", "admit": True}]), encoding="utf-8")
    calls = []

    def fake_run(cmd, **kw):
        return type("R", (), {"returncode": 1})()

    def fake_kill(cmd, env, timeout):
        calls.append(cmd)
        return "warm" not in cmd                       # warm 超时

    monkeypatch.setattr(land.subprocess, "run", fake_run)
    monkeypatch.setattr(land, "run_killing", fake_kill)
    monkeypatch.setattr(land, "MIN_FREE_GB", 10 ** 9)           # 盘不够：不补拉
    land.ensure_alt_cards(tmp_path, "b", ["7:2:3"], None, need_alt=["7:2:3"])
    assert not calls and "盘只剩" in capsys.readouterr().err
    monkeypatch.setattr(land, "MIN_FREE_GB", 0)                 # warm 超时：清楚报错、不抛，且只 warm 缺图的页
    land.ensure_alt_cards(tmp_path, "b", ["7:2:3"], None, need_alt=["7:2:3"])
    assert "超过" in capsys.readouterr().err
    w = [c for c in calls if "warm" in c][0]
    assert w[w.index("--pages") + 1] == "7"


def test_run_killing_kills_group(tmp_path):
    import sys
    import time
    t0 = time.time()
    ok = land.run_killing([sys.executable, "-c", "import time,subprocess,sys; subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); time.sleep(30)"], {}, 1)
    assert not ok and time.time() - t0 < 10


def test_default_text_id_from_workspace(tmp_path):
    from guji_manager.collect import default_text_id
    ws = tmp_path / "995ejelvk0-quan-tang-wen"
    ws.mkdir()
    assert default_text_id(ws) == "995ejelvk0"
    (ws / "workspace.yaml").write_text("text_id: abc1234567\n", encoding="utf-8")
    assert default_text_id(ws) == "abc1234567"
    other = tmp_path / "ws"
    other.mkdir()
    assert default_text_id(other) == "96mid1ogzk"


def test_sync_fig_boxes_follows_rebased_cord():
    from guji_manager.formats import guji_char_cord as cc
    char = {"pages": [{"page": 158, "columns": [{"col": 4, "cells": [{"a": "158:4:19", "c": "□", "fig": "f1"}]}]}]}
    cord = {"pages": [{"page": 158, "cells": [{"a": "158:4:19", "box": [1039, 2106, 96, 117]}], "marks": []}]}
    fig = {"figures": [{"id": "f1", "kind": "inline", "page": 158, "box": [1039, 2107, 96, 117]}]}
    assert cc.sync_fig_boxes(char, cord, fig) == 1 and fig["figures"][0]["box"] == [1039, 2106, 96, 117]
    assert cc.sync_fig_boxes(char, cord, fig) == 0


def test_warm_if_cold_runs_parallel_warm_only_when_cache_empty(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(land, "run_killing", lambda cmd, env, timeout: (calls.append(cmd), True)[1])
    monkeypatch.setattr(land, "MIN_FREE_GB", 0)
    assert land.warm_if_cold(tmp_path, "b", jobs=4) is True
    w = calls[0]
    assert "warm" in w and w[w.index("--jobs") + 1] == "4" and w[w.index("--book") + 1] == "b"
    d = tmp_path / "cache" / "b"
    d.mkdir(parents=True)
    for i in range(25):
        (d / f"{i}.png").write_bytes(b"1")
    calls.clear()
    assert land.warm_if_cold(tmp_path, "b") is False and not calls


_NOTE = {"book": "b", "u": 7, "cell": "b:1:2:3", "cands": ["甲", "乙"],
         "trace": [{"level": "L2", "char": "甲", "conf": "high", "why": "文意", "status": "pending"}]}


def test_merge_cards_attaches_notes_by_book_u():
    from guji_manager import land_enrich as E
    from guji_manager.review.dian_trace import find_note  # noqa: F401
    idx = {("u", "b", 7): _NOTE}
    out = E.merge_cards([{"cell": "1:2:3", "review": "pending"}], {}, idx, {"1:2:3": 7}, "b")
    assert out[0]["ctx"]["c"] == "甲" and out[0]["ctx"]["src"] == "punct_llm"
    assert E.merge_cards([{"cell": "1:2:3"}], {}, idx, {"1:2:3": 8}, "b")[0].get("ctx") is None


def test_hand_item_backfills_ai_without_touching_other_keys(tmp_path):
    s = P.ItemStore(tmp_path / "pending" / "t" / "001.items.jsonl", "t", "001")
    s.put(None, op="open", by="x", at="2026-11-01", id="pi_1", cell="1:2:3", fp="f", state="open",
          doc={"why": ["人工"], "review": "pending"}, src="human:qtw-web")
    s.save()
    s = P.ItemStore(s.path, "t", "001")
    P.reconcile(s, [{"cell": "1:2:3", "review": "pending", "why": ["机器"], "ai": {"s": "摘要"}, "dnote": "n"}],
                src="land:b", fps={"1:2:3": "f"}, keep_src=land.HAND_SRC, fp_reopen=False)
    d = s.find("1:2:3")[0]["doc"]
    assert d["ai"] == {"s": "摘要"} and d["dnote"] == "n" and d["why"] == ["人工"]


def test_attach_dian_finds_note_from_card_id(monkeypatch):
    from guji_manager.review import dian_attach as DA
    import guji_manager.u_stamp as U
    monkeypatch.setattr(U, "u_map", lambda book, ids: {i: 7 for i in ids})
    cards, n = DA.attach_dian([{"id": "b:1:2:3"}], {("u", "b", 7): _NOTE})
    assert n == 1 and cards[0]["dian"]["char"] == "甲"
