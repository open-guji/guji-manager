# -*- coding: utf-8 -*-
"""形近字组 members（cv #1921 evidence.group.members）→ 待审卡 grp、相似字 alt、点校候选；没有 members 保持旧行为。"""
import numpy as np

from guji_manager.review.alt_cands import ALT_K, ensure_members, members_of, pivots_of
from guji_manager.review.dian_trace import dian_for, summarize_trace
from guji_manager.review.group_members import group_of
from guji_manager.review.proof_fields import pending_fields


def test_group_of():
    assert group_of({"group": {"id": "jys", "members": "已巳己"}}) == {"id": "jys", "m": ["已", "巳", "己"]}
    assert group_of({"group": {"id": "ri", "members": ["日", "曰", "日"]}}) == {"id": "ri", "m": ["日", "曰"]}
    assert group_of({"group": {"id": "jys"}}) is None          # 旧产物：没有 members
    assert group_of(None) is None and group_of({}) is None


def test_pending_fields_grp_only_when_members():
    assert pending_fields({"grp": {"id": "jys", "m": ["已", "巳", "己"]}})["grp"] == {"id": "jys", "m": ["已", "巳", "己"]}
    assert "grp" not in pending_fields({"grp": None})
    assert "grp" not in pending_fields({})


def test_pivots_include_members():
    card = {"char": "己", "grp": {"id": "jys", "m": ["已", "巳", "己"]}}
    assert pivots_of(card) == ["己", "已", "巳"]
    assert members_of({"char": "己"}) == [] and pivots_of({"char": "己"}) == ["己"]


def test_ensure_members_fills_missing_only():
    q = np.array([1.0, 0.0])
    vec = {"巳": np.array([0.6, 0.8]), "已": np.array([0.9, 0.1])}
    ranked = [{"c": "己", "s": 0.95, "p": "己", "src": "v"}]
    out = ensure_members(ranked, ["己", "巳", "已"], q, lambda cs: {c: vec[c] for c in cs if c in vec})
    assert [a["c"] for a in out] == ["己", "已", "巳"]
    assert out[0]["src"] == "v" and out[1]["src"] == "grp"
    assert ensure_members(ranked, ["己"], q, None) is ranked
    assert ensure_members(ranked, [], q, None) is ranked        # 旧产物不动
    out = ensure_members([], ["日", "曰"], None, None)
    assert [(a["c"], a["s"]) for a in out] == [("日", None), ("曰", None)]
    assert pending_fields({"alt": out})["alt"][0]["s"] is None


def test_ensure_members_keeps_members_within_cap():
    ranked = [{"c": chr(0x4e00 + i), "s": 0.9 - i * 0.001, "p": "", "src": "v"} for i in range(ALT_K)]
    out = ensure_members(ranked, ["己", "巳"], np.array([1.0, 0.0]), lambda cs: {c: np.array([0.0, 1.0]) for c in cs})
    assert len(out) == ALT_K and {"己", "巳"} <= {a["c"] for a in out}


def _trace(ch, conf="high"):
    return [{"level": "L1", "routes": {"A": ["日", "high"], "B": ["曰", "mid"]}},
            {"level": "L2", "char": ch, "conf": conf, "why": "文意"}]


def test_dian_member_counts_as_candidate():
    idx = {("cell", "b:1:1:1"): {"cell": "b:1:1:1", "cands": ["日", "曰"], "trace": _trace("目")}}
    old = dian_for(idx, cell="b:1:1:1")                       # 旧产物：目 在候选外
    assert "char" not in old and old["out"] == ["目"]
    new = dian_for(idx, cell="b:1:1:1", extra_cands=["日", "曰", "目"])
    assert new["char"] == "目" and "out" not in new


def test_dian_out_goes_to_dout():
    d = summarize_trace(_trace("白"), ["日", "曰"])
    assert d["out"] == ["白"]
    f = pending_fields({"dian": d})
    assert f["dout"] == ["白"] and "dnote" in f
    assert "out" not in summarize_trace(_trace("白", conf="low"), ["日", "曰"])
