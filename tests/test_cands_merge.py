"""cands/1 并进待审条目：只追加新 ver、幂等、u 不符不配、只动 open 条目。"""
from guji_manager.review import pending_items as P
from guji_manager.review.cands_merge import merge_cands


def _cands(by="v1", chars="鶴鸖"):
    return {"v": "cands/1", "by": by, "top": 2, "p_other": None,
            "list": [{"c": c, "p": None, "fam": c, "src": {"c": 0.9}} for c in chars]}


def _store(tmp_path):
    s = P.ItemStore.open(tmp_path, "995ejelvk0", "004")
    for cell, u in (("1:1:1", 11), ("1:1:2", 12), ("1:1:3", 13), ("1:1:4", 14)):
        s.add(cell, {"why": ["x"]}, by="t", src="script:t", u=u)
    s.save()
    return P.ItemStore.open(tmp_path, "995ejelvk0", "004")


def test_merge_appends_once(tmp_path):
    s = _store(tmp_path)
    s.withdraw("1:1:4", by="t")
    cards = [{"id": "vol04:1:1:1", "u": 11, "cands": _cands()},
             {"id": "vol04:1:1:2", "u": 99, "cands": _cands()},       # u 不符
             {"id": "vol04:1:1:4", "u": 14, "cands": _cands()}]       # 撤下的不动
    r = merge_cands(s, cards, by="t")
    assert r["追加"] == 1 and r["u 不符"] == 1 and r["无卡"] == 1 and r["open"] == 3
    s.save()
    s = P.ItemStore.open(tmp_path, "995ejelvk0", "004")
    it = s.find("1:1:1")[0]
    assert it["ver"] == 2 and it["op"] == "cands" and it["doc"]["cands"]["list"][0]["c"] == "鶴"
    assert it["doc"]["why"] == ["x"] and it["u"] == 11                  # 别的字段不动
    assert "cands" not in (s.find("1:1:2")[0]["doc"])
    # 幂等：同样的再并一次不追加；算法版本变了才追加
    assert merge_cands(s, cards, by="t")["已有"] == 1
    cards[0]["cands"] = _cands(by="v2")
    assert merge_cands(s, cards, by="t")["追加"] == 1


def test_cards_of_items():
    from guji_manager.review.cands_attach import cards_of_items
    it = {"id": "pi_x", "cell": "36:4:4b", "u": 7,
          "doc": {"refc": "棘", "lib_top": [{"c": "𣗥", "s": 0.99}, {"c": "棘", "s": 0.97}]}}
    c = cards_of_items("004", [it, {"id": "pi_y", "cell": "bad", "doc": {}}])
    assert len(c) == 1 and c[0]["id"] == "004:36:4:4b" and (c[0]["page"], c[0]["col"], c[0]["slot"], c[0]["sub"]) == (36, 4, 4, "b")
    assert c[0]["ref"] == {"char": "棘"} and c[0]["db"]["candidates"][0] == ["𣗥", 0.99] and c[0]["u"] == 7
