"""中心库测试夹具（2026-11-18 中心库迁 D1：库换成本机 SQLite，建表同 D1；不再要 GUJI_TEST_PG_DSN）。

同名覆盖 cv tests/datastore/pg_fixtures.py（本目录排在 cv 测试目录之前）。
"""
from __future__ import annotations

import json
import os
import subprocess

import pytest

DSN = "sqlite"      # 老测试拿它判断「有没有测试库」：本机 SQLite 总是有


def _line(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False, sort_keys=True)


def _git(repo, *args) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _commit(repo, files: dict[str, bytes | None], msg: str) -> str:
    for rel, data in files.items():
        p = repo / rel
        if data is None:
            p.unlink()
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "ws-repo"
    r.mkdir()
    _git(r, "init", "-q")
    return r


@pytest.fixture
def conn():
    from guji_manager.datastore.d1conn import Conn, SqliteBackend
    c = Conn(SqliteBackend())
    try:
        yield c
    finally:
        c.close()


def _base() -> dict[str, bytes]:
    ev = lambda i, v: _line(id=f"evt_b_{i}", batch="b", seq=i, kind="confirm", actor="user",
                            payload={"v": v}, target={"book": "vol03"}, ts="t")
    inst = _line(instance_id="v2:vol03:1:1:1", source_id="v2", page="1", col=1, idx=1,
                 label="曰", semantic="曰", updated_at="t")
    return {
        "W/workspace.yaml": b"id: tws\n",
        "W/books/vol03.yaml": "id: vol03\ntitle: 卷三\n".encode(),
        "W/feedback/events/b.jsonl": (ev(1, "師") + "\n" + ev(2, "所") + "\n").encode(),
        "W/feedback/consumed/glyphdb_admit.jsonl": (
            (_line(event="evt_b_1", ts="t", note="b") + "\n") * 2).encode(),
        "W/feedback/lists/x.txt": b"vol03:1:1:1\n",
        "W/output/glyph_store/glyphs.jsonl": (_line(
            edition_tag="e", char="曰", status="sparse", n_confirmed=1, updated_at="t") + "\n"
        ).encode(),
        "W/output/glyph_store/approx_clears.jsonl": b"",
        "W/output/glyph_store/instances/v2.jsonl": (inst + "\n").encode(),
        "W/output/glyph_store/patches/v2_vol03_1_1_1.png": b"\x89PNG one",
        "W/other/page.png": b"out of scope, never read",
    }
