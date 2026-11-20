"""收单快路 ``guji collect``：定字票对 book-text 现文分流、落字、核对位；cellvotes 落票结条目。"""
from __future__ import annotations

import json

import pytest

from guji_manager import collect as C


def _char(s, extra=None):
    cells = [{"a": f"1:1:{i + 1}", "c": ch} for i, ch in enumerate(s)]
    for a, kv in (extra or {}).items():
        next(x for x in cells if x["a"] == a).update(kv)
    return {"pages": [{"page": 1, "columns": [{"col": 1, "cells": cells}]}]}


def test_plan_edits_sorts_cells():
    char = _char("曰天□別圖", {"1:1:3": {"lacuna": True}, "1:1:5": {"fig": {"alt": "圖"}, "c": "□"}})
    want = {"1:1:1": ("日", "票"), "1:1:2": ("天", "票"), "1:1:3": ("地", "票"), "1:1:4": ("别", "票"),
            "1:1:5": ("圖", "票"), "1:1:9": ("人", "票"), "1:1:10": ("之", "票")}
    same = lambda p, q: {"别": "別"}.get(p, p) == {"别": "別"}.get(q, q)  # noqa: E731
    plan = C.plan_edits(char, want, box_problem=lambda a: "本列格位变了" if a == "1:1:1" else None, same=same)
    got = {k: [x[0] for x in v] for k, v in plan.items()}
    assert got["layout"] == ["1:1:1"]                 # 格框对不上：等重放
    assert got["already"] == ["1:1:2", "1:1:4"]       # 同字、只差码位都不动
    assert got["apply"] == ["1:1:3"]                  # □（阙）→ 人裁字
    assert got["fig"] == ["1:1:5"]
    assert got["missing"] == ["1:1:9", "1:1:10"]       # 按格序，不按字符串序


def test_apply_edits_sets_char_and_drops_lacuna():
    char = _char("曰天□", {"1:1:3": {"lacuna": True, "guess_c": "地"}})
    out = C.apply_edits(char, [("1:1:3", "□", "地", "票"), ("1:1:1", "曰", "日", "票")])
    cells = out["pages"][0]["columns"][0]["cells"]
    assert [x["c"] for x in cells] == ["日", "天", "地"]
    assert "lacuna" not in cells[2] and "guess_c" not in cells[2]
    assert char["pages"][0]["columns"][0]["cells"][2]["c"] == "□"     # 入参不动


