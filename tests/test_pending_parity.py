from __future__ import annotations

import json
import sqlite3

from guji_manager import cli_parity as P


def test_vol_key_normalises_forms():
    assert {P.vol_key(x) for x in ("01", "001", "vol01", "1")} == {"1"}
    assert P.vol_key("abc") == "abc"


def test_compare_reports_only_mismatches_with_sign():
    db = {("b", "1"): 5, ("b", "2"): 3, ("c", "1"): 1}
    site = {("b", "1"): 5, ("b", "2"): 2, ("d", "1"): 4}
    rows = P.compare(db, site)
    assert [(r["book"], r["vol"], r["diff"]) for r in rows] == [("b", "2", 1), ("c", "1", 1), ("d", "1", -4)]


def test_db_open_counts_merges_vol_spellings():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE pending_current (book TEXT, vol TEXT, state TEXT)")
    conn.executemany("INSERT INTO pending_current VALUES (?,?,?)",
                     [("b", "01", "open"), ("b", "001", "open"), ("b", "2", "resolved"), ("c", "1", "open")])
    assert P.db_open_counts(conn) == {("b", "1"): 2, ("c", "1"): 1}
    assert P.db_open_counts(conn, ["c"]) == {("c", "1"): 1}


def test_site_counts_skips_zero(monkeypatch):
    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"counts": {"001": 4, "002": 0}}).encode()
    monkeypatch.setattr(P.urllib.request, "urlopen", lambda req, timeout=0: R())
    assert P.site_counts("https://x", ["b"]) == {("b", "1"): 4}
