"""待审条目逐行进 pending_items 表（GM4 11-26，待审与裁定整理方案第 4 步）。"""

from __future__ import annotations

import json
import subprocess

import pytest


def _line(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False, sort_keys=True)


def _git(repo, *args) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _commit(repo, files: dict[str, bytes], msg: str) -> str:
    for rel, data in files.items():
        p = repo / rel
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
    ev = _line(id="evt_b_1", batch="b", seq=1, kind="confirm", actor="user", payload={"v": "師"},
               target={"book": "vol03"}, ts="t")
    return {"W/workspace.yaml": b"id: tws\n", "W/books/vol03.yaml": "id: vol03\n".encode(),
            "W/feedback/events/b.jsonl": (ev + "\n").encode(), "W/feedback/lists/x.txt": b"vol03:1:1:1\n"}

PEND = "W/feedback/lists/pending/vol03/001.items.jsonl"


def _item(i, ver, state, **kw):
    return _line(id=f"pi_{i}", ver=ver, state=state, op="open" if ver == 1 else "close", cell=f"1:1:{i}",
                 at="t", by="x", src="rev:r1", fp="", doc={"recheck": i == 2}, **kw)


def _files():
    f = _base()
    f[PEND] = "\n".join([_item(1, 1, "open", u=7), _item(2, 1, "open"), _item(1, 2, "closed", u=7),
                         _item(1, 2, "closed", u=7, why="另一台机器同 ver 追加")]).encode() + b"\n"
    return f


def test_classify_pending_items():
    from guji_manager.datastore.scope import classify
    assert classify("feedback/lists/pending/vol03/001.items.jsonl") == "pending_items"
    assert classify("feedback/lists/pending/vol03/001.pending.json") == "files"
    assert classify("feedback/lists/pending/001.items.jsonl") == "files"        # 层级不对的照旧整文件
    assert classify("feedback/lists/proofing/vol03/001.pending.json") == "list_rows"    # 整张待审单（11-26 起）


def test_import_rows_current_view_and_verify(repo, conn):
    from guji_manager.datastore.importer import import_commit
    from guji_manager.datastore.verify import verify_commit

    c1 = _commit(repo, _files(), "c1")
    rep = import_commit(conn, repo, c1)
    assert rep.per_table["pending_items"]["insert"] == 4
    assert conn.execute("SELECT count(*) FROM files WHERE src_path LIKE 'feedback/lists/pending/%'").fetchone()[0] == 0
    rows = conn.execute("SELECT item_id, ver, book, vol, state, actor, recheck, u FROM pending_items ORDER BY src_line").fetchall()
    assert [tuple(r) for r in rows] == [("pi_1", 1, "vol03", "001", "open", "x", 0, 7),
                                        ("pi_2", 1, "vol03", "001", "open", "x", 1, None),
                                        ("pi_1", 2, "vol03", "001", "closed", "x", 0, 7),
                                        ("pi_1", 2, "vol03", "001", "closed", "x", 0, 7)]
    cur = conn.execute("SELECT item_id, src_line, state FROM pending_current ORDER BY item_id").fetchall()
    assert [tuple(r) for r in cur] == [("pi_1", 3, "closed"), ("pi_2", 1, "open")]
    assert verify_commit(conn, repo, c1)["ok"]

    # 追加一个版本：只多一行
    f = _files()
    f[PEND] += (_item(2, 2, "closed") + "\n").encode()
    c2 = _commit(repo, f, "c2")
    rep2 = import_commit(conn, repo, c2)
    assert rep2.per_table["pending_items"] == {"rows": 5, "insert": 1, "update": 0, "delete": 0, "moved": 0}
    assert verify_commit(conn, repo, c2)["ok"]


def test_old_files_row_moves_to_pending_items(repo, conn, monkeypatch):
    """旧版 manager 推过的整文件行：新版推一次就从 files 挪到 pending_items。"""
    from guji_manager.datastore import scope
    from guji_manager.datastore.importer import import_commit
    from guji_manager.datastore.verify import verify_commit

    new = scope.classify
    monkeypatch.setattr(scope, "classify", lambda rel: "files" if rel.endswith(".items.jsonl") else new(rel))
    c1 = _commit(repo, _files(), "c1")
    import_commit(conn, repo, c1)
    assert conn.execute("SELECT count(*) FROM files WHERE src_path = ?", (PEND[2:],)).fetchone()[0] == 1
    monkeypatch.setattr(scope, "classify", new)
    c2 = _commit(repo, {**_files(), "W/feedback/lists/x.txt": b"touch\n"}, "c2")
    rep = import_commit(conn, repo, c2, allow_delete=True)
    assert rep.per_table["pending_items"]["insert"] == 4 and rep.per_table["files"]["delete"] == 1
    assert conn.execute("SELECT tbl FROM source_files WHERE src_path = ?", (PEND[2:],)).fetchone()[0] == "pending_items"
    assert verify_commit(conn, repo, c2)["ok"]
    assert json.loads(conn.execute("SELECT raw FROM pending_items WHERE src_line = 0").fetchone()[0])["id"] == "pi_1"


def test_materialize_restores_pending_file(repo, conn, tmp_path):
    """拉取：按 source_files.tbl 从 pending_items 逐行拼回，逐字节同原文件。"""
    from guji_manager.datastore.importer import import_commit
    from guji_manager.datastore.materialize import materialize
    from guji_manager.datastore.sqlsource import SqlSource

    f = _files()
    import_commit(conn, repo, _commit(repo, f, "c1"))
    out = tmp_path / "out"
    materialize(SqlSource(conn), "tws", out, prefixes=("feedback/lists/",), with_images=False)
    assert (out / PEND[2:]).read_bytes() == f[PEND]
    assert (out / "feedback/lists/x.txt").read_bytes() == f["W/feedback/lists/x.txt"]


