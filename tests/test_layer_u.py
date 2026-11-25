"""book-text 伴生层按字格永久编号 u 对格（punct／entity v0.4 以 u 为准）：出单句、收口锚点、写回、换包后续挪锚。"""
from guji_manager.closeout.derive import invalid_anchors
from guji_manager.closeout.writeback import apply_fixes
from guji_manager.formats import layer_u as L
from guji_manager.review.sent_export import sent_export
from guji_manager.swap import booktext as bt


def _char(s, us=None):
    """第 1 页第 1 列；us 给了就每格带 u（char v0.6）。"""
    cells = [{"a": f"1:1:{i + 1}", "c": ch} for i, ch in enumerate(s)]
    if us is not None:
        for c, u in zip(cells, us):
            c["u"] = u
    d = {"pages": [{"page": 1, "columns": [{"col": 1, "cells": cells}]}]}
    if us is not None:
        d["u_max"] = max(us)
    return d


def test_lookup_prefers_u_and_falls_back_without_u():
    ch = _char("甲乙丙", us=[10, 11, 12])
    u2a = L.u_to_a(ch)
    assert L.punct_cell({"anchor": "1:1:1", "u": 12}, u2a) == "1:1:3"       # 以 u 为准
    assert L.punct_cell({"anchor": "1:1:1", "u": 99}, u2a) is None          # u 不在 char：不回退格位 key
    assert L.punct_cell({"anchor": "1:1:1"}, u2a) == "1:1:1"                # 条目没 u：按 key
    assert L.punct_cell({"a": "1:1:2", "u": 10}, u2a) == "1:1:1"            # norm 条目键 a
    assert L.punct_cell({"anchor": "1:1:1", "u": 12}, {}) == "1:1:1"        # char 没上 u：按 key
    assert L.entity_cells({"anchor": {"start": "1:1:1", "end": "1:1:1"}, "u_start": 11, "u_end": 12}, u2a) == ("1:1:2", "1:1:3")


def test_sent_export_reads_marks_by_u():
    ch = _char("甲乙丙丁", us=[1, 2, 3, 4])
    # 格位 key 过期（指第 1 格），u 指第 2 格：句号应落在「乙」后
    pj = {"punctuations": [{"mark": "。", "pos": "after", "anchor": "1:1:1", "u": 2},
                           {"mark": "。", "pos": "after", "anchor": "1:1:4", "u": 4}]}
    ej = {"entities": [{"id": "e1", "type": "people", "text": "丙丁", "anchor": {"start": "1:1:1", "end": "1:1:2"},
                        "u_start": 3, "u_end": 4, "target": {"status": "new_candidate"}}]}
    r = sent_export(ch, pj, ej)
    assert [s["t"] for s in r] == ["甲乙", "丙丁"]
    assert any(m["kind"] == "entity" and (m["start"], m["end"]) == (0, 2) for m in r[1]["marks"])


def test_invalid_anchors_by_u():
    ch = _char("甲乙丙", us=[1, 2, 3])
    pj = {"punctuations": [{"mark": "，", "pos": "after", "anchor": "1:1:1", "u": 2, "pre_char": "乙"},   # key 旧、u 对：不报
                           {"mark": "，", "pos": "after", "anchor": "1:1:3", "u": 7, "pre_char": "丙"},   # u 没了：报
                           {"mark": "，", "pos": "after", "anchor": "1:1:3", "u": 3, "pre_char": "丁"}]}  # 校验字不符
    out = invalid_anchors(ch, pj, None)
    assert [(o[1], o[3]) for o in out] == [("#1", "1:1:3"), ("#2", "1:1:3")]
    assert "u=7" in out[0][-1] and "校验字不符" in out[1][-1]
    ej = {"entities": [{"id": "e1", "text": "甲乙", "anchor": {"start": "1:1:2", "end": "1:1:3"}, "u_start": 1, "u_end": 2}]}
    assert invalid_anchors(ch, None, ej) == []


