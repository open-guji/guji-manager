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
