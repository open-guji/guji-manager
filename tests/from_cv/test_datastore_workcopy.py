"""中心库数据副本（GUJI-608）：数据迁出工作区、pull／push、版本号比对、glyph.db 导出与重建。

要 ``GUJI_TEST_PG_DSN``（可建删 schema 的 Postgres），不给就跳过。
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
from test_datastore_pg import DSN, _commit, _git, _line, conn, repo  # noqa: F401  (fixtures)
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
    from guji_manager.datastore.importer import import_commit
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
    from guji_manager.datastore.workcopy import pull
    d.mkdir(parents=True)
    (d / "workspace.yaml").write_bytes(files["W/workspace.yaml"])
    (d / ".central.json").write_text('{"ws": "tws", "branch": "main"}')
    pull(src, d, cache=cache, glyph=hooks(d) if hooks else None)
    return d


def _data_files(data: Path) -> dict[str, bytes]:
    return {p.relative_to(data).as_posix(): p.read_bytes() for p in data.rglob("*")
            if p.is_file() and p.name != ".central-state.json"}


def test_migrate_refuses_differences_unless_keep_local(repo, conn, tmp_path):  # noqa: F811
    from guji_manager.cli_db import _pg_conn  # noqa: F401  （入口能导入）
    from guji_manager.datastore.workcopy import local_changes, migrate, push
    src, files, cache, _ = _setup(repo, conn, tmp_path)
    ws = _checkout(files, tmp_path / "ws")
    ev = ws / "feedback" / "events" / "b.jsonl"
    ev.write_bytes(ev.read_bytes() + (_line(id="evt_b_2", batch="b", seq=2) + "\n").encode())
    with pytest.raises(SystemExit, match="不一致"):
        migrate(src, ws, cache=cache)
    assert ev.exists() and not (ws / ".central.json").exists()          # 拒绝时什么都没动
    rep = migrate(src, ws, cache=cache, keep_local=True)
    assert rep["pending"] == 1 and not ev.exists()
    assert local_changes(ws) == ["feedback/events/b.jsonl"]
    out = push(conn, ws, actor="t")
    assert out["rev_to"] > out["rev_from"] and local_changes(ws) == []
    assert any(r["id"] == "evt_b_2" for r in src.rows("events", "tws"))


# ---- 整理本进中心库（共享方案 2.2 节，S1）----

def _migrated(repo, conn, tmp_path):  # noqa: F811
    from open_guji_cv.datastore.client import PgSource
    from guji_manager.datastore.importer import import_commit
    from guji_manager.datastore.workcopy import migrate
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
    from guji_manager.datastore.importer import import_commit
    files = _workspace(tmp_path)
    files["W/workspace.yaml"] = b"id: tws\nglyph_lib:\n  borrow: [lib]\n"
    lib = {"L/workspace.yaml": b"id: lib\n", **{f"L/{k}": v for k, v in _lib_store(tmp_path).items()}}
    import_commit(conn, repo, _commit(repo, {**files, **lib}, "c1"))
    cache = _Cache(tmp_path / "cache", {k[2:]: v for k, v in {**files, **lib}.items()})
    return PgSource(conn), files, lib, cache


def _fake_hooks(db: Path, calls: list):
    from guji_manager.datastore.workcopy import GlyphHooks
    db.write_text("v1")
    return GlyphHooks(fingerprint=lambda p: Path(p).read_text(), export=lambda p, s: {},
                      rebuild=lambda w, s, p, e=None: calls.append(list(e or [])) or {}, db_path=db)


# ---- 两级语料库清单（共享方案 S2）----


def test_glyphlib_publish_creates_once(repo, conn, tmp_path):  # noqa: F811
    """共享刻例库：升级脚本第一次推新开工作区、图按 png 进 R2；同一版再推拒绝（版本不可改）。"""
    from open_guji_cv.core.workspace import central_data_dir
    from open_guji_cv.datastore.client import PgSource
    from guji_manager.datastore.importer import apply_schema
    from guji_manager.ops.glyphlib import publish
    apply_schema(conn)                                                  # 空库（真库早有表）
    data = central_data_dir("glyphlib-t-v1")
    for rel, b in _lib_store(tmp_path).items():
        p = data / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
    calls = []
    out = publish(conn, "glyphlib-t-v1", actor="t", uploader=lambda imgs, ext="png": calls.append(ext) or {})
    assert out["rev_to"] > out["rev_from"] and calls == ["png"]
    assert PgSource(conn).rows("glyph_instances", "glyphlib-t-v1")
    with pytest.raises(SystemExit, match="已经发布过"):
        publish(conn, "glyphlib-t-v1", actor="t")


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