def test_writeback_restamps_u():
    ch = _char("甲乙丙", us=[5, 6, 7])
    pj = {"punctuations": [{"mark": "，", "anchor": "1:1:1", "u": 5, "pre_char": "乙"}]}
    assert apply_fixes(pj, ch, [{"idx": 0, "old": "1:1:1", "new": "1:1:2", "pre_char": "乙"}]) == 1
    assert pj["punctuations"][0]["anchor"] == "1:1:2" and pj["punctuations"][0]["u"] == 6


def test_restamp_moved_and_no_u_char_untouched():
    a2u = L.a_to_u(_char("甲乙", us=[3, 4]))
    before = {"punctuations": [{"anchor": "1:1:1", "u": 1}, {"anchor": "1:1:2", "u": 4}]}
    after = {"punctuations": [{"anchor": "1:1:2", "u": 1}, {"anchor": "1:1:2", "u": 4}]}
    assert L.restamp_moved(before, after, "punct", a2u) == 1 and after["punctuations"][0]["u"] == 4
    e0 = {"entities": [{"id": "x", "anchor": {"start": "1:1:1", "end": "1:1:1"}, "u_start": 3, "u_end": 3}]}
    e1 = {"entities": [{"id": "x", "anchor": {"start": "1:1:1", "end": "1:1:2"}, "u_start": 3, "u_end": 3}]}
    assert L.restamp_moved(e0, e1, "entity", a2u) == 1 and e1["entities"][0]["u_end"] == 4
    p = {"anchor": "1:1:2"}
    L.restamp_punct(p, a2u)                     # 条目没 u（旧文件）：不加字段
    assert "u" not in p
    q = {"anchor": "1:1:2", "u": 1}
    L.restamp_punct(q, {})                      # char 没上 u：不动
    assert q["u"] == 1


def test_swap_post_steps_restamp_u():
    new_c = _char("論語孟子集", us=[1, 2, 6, 3, 4])
    rows = [dict(old="1:1:1", new="1:1:1", kind="同格"), dict(old="1:1:2", new="1:1:2", kind="同格"),
            dict(old="1:1:3", new="1:1:4", kind="改号"), dict(old="", new="1:1:3", kind="新增")]
    ent = {"entities": [{"id": "e1", "type": "work", "text": "語子", "anchor": {"start": "1:1:2", "end": "1:1:3"},
                         "u_start": 2, "u_end": 3, "target": {"status": "new_candidate"}}]}
    rep = [("entity", "e1", "1:1:2～1:1:3", "1:1:2～1:1:4", "語子", "ANCHOR_MISS｜新格不连续或长度变了（語孟子）")]
    bt._grow_spans(ent, new_c, rows, rep)
    e = ent["entities"][0]
    assert e["anchor"] == {"start": "1:1:2", "end": "1:1:4"} and (e["u_start"], e["u_end"]) == (2, 3)


def test_break_follows_heading_restamps_u_and_sorts_without_offsets():
    new_c = _char("甲乙丙丁戊", us=[1, 6, 7, 2, 3])
    rows = [dict(old="1:1:1", new="1:1:1", kind="同格"), dict(old="", new="1:1:2", kind="新增"),
            dict(old="", new="1:1:3", kind="新增"), dict(old="1:1:2", new="1:1:4", kind="改号"),
            dict(old="1:1:3", new="1:1:5", kind="改号")]
    p = {"punctuations": [{"anchor": "1:1:1", "kind": "break", "pos": "after", "pre_char": "甲", "u": 1},
                          {"anchor": "1:1:4", "kind": "heading", "pos": "before", "u": 2},
                          {"anchor": "1:1:5", "kind": "point", "mark": "。", "pos": "after", "u": 3}]}
    out = bt._breaks_follow_headings(p, new_c, rows)
    pm = p["punctuations"]
    assert out == [("1:1:1", "1:1:3")]
    assert pm[0]["anchor"] == "1:1:3" and pm[0]["u"] == 7
    assert [x["kind"] for x in pm] == ["break", "heading", "point"]      # 没有 char_offset 也按读序，不把 before 全挪前
