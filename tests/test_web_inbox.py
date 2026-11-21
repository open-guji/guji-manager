"""网站收件箱 web_inbox（A20 11-21）：--from-inbox 读到的票与 --from-kv 产出逐字节相同。"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from guji_manager import cli_cellvotes as C
from guji_manager.feedback import web_inbox as WI
from guji_manager.opinions import ingest as I

BOOK, REV = "sitebk01", "004-r3"


def vote(a, choice, char="", voter="v1", ts=1, rev=REV, **kw):
    return {"v": 1, "book": BOOK, "vol": "004", "a": a, "rev": rev, "choice": choice,
            **({"char": char} if char else {}), "note": "", "voter": voter, "ts": ts, **kw}


def rows_of(pairs, seq0=1):
    return [{"seq": seq0 + i, "kind": "cellreview", "key": k, "book": BOOK, "ts": v.get("ts", 0), "value": v}
            for i, (k, v) in enumerate(pairs)]


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_pages_and_falls_back_on_401(monkeypatch):
    monkeypatch.setenv("GUJI_DATA_TOKEN", "bad")
    monkeypatch.setenv("GUJI_DATA_TOKEN_READ", "good")
    monkeypatch.delenv("GUJI_DATA_TOKEN_PROD", raising=False)
    seen = []
    pages = {0: {"items": rows_of([("cr:i:x:1:a", {}), ("cr:i:x:2:a", {})]), "next": 2, "hasMore": True},
             2: {"items": rows_of([("cr:i:x:3:a", {})], seq0=3), "next": None, "hasMore": False}}

    def opener(req, timeout=0):
        tok = req.headers["Authorization"].split()[1]
        after = int(req.full_url.split("after=")[1].split("&")[0])
        seen.append((tok, after))
        if tok == "bad":
            raise urllib.error.HTTPError(req.full_url, 401, "no", {}, None)
        return _Resp(json.dumps(pages[after]).encode())
    rows, seq = WI.fetch("cellreview", BOOK, opener=opener, base="https://x")
    assert len(rows) == 3 and seq == 3
    assert seen == [("bad", 0), ("good", 0), ("bad", 2), ("good", 2)]


def test_key_filters_and_probe_ignored():
    rows = rows_of([("cr:i:sitebk01:pi_b:v1", {"n": 2}), ("cr:004-r3:sitebk01:1:1:1:v1", {"n": 3}),
                    ("cr:i:sitebk01:pi_a:v1", {"n": 1}), ("cr:004-r4:sitebk01:1:1:1:v1", {"n": 4}),
                    ("cr:i:other:pi_a:v1", {"n": 9}), ("probe:tmp", {"n": 0})])
    assert [v["n"] for v in WI.item_votes(rows, BOOK)] == [1, 2]
    assert [v["n"] for v in WI.rev_votes(rows, BOOK, REV)] == [3]
    assert {k: [v["n"] for v in vs] for k, vs in WI.rev_files(rows, BOOK).items()} == {"004-r3.jsonl": [3], "004-r4.jsonl": [4]}
    assert [v["n"] for v in WI.fix_values(rows_of([("cf:b", {"n": 2}), ("probe:x", {"n": 0}), ("cf:a", {"n": 1})]))] == [1, 2]


def _args(tmp_path, monkeypatch, out, **kw):
    import argparse
    ws = tmp_path / "ws"
    (ws / "feedback" / "events").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GUJI_WORKSPACE", str(ws))
    monkeypatch.setenv("TOK", "t")
    base = dict(book="vol04", site_book=BOOK, rev=REV, cord=None, no_box_check=True, tol=8.0, include_none=True,
                from_file=None, from_kv=False, from_inbox=False, token_env="TOK", source="测试", out=str(out),
                pack=None, sheet=None, items=False, allow_empty=False)
    return argparse.Namespace(**{**base, **kw})


def test_draft_from_inbox_byte_identical_to_kv(tmp_path, monkeypatch):
    kv = [vote("1:1:1", "char", "甲", ts=5), vote("1:1:2", "none", voter="v2", ts=3),
          vote("1:1:3", "char", "乙", ts=2), vote("1:1:3", "char", "丙", voter="v9", ts=4)]
    keyed = [(f"cr:{REV}:{BOOK}:{v['a']}:{v['voter']}", v) for v in kv]
    keyed.append((f"cr:004-r2:{BOOK}:1:1:1:v1", vote("1:1:1", "char", "丁", rev="004-r2")))   # 别的单，不读
    monkeypatch.setattr(C, "_fetch_kv", lambda *a, **k: kv)
    monkeypatch.setattr(C, "_fetch_kv_items", lambda *a, **k: [])
    monkeypatch.setattr(WI, "fetch", lambda *a, **k: (rows_of(reversed(keyed)), 9))
    C.cmd_draft(_args(tmp_path, monkeypatch, tmp_path / "kv", from_kv=True))
    C.cmd_draft(_args(tmp_path, monkeypatch, tmp_path / "ib", from_inbox=True))
    assert (tmp_path / "kv" / "drafts.jsonl").read_text(encoding="utf-8").count("\n") >= 2
    for f in ("drafts.jsonl", "held.tsv"):
        a, b = (tmp_path / "kv" / f), (tmp_path / "ib" / f)
        assert a.exists() == b.exists()
        if a.exists():
            assert a.read_bytes() == b.read_bytes(), f


def test_draft_rejects_both_sources(tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="只能选一个"):
        C.cmd_draft(_args(tmp_path, monkeypatch, tmp_path / "x", from_kv=True, from_inbox=True))


def test_allow_empty_accepts_inbox(tmp_path, monkeypatch):
    monkeypatch.setattr(WI, "fetch", lambda *a, **k: ([], 0))
    args = _args(tmp_path, monkeypatch, tmp_path / "e", from_inbox=True, allow_empty=True)
    C.cmd_draft(args)
    meta = json.loads((tmp_path / "e" / "meta.json").read_text(encoding="utf-8"))
    assert meta["n_votes"] == 0 and meta["empty_confirmed"]["by_item"] == 0


def test_opinions_read_inbox_same_as_snapshot():
    fix = {"v": 1, "kind": "char", "book_id": BOOK, "volume": "4", "text_version": "0.1.0", "cell_id": "1:1:1",
           "old_char": "甲", "new_char": "乙", "voter": "abcdef12", "ts": 1}
    cr = vote("1:1:1", "char", "甲")
    def fetch(kind, book, token_env=None):
        if kind == "charfix":
            return [{"seq": 1, "kind": "charfix", "key": "cf:x", "book": BOOK, "ts": 1, "value": fix}], 1
        return rows_of([(f"cr:{REV}:{BOOK}:1:1:1:v1", cr), (f"cr:i:{BOOK}:pi_a:v1", {"item": "pi_a"})]), 2
    ib = I.read_inbox(BOOK, fetch=fetch)
    snap = I.Sources(fixes=[fix], cellreview={f"{REV}.jsonl": [cr]})
    ids = lambda s: [(i.op.id, i.source) if i.op else i.drop for i in I.incoming(s, BOOK)]  # noqa: E731
    assert ids(ib) == ids(snap)


def test_diff_votes():
    a = [vote("1:1:1", "char", "甲"), vote("1:1:2", "none"), {"item": "pi_a", "voter": "v1", "choice": "char"}]
    b = [vote("1:1:1", "char", "乙"), {"item": "pi_a", "voter": "v1", "choice": "char"}, vote("1:1:3", "none")]
    d = WI.diff_votes(a, b)
    assert d == {"only_kv": [f"{REV}:1:1:2:v1"], "only_inbox": [f"{REV}:1:1:3:v1"], "differ": [f"{REV}:1:1:1:v1"]}
