# -*- coding: utf-8 -*-
"""审阅卡「相似字」alt：近似字 → 三家异体族合并 → 按字块图排序 → pending 字段。

数据全在测试里造（字统网响应、部件檢索表、向量），不联网、不需要 torch；
只有 `family_pool` 读本仓 `config/variants/variants.json` 的现成边（弊—𡚁）。
"""
from __future__ import annotations

import io
import json

import numpy as np

from open_guji_cv.clustering import variant_sources as vs
from guji_manager.review.alt_cands import attach, pivots_of, rank_pool
from guji_manager.review.proof_fields import pending_fields


def _zi_doc(q: str, forms: list[str]) -> dict:
    """仿字统网 /api/zi/<q>：一个字形＝q 的节点，连到若干节点（字形各为 forms 里的字）。"""
    def node(k, form, zheng=""):
        n = [k, "TVAR", k, "0", form, form, form, "", None, None, zheng]
        return n + [None] * 6
    nodes = {"Q": node("Q", q)}
    edges = []
    for i, f in enumerate(forms):
        nodes[f"N{i}"] = node(f"N{i}", f)
        edges.append(["Q", f"N{i}"])
    nodes["FAR"] = node("FAR", "遠")                  # 两跳外，不收
    edges.append(["N0", "FAR"])
    return {"yi": {"nodes": nodes, "edges": edges}}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_pivots_of_priority_and_dedup():
    card = {"ref": {"char": "弊", "form": "獘"}, "ctx": {"char": "弊", "llm_suggestion": None},
            "db": {"candidates": [["敝", 0.9], ["幣", 0.8], ["蔽", 0.7], ["x", 0.1]]},
            "form": {"forms": ["𡚁"]}, "jys": None, "char": "敝"}
    assert pivots_of(card, ["斃"]) == ["弊", "獘", "敝", "幣", "蔽", "𡚁", "斃"]


def test_rank_pool_orders_by_cosine_and_drops_unrenderable():
    q = np.array([1.0, 0.0])
    vec = {"甲": np.array([0.6, 0.8]), "乙": np.array([1.0, 0.0]), "丙": np.array([0.0, 1.0])}
    pool = {c: {"p": "乙", "src": "v"} for c in ("甲", "乙", "丙", "丁")}       # 丁 渲染不出
    got = rank_pool(q, pool, lambda cs: {c: vec[c] for c in cs if c in vec}, k=2)
    assert [a["c"] for a in got] == ["乙", "甲"]
    assert got[0] == {"c": "乙", "s": 1.0, "p": "乙", "src": "v"}


def test_pending_fields_carries_alt():
    card = {"id": "b:1:2:3", "doubts": [], "ref": {"char": "弊", "op": "equal"}}
    attach([card], {"b:1:2:3": [{"c": "𡚁", "s": 0.912345, "p": "弊", "src": "v,zi"}]})
    out = pending_fields(card)
    assert out["alt"] == [{"c": "𡚁", "s": 0.9123, "p": "弊", "src": "v,zi"}]
    assert "alt" not in pending_fields({"id": "x", "doubts": []})


def test_alt_eval_ranks_and_hard_tier():
    from guji_manager.review.alt_cands import alt_eval
    cards = [
        {"id": "b:1", "ref": {"char": "弊"}, "alt": [{"c": "弊"}, {"c": "𡚁"}]},          # 整理本字即答案：不算难格
        {"id": "b:2", "ref": {"char": "弊"}, "db": {"candidates": [["敝", 0.9]]},
         "alt": [{"c": "斃"}, {"c": "獘"}, {"c": "𡚁"}]},                                 # 难格，排第 3
        {"id": "b:3", "ref": {"char": "歷"}, "alt": [{"c": "歷"}]},                      # 难格，没找到
        {"id": "b:4", "alt": [{"c": "甲"}]},                                             # 没人裁，不算
    ]
    res = alt_eval(cards, {"b:1": "弊", "b:2": "𡚁", "b:3": "厯"})
    assert res["all"]["n"] == 3 and res["all"]["top1"] == 1 and res["all"]["top3"] == 2
    assert res["hard"] == {"n": 2, "top1": 0, "top3": 1, "top5": 1, "top10": 1, "in_alt": 1, "mean_rank_when_hit": 3.0}
    assert res["hard_examples"][0] == {"g": "𡚁", "rank": 3, "old": "弊敝"}


def test_alt_for_cards_cuts_patch_when_cache_missing(monkeypatch):
    """缓存里没有字块图（从产物包出单）时走 ctx 现切；没有 ctx 就跳过并记数。"""
    from open_guji_cv.clustering import rare_panel
    from guji_manager.review import alt_cands as ac

    class Bank:
        available = True
        def embed(self, img):
            return np.array([1.0, 0.0])
        def vectors(self, chars):
            return {c: np.array([1.0, 0.0]) if c == "已" else np.array([0.0, 1.0]) for c in chars}

    class Ctx:
        keys = []
        def image(self, kind, key):
            self.keys.append((kind, key))
            return np.zeros((8, 8), np.uint8)

    monkeypatch.setattr(rare_panel, "rare_patch", lambda *a, **k: None)
    monkeypatch.setattr(rare_panel, "_book_norm_stroke", lambda b: None)
    monkeypatch.setattr("open_guji_cv.clustering.normalize.normalize_patch", lambda img, stroke_width=None: img)
    monkeypatch.setattr(vs, "family_pool", lambda piv, zi=None: {"已": {"p": "己", "src": "v"}, "巳": {"p": "己", "src": "v"}})
    card = {"id": "b:3:1:6", "page": 3, "col": 1, "slot": 6, "char": "己"}
    logs = []
    assert ac.alt_for_cards("b", [card], bank=Bank(), log=logs.append) == {}
    assert any("取不到字块图" in m for m in logs)
    ctx = Ctx()
    got = ac.alt_for_cards("b", [card], bank=Bank(), ctx=ctx)
    assert [a["c"] for a in got["b:3:1:6"]] == ["已", "巳"] and ctx.keys == [("char_patch", "p0003c01s6")]


def test_symbol_hint_threshold():
    """图像与某个符号模板够像（≥ SYM_MIN）才提示符号，否则不提示（设计 4.3 兜底）。"""
    from guji_manager.review.alt_cands import SYM_MIN, symbol_hint
    q = np.array([1.0, 0.0])
    near = np.array([SYM_MIN + 0.01, (1 - (SYM_MIN + 0.01) ** 2) ** 0.5])
    far = np.array([SYM_MIN - 0.1, (1 - (SYM_MIN - 0.1) ** 2) ** 0.5])
    assert symbol_hint(q, lambda cs: {c: (near if c == "○" else far) for c in cs}) == "○"
    assert symbol_hint(q, lambda cs: {c: far for c in cs}) is None