# ---- list_rows（files 清退路线）----

LST = "W/feedback/lists/opinions/96mid1ogzk/opinions.jsonl"
FRZ = "W/feedback/lists/freeze/vol01.jsonl"


def _lists():
    f = _base()
    f[LST] = (_line(id="op_1", book="96mid1ogzk", u=5) + "\n\n" + _line(id="op_2", book="96mid1ogzk") + "\n").encode()
    f[FRZ] = (_line(book="vol01", pack="p1") + "\n").encode()
    f["W/feedback/lists/stale_verdicts.tsv"] = b"a\tb\n"
    f["W/feedback/lists/web/96mid1ogzk/bad.jsonl"] = b'{"a":1}\nnot json\n'
    return f


def test_classify_list_rows():
    from guji_manager.datastore.scope import classify
    assert classify("feedback/lists/opinions/96mid1ogzk/opinions.jsonl") == "list_rows"
    assert classify("feedback/lists/web/96mid1ogzk/items.jsonl") == "list_rows"
    assert classify("feedback/lists/freeze/vol01.jsonl") == "list_rows"
    assert classify("feedback/lists/u_void/vol02.jsonl") == "list_rows"
    assert classify("feedback/lists/opinions/96mid1ogzk/text_versions.json") == "files"
    assert classify("feedback/lists/stale_verdicts.tsv") == "files"
    assert classify("feedback/lists/proofing/vol03/001.pending.json") == "list_rows"    # 整张待审单（11-26 起）


def test_list_rows_import_verify_and_materialize(repo, conn, tmp_path):
    from guji_manager.datastore.importer import import_commit
    from guji_manager.datastore.materialize import materialize
    from guji_manager.datastore.sqlsource import SqlSource
    from guji_manager.datastore.verify import verify_commit

    f = _lists()
    c1 = _commit(repo, f, "c1")
    rep = import_commit(conn, repo, c1)
    assert rep.per_table["list_rows"]["insert"] == 3          # 空行不入库；坏 json 的文件整份进 files
    rows = conn.execute("SELECT dataset, book, name, id, u FROM list_rows ORDER BY src_path, src_line").fetchall()
    assert [tuple(r) for r in rows] == [("freeze", None, "vol01", None, None),
                                        ("opinions", "96mid1ogzk", "opinions", "op_1", 5),
                                        ("opinions", "96mid1ogzk", "opinions", "op_2", None)]
    left = {r[0] for r in conn.execute("SELECT src_path FROM files WHERE kind = 'list'")}
    assert left == {"feedback/lists/stale_verdicts.tsv", "feedback/lists/web/96mid1ogzk/bad.jsonl", "feedback/lists/x.txt"}
    assert verify_commit(conn, repo, c1)["ok"]
    out = tmp_path / "out"
    materialize(SqlSource(conn), "tws", out, prefixes=("feedback/lists/",), with_images=False)
    for rel in (LST, FRZ, "W/feedback/lists/web/96mid1ogzk/bad.jsonl"):
        assert (out / rel[2:]).read_bytes() == f[rel]         # 含空行、逐字节


def test_proofing_sheet_rows_and_oversize(repo, conn, tmp_path):
    """整张待审单一行一个 json 对象进 list_rows；一行超过 D1 单行上限的退回 files（11-26）。"""
    from guji_manager.datastore import scope
    from guji_manager.datastore.importer import import_commit
    from guji_manager.datastore.materialize import materialize
    from guji_manager.datastore.sqlsource import SqlSource
    from guji_manager.datastore.verify import verify_commit

    f = _base()
    small = "W/feedback/lists/proofing/96mid1ogzk/001.pending.json"
    big = "W/feedback/lists/proofing/96mid1ogzk/002.pending.json"
    f[small] = (_line(rev=3, cells=[{"cell": "1:1:1", "id": "pi_1"}]) + "\n").encode()
    f[big] = (_line(rev=3, blob="x" * (scope.ROW_MAX_BYTES + 10)) + "\n").encode()
    c1 = _commit(repo, f, "c1")
    rep = import_commit(conn, repo, c1)
    assert rep.per_table["list_rows"]["insert"] == 1
    row = conn.execute("SELECT dataset, book, name FROM list_rows").fetchone()
    assert tuple(row) == ("proofing", "96mid1ogzk", "001.pending")
    tbls = dict(conn.execute("SELECT src_path, tbl FROM source_files WHERE src_path LIKE 'feedback/lists/proofing/%'").fetchall())
    assert tbls == {"feedback/lists/proofing/96mid1ogzk/001.pending.json": "list_rows",
                    "feedback/lists/proofing/96mid1ogzk/002.pending.json": "files"}
    # 超行上限的整份进 files（正文在 R2，测试替身读不回，只验其余文件不受影响）
    assert conn.execute("SELECT body_r2 FROM files WHERE src_path LIKE '%002.pending.json'").fetchone()[0] == 1
    bad = verify_commit(conn, repo, c1)["workspaces"]["tws"].get("mismatches") or []
    assert all("002.pending.json" in m for m in bad), bad
    out = tmp_path / "out"
    materialize(SqlSource(conn), "tws", out, prefixes=("feedback/lists/",), with_images=False)
    assert (out / small[2:]).read_bytes() == f[small]
