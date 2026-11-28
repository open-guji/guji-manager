"""pending-stats 读待审条目表（11-28 整张单撤后）：open 条目＝待审，已有落定事件的格扣掉；`--from-dir` 读网站 /api/pending 存下的单。"""
import json
import sqlite3
from pathlib import Path

import pytest

from guji_manager import pending_stats


def _db():
    con = sqlite3.connect(":memory:")
    con.executescript((Path(pending_stats.__file__).parent / "datastore" / "schema_d1.sql").read_text(encoding="utf-8"))
    con.execute("PRAGMA foreign_keys = OFF")
    return con


def _item(con, iid, vol, cell, u, state="open", line=1, doc=None):
    raw = {"u": u, "doc": doc or {"pending_reason": "hard_pair", "ref": {"c": "曰"}}}
    con.execute("INSERT INTO pending_items (ws, src_path, src_line, item_id, ver, book, vol, cell, state, at, raw, rev) "
                "VALUES ('w', 'p/001.items.jsonl', ?, ?, 1, 'bk', ?, ?, ?, '2026-11-01', ?, 1)",
                (line, iid, vol, cell, state, json.dumps(raw, ensure_ascii=False)))


def _event(con, eid, u, key, level="human"):
    con.execute("INSERT INTO events (ws, src_path, id, stream, book, kind, actor, ts, payload, target, src_line, raw, rev) "
                "VALUES ('w', 'e.jsonl', ?, 'events', 'bk', 'confirm', 'user', '2026-11-27T00:00:00Z', ?, ?, 1, '{}', 1)",
                (eid, json.dumps({"v": "confirm", "level": level}), json.dumps({"unit": "cell", "key": key, "anchor": {"u": u}})))


def test_load_items_subtracts_settled(monkeypatch):
    con = _db()
    _item(con, "pi_a", "vol01", "1:1:1", 11, line=1)
    _item(con, "pi_b", "vol01", "1:1:2", 12, line=2)
    _item(con, "pi_c", "vol02", "3:1:1", 21, line=3)
    _item(con, "pi_d", "vol01", "1:1:3", 13, state="resolved", line=4)
    _event(con, "ev1", 12, "vol01:1:1:2")
    monkeypatch.setattr("guji_manager.dbconfig.apply_env", lambda: None)
    monkeypatch.setattr("guji_manager.datastore.connect.connect", lambda *a, **k: con)
    allopen = pending_stats.load_items("w", "bk", None, settled=False)
    assert sum(len(d["cells"]) for d in allopen.values()) == 3
    assert list(pending_stats.load_items("w", "bk", {2}, settled=False)) == ["002"]
    pytest.importorskip("open_guji_cv")      # 扣落定走 settle_sync，包 manager.feedback，要装 cv
    lists = pending_stats.load_items("w", "bk", None)
    assert {v: [c["u"] for c in d["cells"]] for v, d in lists.items()} == {"001": [11], "002": [21]}
    assert lists["001"]["cells"][0]["pending_reason"] == "hard_pair"


def test_from_dir_web_sheet(tmp_path, monkeypatch):
    monkeypatch.setattr(pending_stats, "_group_of", lambda ch: None)
    sheet = {"found": True, "cells": [{"cell": "7:1:13", "c": "子", "review": "pending", "id": "pi_x", "ver": 2, "u": 946,
                                       "pending_reason": "hard_pair", "pending_reason_cause": "Z"}], "live": {"hidden": 3, "of": 4}}
    (tmp_path / "044.pending.json").write_text(json.dumps(sheet, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "out"
    assert pending_stats.main(["--from-dir", str(tmp_path), "--out", str(out)]) == 0
    assert json.loads((out / "summary.json").read_text(encoding="utf-8"))["n"] == 1