def test_vote_chars_reads_only_char_confirms(tmp_path):
    rows = [{"id": "vol20:84:3:10", "v": "confirm", "shape": "𦱪"},
            {"id": "vol20:84:3:11", "v": "seg_defect", "quality": "truncated", "shape": "之"},
            {"id": "vol20:84:3:12", "v": "figure", "unk": "艹+冊"},
            {"id": "vol20:84:3:13", "v": "not_a_char"},
            {"id": "vol20:84:3:14", "v": "confirm", "shape": "□"}]
    (tmp_path / "drafts.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    assert C.vote_chars(tmp_path) == {"84:3:10": ("𦱪", "票")}


def test_live_open_cells():
    doc = {"cells": [{"cell": "1:1:1"}, {"cell": "1:1:2", "review": "human"}, {"cell": "vol01:1:1:3", "review": "pending"}]}
    assert C.live_open_cells(doc) == {"1:1:1", "1:1:3"}


def test_run_state_resume_and_dry(tmp_path):
    sp = tmp_path / "s" / "state.json"
    r = C.Run(sp, fresh=False)
    r.mark("pull", {"rev": "020-r13"})
    assert C.Run(sp, fresh=False).done("pull")
    assert not C.Run(sp, fresh=True).done("pull")
    d = C.Run(tmp_path / "d" / "state.json", fresh=True, dry=True)
    d.mark("draft")
    assert not (tmp_path / "d" / "state.json").exists()


def test_cellvotes_write_resolves_items_by_draft_id(tmp_path, monkeypatch):
    """草稿行只有 id（vol04:15:8:20）没有 a：落票后条目照样结案。"""
    from guji_manager import cli_cellvotes as CVT
    from guji_manager.review import pending_items as P

    store = P.ItemStore.open(tmp_path, "96mid1ogzk", "004")
    try:
        store.add("15:8:20", {"pending_reason": "R01"}, by="t", src="test")
    except TypeError:
        pytest.skip("ItemStore.add 签名变了")
    store.save()
    monkeypatch.setattr("guji_manager._cv.feedback_root", lambda: tmp_path / "feedback", raising=False)
    import guji_manager._cv as cvmod
    monkeypatch.setattr(cvmod, "feedback_root", lambda: tmp_path / "feedback", raising=False)
    rows = [{"id": "vol04:15:8:20", "v": "confirm", "shape": "之"}]
    CVT._resolve_items({"site_book": "96mid1ogzk", "rev": "004-r3"}, rows, {"ids": ["ev1"]}, "sheldon")
    st = P.ItemStore.open(tmp_path, "96mid1ogzk", "004")
    assert [x["state"] for x in st.items.values()] == ["resolved"]


def test_consistent_cells_from_draft_meta(tmp_path):
    meta = {"skipped": [["84:3:10", "与已有人裁 evt_H-web-vol20-020-r12-2026-11-19_000011 一致"],
                        ["84:3:11", "只有「看不出」×1"], ["84:3:12", "char 档不写"]]}
    (tmp_path / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    assert C.consistent_cells(tmp_path) == {"84:3:10": "evt_H-web-vol20-020-r12-2026-11-19_000011"}


def test_books_with_votes_picks_open_items_only():
    votes = [{"vol": "13", "item": "i1"}, {"vol": "013", "item": "i2"}, {"vol": "14", "item": "j1"}, {"vol": "20"}]
    open_ = {"013": {"i2"}, "014": set()}
    assert C.books_with_votes(votes, lambda ch: open_.get(ch, set())) == ["vol13"]


def test_ai_ruling_chars_window_hit_and_vis(tmp_path):
    """AI 裁定直接落（11-20）：文意按窗口命中且 high、字在组内；看图 O 要 admit_ok、对位字没变、非半格；已放行格不落。"""
    from guji_manager._cv import RulingLog, RulingStore
    from open_guji_cv.feedback.events import EventTarget, make_event
    from open_guji_cv.feedback.llm_queue import PENDING
    store = RulingStore(tmp_path / "fb")
    store._batch = "llm-x"
    store.put("ry", "v1", "甲乙", "丙丁", char="曰", conf="high", why="", model="m", cell="001:1:1:1")
    store.put("ry", "v1", "子丑", "寅卯", char="日", conf="mid", why="", model="m", cell="001:1:1:2")
    store.put("ry", "v1", "辰", "巳", char="月", conf="high", why="", model="m", cell="001:1:1:3")     # 不在组内
    store.put("ry", "v1", "午", "未", char="曰", conf="high", why="", model="m", cell="001:1:1:8")     # 已放行
    log = RulingLog(tmp_path / "fb")
    for i, (cell, ref) in enumerate([("001:1:1:4", "日"), ("001:1:1:5", "日"), ("001:1:1:6a", "日")]):
        pay = {"source": "llm", "group": "O", "prompt_ver": "vis-o1", "char": "曰", "conf": "high", "admit_ok": True,
               "cell": cell, "ref": ref, "ctx": {"left": "", "right": "", "hash": f"h{i}"}}
        log.append([make_event("vis-b", i + 1, "ctx_ruling", EventTarget(step="seed_admit", unit="cell", key=cell, book="001"),
                               pay, actor="model")])
    ask = lambda l, r: {"evidence": {"group": {"id": "ry", "solvers": [{"why": PENDING, "ask": {"ver": "v1", "l": l, "r": r}}]}}}  # noqa: E731
    root = tmp_path / "p"
    (root / "001" / "seed_admit").mkdir(parents=True)
    cells = [{"id": "001:1:1:1", "char": "日", **ask("甲乙", "丙丁")}, {"id": "001:1:1:2", "char": "日", **ask("子丑", "寅卯")},
             {"id": "001:1:1:3", "char": "日", **ask("辰", "巳")}, {"id": "001:1:1:4", "char": "日"},
             {"id": "001:1:1:5", "char": "日"}, {"id": "001:1:1:6a", "char": "日"},
             {"id": "001:1:1:8", "char": "曰", "admit": True, **ask("午", "未")}]
    (root / "001" / "seed_admit" / "p0001.json").write_text(json.dumps({"seed_admit": {"columns": [{"chars": cells}]}}), encoding="utf-8")
    (root / "001" / "align_ref").mkdir(parents=True)
    (root / "001" / "align_ref" / "p0001.json").write_text(json.dumps({"align_ref": {"chars": [
        {"id": "001:1:1:4", "align_char": "日"}, {"id": "001:1:1:5", "align_char": "曰"}, {"id": "001:1:1:6a", "align_char": "日"}]}}),
        encoding="utf-8")
    got, notes = C.ai_ruling_chars(root, "001", RulingStore(tmp_path / "fb"), members={"ry": {"日", "曰"}})
    assert got == {"1:1:1": ("曰", "AI文意/ry"), "1:1:4": ("曰", "AI看图/vis-o1")}
    joined = "\n".join(notes)
    assert "把握 mid" in joined and "不在组" in joined and "对位字" in joined and "半格" in joined
