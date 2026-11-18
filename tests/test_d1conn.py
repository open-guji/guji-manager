"""中心库 D1 连接垫片：Postgres 写法翻译、事务攒写＋守卫、分段提交、进度表函数（2026-11-18 迁 D1）。"""
from __future__ import annotations

import json

import pytest

from guji_manager.datastore import d1conn, d1sql
from guji_manager.datastore.d1conn import Conn, SqliteBackend


def test_translate():
    q, p = d1sql.translate("SELECT id FROM events WHERE ws = %s AND id = ANY(%s) AND x::text LIKE 'a%%'", ("w", ["a", "b"]))
    assert q == "SELECT id FROM events WHERE ws = ? AND id IN (SELECT value FROM json_each(?)) AND x LIKE 'a%'"
    assert p == ["w", '["a", "b"]']
    q, _ = d1sql.translate("UPDATE progress.volume SET updated_at = now() WHERE note ILIKE %s", ["x"])
    assert q == f"UPDATE progress_volume SET updated_at = {d1sql.NOW} WHERE note LIKE ?"
    assert "'::text'" in d1sql.translate("SELECT '::text' AS s")[0]          # 字符串里的不动
    assert d1sql.translate("SELECT raw || E'\\n' FROM t")[0] == "SELECT raw || char(10) FROM t"
    assert "sqlite_master" in d1sql.translate("SELECT to_regclass(%s)", ["changes"])[0]
    for bad in ("SELECT encode(sha256(convert_to(raw, 'UTF8')), 'hex') FROM t",
                "SELECT nextval('changes_rev_seq')", "SELECT DISTINCT ON (a) a FROM t"):
        with pytest.raises(d1sql.Untranslatable):
            d1sql.translate(bad)
    assert d1sql.is_noop("LOCK TABLE changes IN EXCLUSIVE MODE")
    assert d1sql.is_write("WITH x AS (SELECT 1) DELETE FROM t") and not d1sql.is_write("SELECT 'DELETE'")


def test_transaction_buffers_and_guard_stale():
    c = Conn(SqliteBackend())
    with c.transaction():
        c.execute("INSERT INTO db_meta (key, value) VALUES (%s, %s)", ("a", "1"))
        assert c.execute("SELECT count(*) FROM db_meta").fetchone() == (0,)     # 攒着，没提交
    assert c.execute("SELECT count(*) FROM db_meta").fetchone() == (1,)
    with c.transaction():
        c.execute("INSERT INTO db_meta (key, value) VALUES ('b', '2')")
        raise d1conn.Rollback()
    assert c.execute("SELECT count(*) FROM db_meta").fetchone() == (1,)
    # 守卫：进事务后别人写了 imports → 整批不写
    with pytest.raises(d1conn.Stale):
        with c.transaction(guard=True):
            assert c.heads() == (0, 0)
            c.execute("INSERT INTO db_meta (key, value) VALUES ('c', '3')")
            c.backend.db.execute("INSERT INTO imports (import_id, source) VALUES (1, 'x')")
    assert c.execute("SELECT key FROM db_meta ORDER BY key").fetchall() == [("a",)]
    with pytest.raises(d1sql.Untranslatable):
        with c.transaction():
            c.execute("INSERT INTO db_meta (key, value) VALUES ('d', '4') RETURNING key")


def test_copy_and_chunked_groups(monkeypatch):
    monkeypatch.setattr(d1conn, "CHUNK_STMTS", 3)
    c = Conn(SqliteBackend())
    calls = []
    real = c.backend.batch
    monkeypatch.setattr(c.backend, "batch", lambda st, g=None: calls.append(len(st)) or real(st, g))
    with c.transaction():
        cur = c.cursor()
        with cur.copy("COPY db_meta (key, value) FROM STDIN") as cp:
            for i in range(5):
                cp.write_row((f"k{i}", json.dumps({"i": i})))
        c.add_group([("INSERT INTO db_meta (key, value) VALUES ('g1', 'x')", []),
                     ("INSERT INTO db_meta (key, value) VALUES ('g2', 'x')", [])])
        c.add_group([("INSERT INTO db_meta (key, value) VALUES ('g3', 'x')", [])])
    assert calls == [1, 2] or sum(calls) == 4 and max(calls) <= 3                # 一组不拆开
    assert c.execute("SELECT count(*) FROM db_meta").fetchone() == (8,)


def test_progress_functions():
    c = Conn(SqliteBackend())
    c.execute("INSERT INTO progress_section (section, title) VALUES ('jobs', '重跑任务')")
    w = c.execute("SELECT progress.put_volume(%s, %s, %s::jsonb, %s)",
                  ("b", "005", json.dumps({"extra": {"a": 1}, "stage": "rough"}), "A31")).fetchone()[0]
    assert sorted(w) == ["extra", "stage"]
    from guji_manager.datastore.progress import put_volume
    assert put_volume(c, "b", "005", {"stage": "fine", "extra": {"b": 2}}, "site", soft=True) == ["extra"]
    with pytest.raises(ValueError, match="不认识"):
        put_volume(c, "b", "005", {"nope": 1}, "A31")
    row = c.execute("SELECT stage, extra, field_meta FROM progress_volume").fetchone()
    assert row[0] == "rough" and row[1] == {"a": 1, "b": 2} and row[2]["stage"]["by"] == "A31"
    c.execute("SELECT progress.put_metric('', '', %s, %s, %s, NULL, '%%', %s, %s, %s::jsonb, 10)",
              ("jobs", "k.x", "重跑", "A30", "t", json.dumps({"t": 1})))
    assert c.execute("SELECT unit, detail, sort FROM progress_metric").fetchone() == ("%", {"t": 1}, 10)
