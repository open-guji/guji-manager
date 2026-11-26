# -*- coding: utf-8 -*-
"""形近字组 members（cv#1921）→ 相似字 alt 里每个组员都有按钮；没有 members 保持旧行为。"""
import numpy as np

from guji_manager.review.alt_cands import ensure_members, group_members_of, pivots_of
from guji_manager.review.proof_fields import pending_fields


def test_group_members_of():
    assert group_members_of({"group": {"id": "jys", "members": ["己", "巳", "已", "己"]}}) == ["己", "巳", "已"]
    assert group_members_of({"group": {"members": "日曰"}}) == ["日", "曰"]
    assert group_members_of({"group": {"id": "jys"}}) == []      # 旧产物：回退旧行为
    assert group_members_of(None) == []


def test_pivots_include_members():
    assert pivots_of({"char": "己", "group_members": ["己", "巳", "已"]}) == ["己", "巳", "已"]
    assert pivots_of({"char": "己"}) == ["己"]


def test_ensure_members_fills_missing_only():
    q = np.array([1.0, 0.0])
    vec = {"巳": np.array([0.6, 0.8]), "已": np.array([0.9, 0.1])}
    ranked = [{"c": "己", "s": 0.95, "p": "己", "src": "x"}]
    out = ensure_members(ranked, ["己", "巳", "已"], q, lambda cs: {c: vec[c] for c in cs if c in vec})
    assert [a["c"] for a in out] == ["己", "已", "巳"]
    assert out[0]["src"] == "x" and out[1]["src"] == "group"
    assert ensure_members(ranked, ["己"], q, None) is ranked      # 都有就不动
    out = ensure_members([], ["日", "曰"], None, None)             # 排不了序：无分，保持组内顺序
    assert [(a["c"], a["s"]) for a in out] == [("日", None), ("曰", None)]
    assert pending_fields({"alt": out})["alt"][0]["s"] is None


def test_ensure_members_keeps_members_within_cap():
    from guji_manager.review.alt_cands import ALT_K
    ranked = [{"c": chr(0x4e00 + i), "s": 0.9 - i * 0.001, "p": "", "src": "x"} for i in range(ALT_K)]
    out = ensure_members(ranked, ["己", "巳"], np.array([1.0, 0.0]), lambda cs: {c: np.array([0.0, 1.0]) for c in cs})
    assert len(out) == ALT_K and {"己", "巳"} <= {a["c"] for a in out}
