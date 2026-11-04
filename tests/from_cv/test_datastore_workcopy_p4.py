"""中心库数据副本（GUJI-608）：数据迁出工作区、pull／push、版本号比对、glyph.db 导出与重建。

要 ``GUJI_TEST_PG_DSN``（可建删 schema 的 Postgres），不给就跳过。
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
from pg_fixtures import DSN, _commit, _git, _line, conn, repo  # noqa: F401  (fixtures)
from test_datastore_pull import _Cache, _tables, _workspace

psycopg = pytest.importorskip("psycopg")
pytestmark = pytest.mark.skipif(not DSN, reason="没有 GUJI_TEST_PG_DSN（测试用 Postgres）")


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home"))
    for k in ("GUJI_WORKSPACE", "GUJI_GLYPH_DB", "GUJI_GLYPH_STORE", "GUJI_FEEDBACK_DIR"):
        monkeypatch.delenv(k, raising=False)


def _setup(repo, conn, tmp_path):  # noqa: F811
    from open_guji_cv.datastore.client import PgSource
    from open_guji_cv.datastore.importer import import_commit
    files = _workspace(tmp_path)
    c1 = _commit(repo, files, "c1")
    import_commit(conn, repo, c1)
    cache = _Cache(tmp_path / "cache", {k[2:]: v for k, v in files.items()})
    return PgSource(conn), files, cache, c1


def _checkout(files, d: Path) -> Path:
    """模拟 guji-workspace 的 git 检出：数据都在工作区里。"""
    for rel, b in files.items():
        p = d / rel[2:]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
    return d


def _fresh(files, d: Path, src, cache, hooks=None) -> Path:
    """新机器：只有 workspace.yaml 和标记，pull 下来。"""
    from open_guji_cv.datastore.workcopy import pull
    d.mkdir(parents=True)
    (d / "workspace.yaml").write_bytes(files["W/workspace.yaml"])
    (d / ".central.json").write_text('{"ws": "tws", "branch": "main"}')
    pull(src, d, cache=cache, glyph=hooks(d) if hooks else None)
    return d


def _data_files(data: Path) -> dict[str, bytes]:
    return {p.relative_to(data).as_posix(): p.read_bytes() for p in data.rglob("*")
            if p.is_file() and p.name != ".central-state.json"}


def test_migrate_moves_data_out_of_workspace(repo, conn, tmp_path):  # noqa: F811
    from open_guji_cv.core import workspace as W
    from open_guji_cv.datastore.workcopy import local_changes, migrate
    from guji_manager.ops.central_glyph import glyph_hooks, rebuild_db
    src, files, cache, _ = _setup(repo, conn, tmp_path)
    ws = _checkout(files, tmp_path / "ws")
    (ws / "products").mkdir()
    (ws / "products" / "x.json").write_text("{}")
    db = ws / "output" / "glyph.db"
    rebuild_db(ws, ws / "output" / "glyph_store", db)
    db_sha = hashlib.sha256(db.read_bytes()).hexdigest()

    rep = migrate(src, ws, cache=cache, glyph=glyph_hooks(ws))
    assert rep["n_differ"] == 0 and rep["removed_from_workspace"] > 0
    left = sorted(p.relative_to(ws).as_posix() for p in ws.rglob("*") if p.is_file())
    assert left == [".central.json", "output/glyph.db", "products/x.json", "workspace.yaml"]
    assert hashlib.sha256(db.read_bytes()).hexdigest() == db_sha        # glyph.db 不动（指纹不跳）

    data = W.central_data_dir("tws")
    assert _data_files(data) == {k[2:]: v for k, v in files.items() if k != "W/workspace.yaml"}
    tok = W.set_workspace_override(str(ws))
    try:
        assert W.feedback_root() == data / "feedback" and W.glyph_store_path() == data / "output" / "glyph_store"
        assert W.books_dir() == data / "books" and W.glyph_db_path() == db
    finally:
        W.reset_workspace_override(tok)
    assert local_changes(ws, glyph_hooks(ws)) == []
    with pytest.raises(SystemExit, match="已经迁过"):
        migrate(src, ws, cache=cache)


def test_pull_push_between_two_machines(repo, conn, tmp_path, monkeypatch):  # noqa: F811
    from open_guji_cv.datastore.importer import DeleteRefused
    from open_guji_cv.datastore.workcopy import (
        FileDeleteRefused,
        StaleBase,
        data_dir,
        pull,
        push,
    )
    from guji_manager.ops.central_glyph import glyph_hooks
    src, files, cache, c1 = _setup(repo, conn, tmp_path)
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home-a"))
    a = _fresh(files, tmp_path / "a", src, cache, glyph_hooks)
    da = data_dir(a)
    # 重建的 glyph.db 与直接从 git 的字形库 rebuild 的全部表逐行相同
    from open_guji_cv.clustering.glyph_db import rebuild_from_store
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", str(wt), c1)
    rebuild_from_store(wt / "W" / "output" / "glyph_store", tmp_path / "ref.sqlite")
    assert _tables(a / "output" / "glyph.db") == _tables(tmp_path / "ref.sqlite")

    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home-b"))
    b = _fresh(files, tmp_path / "b", src, cache)
    db_ = data_dir(b)
    assert _data_files(da) == _data_files(db_)

    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home-a"))
    (da / "books" / "vol04.yaml").write_bytes(b"id: vol04\n")
    push(conn, a, actor="a")
    rev = src.status()
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home-b"))
    (db_ / "books" / "vol05.yaml").write_bytes(b"id: vol05\n")
    with pytest.raises(StaleBase):
        push(conn, b, actor="b")
    assert src.status() == rev
    with pytest.raises(SystemExit, match="还没推"):
        pull(src, b, cache=cache)
    pull(src, b, cache=cache, force=True)
    assert (db_ / "books" / "vol04.yaml").exists() and not (db_ / "books" / "vol05.yaml").exists()

    (db_ / "books" / "vol03.yaml").unlink()
    with pytest.raises(FileDeleteRefused):
        push(conn, b, actor="b")
    push(conn, b, actor="b", allow_delete=True)
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home-a"))
    pull(src, a, cache=cache)
    assert not (da / "books" / "vol03.yaml").exists()                   # 镜像：库里删了本地也删
    (da / "feedback" / "events" / "b.jsonl").write_bytes(b"")
    with pytest.raises(DeleteRefused):
        push(conn, a, actor="a")


# ---- 整理本进中心库（共享方案 2.2 节，S1）----

def _migrated(repo, conn, tmp_path):  # noqa: F811
    from open_guji_cv.datastore.client import PgSource
    from open_guji_cv.datastore.importer import import_commit
    from open_guji_cv.datastore.workcopy import migrate
    files = _workspace(tmp_path)
    import_commit(conn, repo, _commit(repo, files, "c1"))
    src = PgSource(conn)
    cache = _Cache(tmp_path / "cache", {k[2:]: v for k, v in files.items()})
    ws = _checkout(files, tmp_path / "ws")
    migrate(src, ws, cache=cache)
    return src, cache, files, ws


# ---- 借库与共享层只读（共享方案 S4）----

def _lib_store(tmp_path) -> dict[str, bytes]:
    """另一本书的字形库（字、实例号都和 ``_workspace`` 的不重）。"""
    from test_datastore_pull import _cc

    from open_guji_cv.clustering.glyph_db import GlyphDB, export_store
    db = GlyphDB(tmp_path / "lib-seed.sqlite")
    try:
        _cc.seed_glyphs(db, chars=("丙",), n_each=3, edition="lib", seed=7)
        store = tmp_path / "lib_store"
        export_store(db, store)
    finally:
        db.close()
    return {f"output/glyph_store/{p.relative_to(store).as_posix()}": p.read_bytes()
            for p in sorted(store.rglob("*")) if p.is_file()}


def _borrowing(repo, conn, tmp_path):  # noqa: F811
    """库里两个工作区：tws 借 lib 的字形库（workspace.yaml 写工作区名）。"""
    from open_guji_cv.datastore.client import PgSource
    from open_guji_cv.datastore.importer import import_commit
    files = _workspace(tmp_path)
    files["W/workspace.yaml"] = b"id: tws\nglyph_lib:\n  borrow: [lib]\n"
    lib = {"L/workspace.yaml": b"id: lib\n", **{f"L/{k}": v for k, v in _lib_store(tmp_path).items()}}
    import_commit(conn, repo, _commit(repo, {**files, **lib}, "c1"))
    cache = _Cache(tmp_path / "cache", {k[2:]: v for k, v in {**files, **lib}.items()})
    return PgSource(conn), files, lib, cache


def _fake_hooks(db: Path, calls: list):
    from open_guji_cv.datastore.workcopy import GlyphHooks
    db.write_text("v1")
    return GlyphHooks(fingerprint=lambda p: Path(p).read_text(), export=lambda p, s: {},
                      rebuild=lambda w, s, p, e=None: calls.append(list(e or [])) or {}, db_path=db)


def test_pull_rebuilds_glyph_db_with_borrowed_instances(repo, conn, tmp_path):  # noqa: F811
    """真聚类层：重建出的 glyph.db 里有借来的字（丙），自己的字（甲乙）也在。"""
    import sqlite3

    from guji_manager.ops.central_glyph import glyph_hooks
    src, files, _, cache = _borrowing(repo, conn, tmp_path)
    ws = _fresh(files, tmp_path / "ws", src, cache, glyph_hooks)
    c = sqlite3.connect(glyph_hooks(ws).db_path)
    try:
        chars = {r[0] for r in c.execute("SELECT DISTINCT label FROM instances")}
    finally:
        c.close()
    assert {"甲", "乙", "丙"} <= chars


# ---- 两级语料库清单（共享方案 S2）----

def test_corpus_base_published_and_pulled_with_book(repo, conn, tmp_path, monkeypatch):  # noqa: F811
    """build-base 第一次新开 corpus-base、之后加新版不动旧版；书库清单写了 base 的工作区，
    pull 顺带把底库清单拉成只读副本，verify 两级一起对。"""
    from open_guji_cv.core.corpus_pin import BASE_DIR, BASE_WS
    from open_guji_cv.core.workspace import borrowed_root
    from open_guji_cv.datastore.workcopy import data_dir, pull, push, uses_corpus_base
    from guji_manager.ops import corpus_pack as cp
    monkeypatch.setattr(cp, "_repo_dirty", lambda paths, repo=None: [])
    monkeypatch.setattr(cp, "_repo_commit", lambda repo=None: "c0ffee")
    src, cache, files, ws = _migrated(repo, conn, tmp_path)

    r1 = cp.publish_base(src, conn, note="b1", actor="t")
    assert r1["base_version"] == 1 and r1["push"]["rev_to"] > r1["push"]["rev_from"]
    rows = {r["src_path"] for r in src.rows("files", BASE_WS)}
    assert f"{BASE_DIR}/b1/manifest.json" in rows
    with pytest.raises(SystemExit, match="只读"):                    # 普通 push 照旧拒绝
        push(conn, cp.base_workdir("main"), actor="t")

    assert not uses_corpus_base(ws)
    pull(src, ws, cache=cache)
    assert not (borrowed_root(BASE_WS) / BASE_DIR).exists()             # 用不到底库就不拉
    # 本机拉一份底库（同 guji corpus init），出两级书库清单，推上去
    from open_guji_cv.datastore.workcopy import refresh_corpus_base
    refresh_corpus_base(src, ws, cache=cache, always=True)
    cp.build(ws, base="latest")
    push(conn, ws, actor="t")
    assert uses_corpus_base(ws) and cp.verify(ws, 1)["base"] == 1

    r2 = cp.publish_base(src, conn, note="b2", actor="t")
    assert r2["base_version"] == 2
    assert {f"{BASE_DIR}/b1/manifest.json", f"{BASE_DIR}/b2/manifest.json"} <= \
        {r["src_path"] for r in src.rows("files", BASE_WS)}

    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home-m2"))       # 新机器
    fresh = _fresh(files, tmp_path / "m2", src, cache)
    assert (data_dir(fresh) / "config/corpus-pack/v1/manifest.json").exists()
    assert sorted(p.name for p in (borrowed_root(BASE_WS) / BASE_DIR).iterdir()) == ["b1", "b2"]
    assert cp.verify(fresh, 1)["base"] == 1


# ---- 省流量：只向库要变了的文件、只取要用的列（Neon 免费档每月 5 GiB 公网流量）----

class _Counting:
    """包一层数据源，记下每次 rows 的表、列、过滤，和回了几行。"""

    def __init__(self, src):
        self.src, self.calls = src, []

    def __getattr__(self, k):
        return getattr(self.src, k)

    def rows(self, table, ws=None, cols=None, **filters):
        out = list(self.src.rows(table, ws, cols=cols, **filters))
        self.calls.append((table, cols, filters, len(out)))
        return iter(out)


class _WithSnapshots(_Counting):
    """带快照接口的数据源（快照存内存，同 Worker 的 /v1/snapshots：只留 rev 最大的）。"""

    def __init__(self, src, store):
        super().__init__(src)
        self.store = store

    def get_snapshot(self, ws):
        return self.store.get(ws)

    def put_snapshot(self, ws, rev, data):
        if ws not in self.store or self.store[ws][0] < rev:
            self.store[ws] = (rev, data)
        return {}


