"""guji seg pin 的纯编辑函数（seg_pin.apply_edit／slot_map／make_item）。"""
from __future__ import annotations

import pytest

from guji_manager import seg_pin as sp

CX = (2.0, 98.0)


def _col(*spans):
    return [{"slot": i, "sub": None, "kind": "char", "x0": 2.0, "x1": 98.0, "y0": float(a), "y1": float(b)}
            for i, (a, b) in enumerate(spans, 1)]


def _ys(cells):
    return [(c["slot"], c["y0"], c["y1"]) for c in cells]


def test_split_renumbers():
    out = sp.apply_edit(_col((0, 100), (100, 220), (220, 300)), ("split", "2@160"), CX)
    assert _ys(out) == [(1, 0, 100), (2, 100, 160), (3, 160, 220), (4, 220, 300)]


def test_merge_union():
    out = sp.apply_edit(_col((0, 100), (100, 150), (150, 220), (220, 300)), ("merge", "2-3"), CX)
    assert _ys(out) == [(1, 0, 100), (2, 100, 220), (3, 220, 300)]


def test_insert_after_and_front_and_delete():
    c = _col((50, 100), (100, 200))
    assert _ys(sp.apply_edit(c, ("insert-after", "1@100:150"), CX))[1] == (2, 100, 150)
    assert _ys(sp.apply_edit(c, ("insert-after", "0@0:50"), CX))[0] == (1, 0, 50)
    assert _ys(sp.apply_edit(c, ("delete", "1"), CX)) == [(1, 100, 200)]


def test_move_and_ys():
    out = sp.apply_edit(_col((0, 100), (100, 200)), ("move", "1.y1=95"), CX)
    assert out[0]["y1"] == 95.0
    out = sp.apply_edit([], ("ys", "10,100,190"), CX)
    assert _ys(out) == [(1, 10, 100), (2, 100, 190)] and out[0]["x0"] == 2.0 and out[0]["x1"] == 98.0


def test_jiazhu_kept_together_and_split_refused():
    cells = _col((0, 100)) + [
        {"slot": 2, "sub": "a", "kind": "jiazhu_a", "x0": 50.0, "x1": 98.0, "y0": 100.0, "y1": 150.0},
        {"slot": 2, "sub": "b", "kind": "jiazhu_b", "x0": 2.0, "x1": 50.0, "y0": 100.0, "y1": 150.0}]
    out = sp.apply_edit(cells, ("delete", "1"), CX)
    assert [(c["slot"], c["sub"]) for c in out] == [(1, "a"), (1, "b")]
    with pytest.raises(sp.PinError):
        sp.apply_edit(cells, ("split", "2@120"), CX)
    with pytest.raises(sp.PinError):
        sp.apply_edit(cells, ("merge", "1-2"), CX)


def test_bad_inputs():
    c = _col((0, 100))
    for e in (("split", "1@150"), ("split", "9@50"), ("ys", "10,5"), ("move", "1.z=3"), ("move", "1.y1=-5")):
        with pytest.raises(sp.PinError):
            sp.apply_edit(c, e, CX)


def test_slot_map():
    before = _col((0, 100), (100, 220), (220, 300))
    after = sp.apply_edit(before, ("split", "2@160"), CX)
    rows = sp.slot_map(before, after)
    assert (1, 1, "同") in rows and (3, 4, "改号") in rows and (2, 2, "改框") in rows and any(r[2] == "新增" for r in rows)


def test_make_item_keeps_history():
    d = sp.Draft("vol01", 88, 4, _col((0, 100)), CX, "row_segment")
    it = sp.make_item(d, "拆閣領")
    assert it["id"] == "vol01:88:4" and it["history"][0]["change"] == "created" and it["status"] == "active"
    it2 = sp.make_item(d, "再改", prev=it)
    assert [h["change"] for h in it2["history"]] == ["created", "updated"]


def test_write_item_replaces_same_id(tmp_path):
    p = tmp_path / "items.jsonl"
    d = sp.Draft("vol01", 88, 4, _col((0, 100)), CX, "row_segment")
    other = dict(sp.make_item(sp.Draft("vol01", 88, 5, _col((0, 50)), CX, "row_segment"), "x"))
    sp.write_item(p, other)
    sp.write_item(p, sp.make_item(d, "一"))
    sp.write_item(p, sp.make_item(d, "二"))
    rows = sp.read_items(p)
    assert [r["id"] for r in rows] == ["vol01:88:5", "vol01:88:4"]
    assert rows[1]["history"][-1]["why"] == "二"
