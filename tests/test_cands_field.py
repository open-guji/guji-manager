"""待审格候选 `cands/1`（候选字线）：排序、来源、整理本字、族键、空表、点选记录、进待审单。全部自造数据。"""
from __future__ import annotations

from guji_manager.review import cands_field as cf
from guji_manager.review.proof_fields import pending_fields

FINAL = {"cands": [
    {"char": "鶴", "p": None, "evidence": {"a": {"sim": 0.9518}, "c": {"sim": 0.9095}}},
    {"char": "鶼", "p": None, "evidence": {"a": {"sim": 0.9476}, "c": {"sim": 0.8725}}},
    {"char": "鴶", "p": None, "evidence": {"c": {"sim": 0.80, "fam_of": "鶴"}}},
    {"char": "鷂", "p": None, "evidence": {"b": {"group": "g", "cnn_small": 0.4}}},
]}
RANK = {"ran": True, "ranked": [["鶼", 0.95, 0.9476, -1.58], ["鶴", 0.90, 0.9518, -8.11], ["鴶", 0.83, 0.80, -3.0]]}


def test_order_follows_context_rank_then_image_for_the_rest():
    c = cf.build_cands(FINAL, RANK, by="t")
    assert [x["c"] for x in c["list"]] == ["鶼", "鶴", "鴶", "鷂"]      # 融合分在前；没进融合的（鷂）排后
    assert c["v"] == "cands/1" and c["top"] == 3 and c["p_other"] is None and c["by"] == "t"
    assert all(x["p"] is None for x in c["list"])


def test_sources_recorded_per_char():
    c = cf.build_cands(FINAL, RANK)
    d = {x["c"]: x for x in c["list"]}
    assert d["鶴"]["src"] == {"a": 0.9518, "c": 0.9095, "ctx": -8.11}
    assert d["鴶"]["src"]["c"] == 0.8 and d["鴶"]["fam"] == "鶴" and d["鶴"]["fam"] == "鶴"
    assert d["鷂"]["src"] == {"b": {"cnn_small": 0.4}}


def test_ref_char_goes_first_and_is_marked_even_when_not_in_pool():
    c = cf.build_cands(FINAL, RANK, ref="鷂")
    assert [x["c"] for x in c["list"]][:2] == ["鷂", "鶼"] and c["list"][0]["src"]["ref"] == 1
    c2 = cf.build_cands(FINAL, RANK, ref="鴻")
    assert c2["list"][0]["c"] == "鴻" and c2["list"][0]["src"] == {"ref": 1}


def test_without_context_rank_falls_back_to_image_sim():
    c = cf.build_cands(FINAL, None)
    assert [x["c"] for x in c["list"]][:3] == ["鶴", "鶼", "鴶"]
    c = cf.build_cands(FINAL, {"ran": False, "ranked": []})
    assert c["list"][0]["c"] == "鶴"


def test_empty_returns_none_and_max_list_caps():
    assert cf.build_cands(None, None) is None and cf.build_cands({"cands": []}, None, ref="x1") is None
    big = {"cands": [{"char": chr(0x4e00 + i), "evidence": {"c": {"sim": 1 - i / 100}}} for i in range(50)]}
    assert len(cf.build_cands(big, None)["list"]) == cf.MAX_LIST


def test_pick_fields():
    c = cf.build_cands(FINAL, RANK)
    assert cf.pick_fields(c, "鶴") == {"pick_from": ["a", "c", "ctx"], "pick_rank": 2, "pick_shown": True}
    assert cf.pick_fields(c, "鷂") == {"pick_from": ["b"], "pick_rank": 4, "pick_shown": False}
    assert cf.pick_fields(c, "鷂", shown=["鷂"])["pick_shown"] is True          # 卡上原有按钮里就有
    assert cf.pick_fields(c, "鴻") == {"pick_from": [], "pick_rank": None, "pick_shown": False}
    assert cf.pick_fields(None, "鴻", shown=["鴻"]) == {"pick_from": [], "pick_rank": None, "pick_shown": True}


def test_cands_pass_through_pending_fields():
    c = cf.build_cands(FINAL, RANK)
    assert pending_fields({"cands": c})["cands"] == c
    assert "cands" not in pending_fields({"cands": {"list": []}})
    assert "cands" not in pending_fields({})


def test_calibrated_p_goes_first_and_is_copied_and_p_map_passes_through():
    fin = {"cands": [
        {"char": "官", "p": 0.6, "evidence": {"a": {"sim": 0.9}}},
        {"char": "宮", "p": 0.3, "evidence": {"a": {"sim": 0.95}}},
        {"char": "宫", "p": None, "evidence": {"a": {"sim": 0.99}}}], "p_src": "near:cnn_small", "p_map": {"cut": 0.1}}
    c = cf.build_cands(fin, None)
    assert [x["c"] for x in c["list"]] == ["官", "宮", "宫"] and [x["p"] for x in c["list"]] == [0.6, 0.3, None]
    assert c["p_map"] == {"cut": 0.1} and c["p_other"] is None
    assert "p_map" not in cf.build_cands(FINAL, RANK)
