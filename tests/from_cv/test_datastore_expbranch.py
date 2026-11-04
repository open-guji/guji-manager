"""中心库实验分支：GUJI_DATA_BRANCH 换数据目录、glyph.db、products；push／sync 连该分支；diff；图回落实验桶。"""

from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from test_datastore_pg import DSN, conn, repo  # noqa: F401  (fixtures)

# 用到 Postgres 的用例跟 test_datastore_pg 同口径：没给测试库就跳过（装了 psycopg 也一样）
_needs_pg = pytest.mark.skipif(not DSN, reason="没有 GUJI_TEST_PG_DSN（测试用 Postgres）")

EXP = "exp/GUJI-612-try"


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home"))
    for k in ("GUJI_WORKSPACE", "GUJI_GLYPH_DB", "GUJI_PRODUCTS_DIR", "GUJI_DATA_BRANCH", "GUJI_GLYPH_STORE"):
        monkeypatch.delenv(k, raising=False)


def _ws(tmp_path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / ".central.json").write_text('{"ws": "tws", "branch": "main"}')
    (ws / "workspace.yaml").write_text("id: tws\n")
    return ws


def test_write_branch_rules_and_endpoint_lookup(monkeypatch):
    from guji_manager import cli_db
    from guji_manager.datastore import connect, neonapi
    with pytest.raises(SystemExit, match="不能写 ci"):
        cli_db._check_write_branch("ci")
    with pytest.raises(SystemExit, match="不能写"):
        cli_db._check_write_branch("exp/foo")
    cli_db._check_write_branch(EXP)
    assert cli_db._bucket("main") == "main" and cli_db._bucket(EXP) == "exp"

    calls = []
    monkeypatch.setattr(neonapi, "_get", lambda path: {
        "branches": [{"name": "main", "id": "br-m"}, {"name": EXP, "id": "br-x"}],
        "endpoints": [{"id": "ep-m", "branch_id": "br-m", "type": "read_write"},
                      {"id": "ep-x", "branch_id": "br-x", "type": "read_write"}],
    })
    monkeypatch.setattr(connect, "connect", lambda endpoint=None: calls.append(endpoint) or "conn")
    assert cli_db._pg_conn(EXP) == "conn" and calls == ["ep-x"]
    monkeypatch.setenv("GUJI_DATA_BRANCH", EXP)
    cli_db._pg_conn()
    assert calls[-1] == "ep-x"
    with pytest.raises(SystemExit, match="没有分支"):
        neonapi.branch_endpoint("exp/GUJI-1-none")


class _Src:
    def __init__(self, branch, files, events, rev):
        self.branch, self._files, self._events, self._rev = branch, files, events, rev

    def status(self):
        return self._rev

    def rows(self, table, ws=None, **kw):
        if table == "source_files":
            return iter([{"src_path": p, "sha256": s, "n_lines": n} for p, (s, n) in self._files.items()])
        if table == "events":
            return iter([{"id": i} for i in self._events])
        return iter([])


def test_cli_branch_flag_sets_env(tmp_path, monkeypatch):
    import argparse

    from guji_manager import cli_db
    ws = _ws(tmp_path)
    seen = {}
    monkeypatch.setattr(cli_db, "push_workspace", lambda d, **kw: seen.update(
        branch=__import__("os").environ.get("GUJI_DATA_BRANCH")) or {})
    sub = argparse.ArgumentParser().add_subparsers(dest="cmd")
    cli_db.add_parser(sub)
    args = sub.choices["db"].parse_args(["push", "-w", str(ws), "--branch", EXP])
    monkeypatch.setenv("GUJI_DATA_TOKEN", "t")
    monkeypatch.setenv("GUJI_DATA_BRANCH", "")              # cmd_db 会改它；让 monkeypatch 收尾时还原
    cli_db.cmd_db(args)
    assert seen["branch"] == EXP


