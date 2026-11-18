"""回库事后核（`ops/lib_round_audit.py`）：两轮逐格比、只害不帮名单、读库里的回库字。"""
import json
import sqlite3

from guji_manager.ops import lib_round_audit as RA


def _sa(ch, admit):
    return {"char": ch, "admit": admit}


def _gm(*chars):
    return {"candidates": [[c, 0.99 - i * 0.01] for i, c in enumerate(chars)]}


def test_compare_harm_and_help():
    bf = {"蒍", "巿", "揄"}
    bsa = {"a": _sa("為", True), "b": _sa("市", True), "c": _sa("榆", True), "d": _sa("蒍", False),
           "e": _sa("揄", False), "f": _sa("之", True), "g": _sa("其", False), "x": _sa("以", True)}
    bgm = {"a": _gm("為", "爲"), "b": _gm("市", "布"), "c": _gm("榆", "揄"), "d": _gm("為"),
           "e": _gm("榆"), "f": _gm("之"), "g": _gm("甚", "其")}
    asa = {"a": _sa("為", False), "b": _sa("市", False), "c": _sa("榆", False), "d": _sa("蒍", True),
           "e": _sa("揄", True), "f": _sa("之", True), "g": _sa("其", True), "y": _sa("乎", True)}
    agm = {"a": _gm("蒍", "為"),             # 首位换成回库字：抢首位
           "b": _gm("市", "布", "巿"),        # 首位没变、前几名新进回库字
           "c": _gm("揄", "榆"),              # 首位前后都是 榆/揄 之一：前一轮 揄 已在前几 → 首位换成回库字仍算抢首位
           "d": _gm("蒍"), "e": _gm("揄"), "f": _gm("之"), "g": _gm("其")}
    r = RA.compare(bsa, bgm, asa, agm, bf)
    assert r["harm_top1"] == {"蒍": ["a"], "揄": ["c"]}
    assert r["harm_topn"] == {"巿": ["b"]}
    assert r["help"] == {"蒍": ["d"], "揄": ["e"]}            # g 新放行但不靠回库字
    assert r["stat"]["两轮都有"] == 7 and r["stat"]["新增待审"] == 3 and r["stat"]["新放行"] == 3
    assert RA.withdraw_list(r["harm_top1"], r["harm_topn"], r["help"]) == ["巿"]   # 蒍、揄 有帮，留


def test_backfill_chars_reads_live_auto_backfill(tmp_path):
    p = tmp_path / "g.db"
    c = sqlite3.connect(p)
    c.executescript("CREATE TABLE admissions(instance_id TEXT, char TEXT, provenance TEXT, evidence TEXT, admitted_at TEXT);"
                    "CREATE TABLE evictions(instance_id TEXT);")
    rows = [("v2:1", "蒍", "auto", {"backfill": True, "batch": "A"}),
            ("v2:2", "蒍", "auto", {"backfill": True, "batch": "B"}),
            ("v2:3", "巿", "auto", {"backfill": True, "batch": "A"}),     # 已撤
            ("v2:4", "為", "human", {"backfill": True}),                   # 人裁不算
            ("v2:5", "市", "auto", {"batch": "qtw-auto-thick"})]           # 不是回库
    c.executemany("INSERT INTO admissions VALUES (?,?,?,?,'')", [(a, b, d, json.dumps(e)) for a, b, d, e in rows])
    c.execute("INSERT INTO evictions VALUES ('v2:3')")
    c.commit()
    c.close()
    assert RA.backfill_chars(p) == {"蒍": ["v2:1", "v2:2"]}
    assert RA.backfill_chars(p, {"B"}) == {"蒍": ["v2:2"]}


def test_summary_flags_missing_books():
    rep = {"stat": {}, "backfill_chars": 2, "backfill_instances": 3, "help_cells": 0, "harm_chars": 1, "help_chars": 0,
           "withdraw": [{"char": "巿"}], "withdraw_instances": 1, "missing": ["07"]}
    s = RA.summary(rep)
    assert "要撤 1 字 1 例" in s and "缺产物没比的册：07" in s
