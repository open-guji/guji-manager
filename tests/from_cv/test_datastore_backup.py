"""中心库备份与恢复演练（GUJI-611）：导出 → 恢复到另一个库 → 逐表行数与哈希一致；改一行就对不上。
要 ``GUJI_TEST_PG_DSN``，不给就跳过；经 Worker 存取那段用假的存储。"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from test_datastore_pg import DSN, _commit, conn, repo  # noqa: F401  (fixtures)
from test_datastore_pull import _line, _workspace

pytestmark = pytest.mark.skipif(not DSN, reason="没有 GUJI_TEST_PG_DSN（测试用 Postgres）")


class _Store:
    """假的 /v1/backups。"""

    def __init__(self):
        self.objs: dict[tuple[str, str], bytes] = {}

    def put_backup(self, day, name, data, ct):
        self.objs[(day, name)] = data

    def list_backups(self):
        days = sorted({d for d, _ in self.objs})
        return [{"date": d, "files": sum(1 for k in self.objs if k[0] == d)} for d in days]

    def get_backup(self, day, name):
        if (day, name) not in self.objs:
            raise KeyError(name)
        return self.objs[(day, name)]

    def delete_backup(self, day):
        for k in [k for k in self.objs if k[0] == day]:
            del self.objs[k]


@pytest.fixture
def other():
    from guji_manager.datastore.d1conn import Conn, SqliteBackend
    c = Conn(SqliteBackend())
    try:
        yield c
    finally:
        c.close()


def test_backup_restore_roundtrip(repo, conn, other, tmp_path):  # noqa: F811
    from guji_manager.datastore import backup as B
    from guji_manager.datastore.importer import import_commit
    import_commit(conn, repo, _commit(repo, _workspace(tmp_path), "c1"))
    files, man = B.dump(conn)
    assert man["rev"] > 0 and man["tables"]["events"]["rows"] == 1
    assert man["tables"]["glyph_instances"]["rows"] > 0

    st = _Store()
    B.upload(st, "2026-10-19", files, man)
    st.put_backup("2026-10-01", "x.jsonl.gz", b"", "")                # 没有清单＝不完整
    assert B.complete_dates(st) == ["2026-10-19"]
    files2, man2 = B.fetch(st, "2026-10-19")

    other.execute("CREATE TABLE junk (x int)")                      # 目标库原有的东西不碍事
    B.restore(other, files2, man2)
    res = B.check(other, man2)
    assert res["ok"], res
    cur = other.cursor()
    cur.execute("SELECT coalesce(max(rev), 0) FROM changes")
    assert cur.fetchone()[0] == man["rev"]
    assert other.heads() == (man["rev"], man["import_id"])            # 号码接着往下走，不撞号

    other.execute("UPDATE events SET raw = raw || ' '")
    assert not B.check(other, man2)["ok"]

    assert B.prune(st, 10, today=date(2026, 10, 20)) == ["2026-10-01"]
    assert [d["date"] for d in st.list_backups()] == ["2026-10-19"]


def test_backup_catches_up_with_concurrent_write(repo, conn, tmp_path, monkeypatch):  # noqa: F811
    """导出途中有人写入：只补被改的表、changes/imports 只补新行，结果要和写完后整导一致。"""
    from guji_manager.datastore import backup as B
    from guji_manager.datastore.importer import import_commit
    ws = _workspace(tmp_path)
    import_commit(conn, repo, _commit(repo, ws, "c1"))
    real, fired = B._dump_rows, []

    def hooked(cur, t, cols, after=-1):
        out = real(cur, t, cols, after)
        if t == "workspaces" and not fired:                     # 第一轮导完最后一张表时，别人写了一次
            fired.append(1)
            more = {"W/feedback/events/b.jsonl": ws["W/feedback/events/b.jsonl"]
                    + (_line(id="evt_b_2", batch="b", seq=2, kind="confirm") + "\n").encode()}
            import_commit(conn, repo, _commit(repo, more, "c2"))
        return out

    monkeypatch.setattr(B, "_dump_rows", hooked)
    files, man = B.dump(conn)
    monkeypatch.setattr(B, "_dump_rows", real)
    files2, man2 = B.dump(conn)
    assert fired and man["rev"] == man2["rev"] > 0
    assert {t: (s["rows"], s["sha256"]) for t, s in man["tables"].items()} == \
           {t: (s["rows"], s["sha256"]) for t, s in man2["tables"].items()}
