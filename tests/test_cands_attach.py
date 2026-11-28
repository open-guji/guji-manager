"""给已发册待审卡现算 cands/1（review/cands_attach）：池、图像分、前后文重排、缺模型退图像序、挂卡。全部自造数据，假填空模型。"""
from __future__ import annotations

from guji_manager.review import cands_attach as ca

CARD = {"id": "b:1:1:2", "db": {"candidates": [["鶴", 0.9518], ["鶼", 0.9476]]}, "ref": {"char": "鷂"}}
CAND50 = [["鶴", 0.90], ["鴶", 0.85], ["鶼", 0.80]] + [[chr(0x4e00 + i), 0.5 - i / 100] for i in range(12)]
FAM = {"鴶": "鶴"}


class FakeLM:
    def __init__(self, table):
        self.table, self.seen = table, []

    def sem(self, left, right, chars):
        self.seen.append((left, right))
        return {c: self.table.get(c, -10.0) for c in chars}


def fuse(pool, sem, w):
    out = [(c, s + w * sem.get(c, -10.0), sem.get(c)) for c, s in pool]
    return sorted(out, key=lambda t: -t[1])


def test_final_of_merges_3a_and_3c_and_keeps_fam_of():
    f = ca.final_of(CARD, CAND50, FAM)
    d = {x["char"]: x["evidence"] for x in f["cands"]}
    assert d["鶴"] == {"a": {"sim": 0.9518}, "c": {"sim": 0.9}}                 # 3a 与 3c 都有的字两路证据并列
    assert d["鴶"] == {"c": {"sim": 0.85, "fam_of": "鶴"}}
    assert len(f["cands"]) == 10                                                  # 3a 两个都在 3c 前 10 里，去重后 10 个
    assert ca.pool_of(f)[0] == ("鶴", 0.9518)                                    # 图像分取 a／c 大者


def test_context_reorders_and_ref_goes_first():
    lm = FakeLM({"鶼": -1.0, "鶴": -9.0})
    c = ca.cands_for_cells(CARD, CAND50, FAM, "左", "右", lm=lm, fuse=fuse, by="t")
    got = [x["c"] for x in c["list"]]
    assert got[0] == "鷂" and got[1:3] == ["鶼", "鶴"]                            # 填空把 鶼 抬到 鶴 前；整理本字永远第一
    assert lm.seen == [("左", "右")] and c["by"] == "t"
    d = {x["c"]: x["src"] for x in c["list"]}
    assert d["鶼"]["ctx"] == -1.0 and d["鶴"]["a"] == 0.9518 and d["鶴"]["c"] == 0.9 and d["鷂"] == {"ref": 1}


def test_without_lm_or_context_falls_back_to_image_order():
    for kw in ({"lm": None}, {"lm": FakeLM({}), "left": "", "right": ""}):
        left, right = kw.pop("left", "左"), kw.pop("right", "右")
        c = ca.cands_for_cells(CARD, CAND50, FAM, left, right, fuse=fuse, **kw)
        assert [x["c"] for x in c["list"]][:3] == ["鷂", "鶴", "鶼"] and "ctx" not in c["list"][1]["src"]


def test_attach_sets_cands_on_matching_cards_only():
    cards = [{"id": "b:1:1:2"}, {"id": "b:1:1:3"}]
    assert ca.attach(cards, {"b:1:1:2": {"v": "cands/1", "list": [{"c": "甲"}]}}) == 1
    assert cards[0]["cands"]["v"] == "cands/1" and "cands" not in cards[1]
