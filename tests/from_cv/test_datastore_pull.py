"""中心库读路径验收（GUJI-606）：篡改的库内容被拒、实验分支事件显式导入、经 Worker 读（假 Worker）
分页与批量签名。拉、推、迁移见 ``test_datastore_workcopy.py``。

要 ``GUJI_TEST_PG_DSN``（可建删 schema 的 Postgres），不给就跳过；假 Worker 那条不要库。
"""

from __future__ import annotations

from cv_paths import CV_REPO, CV_TESTS  # cv 仓根（本测试从 cv tests/ 搬来）
import hashlib
import importlib.util
import json
import sqlite3
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from pg_fixtures import DSN, _commit, _git, _line, conn, repo  # noqa: F401  (fixtures)

psycopg = pytest.importorskip("psycopg")
needs_pg = pytest.mark.skipif(not DSN, reason="没有 GUJI_TEST_PG_DSN（测试用 Postgres）")

_spec = importlib.util.spec_from_file_location(
    "_clustering_conftest", CV_TESTS / "clustering" / "conftest.py")
_cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cc)


def _store_files(tmp_path) -> dict[str, bytes]:
    """造一个真字形库（admit → export），返回 {工作区内相对路径: 字节}。"""
    from open_guji_cv.clustering.glyph_db import GlyphDB, export_store
    db = GlyphDB(tmp_path / "seed.sqlite")
    try:
        _cc.seed_glyphs(db, chars=("甲", "乙"), n_each=4)
        cur = db.conn.cursor()
        cur.execute("INSERT INTO events (source_id, batch, seq, ts, op, payload) VALUES (?,?,?,?,?,?)",
                    ("tbook", "b1", 1, "t", "confirm", '{"op": "confirm"}'))
        db.conn.commit()
        store = tmp_path / "seed_store"
        export_store(db, store)
    finally:
        db.close()
    return {f"output/glyph_store/{p.relative_to(store).as_posix()}": p.read_bytes()
            for p in sorted(store.rglob("*")) if p.is_file()}


def _workspace(tmp_path) -> dict[str, bytes]:
    files = {"W/workspace.yaml": b"id: tws\n", "W/books/vol03.yaml": b"id: vol03\n"}
    files.update({f"W/{k}": v for k, v in _store_files(tmp_path).items()})
    files["W/feedback/events/b.jsonl"] = (_line(id="evt_b_1", batch="b", seq=1, kind="confirm") + "\n").encode()
    return files


class _Cache:
    """预先灌好的图缓存（PgSource 拿不到 R2）。"""

    def __init__(self, root: Path, files: dict[str, bytes]):
        from open_guji_cv.datastore.client import BlobCache
        self.c = BlobCache(root)
        for rel, b in files.items():
            if rel.endswith(".png"):
                self.c.put(hashlib.sha256(b).hexdigest(), b)

    def __getattr__(self, k):
        return getattr(self.c, k)


def _tables(db_path: Path) -> dict[str, list]:
    c = sqlite3.connect(db_path)
    try:
        names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                         "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {n: sorted(map(repr, c.execute(f"SELECT * FROM {n}").fetchall())) for n in names}
    finally:
        c.close()


@needs_pg
def test_materialize_refuses_tampered_db(repo, conn, tmp_path):  # noqa: F811
    from open_guji_cv.datastore.client import PgSource
    from guji_manager.datastore.importer import import_commit
    from guji_manager.datastore.materialize import MaterializeError, materialize

    files = _workspace(tmp_path)
    import_commit(conn, repo, _commit(repo, files, "c1"))
    conn.execute("UPDATE glyphs SET raw = raw || ' '")
    out = tmp_path / "out"
    with pytest.raises(MaterializeError, match="sha 不符"):
        materialize(PgSource(conn), "tws", out, cache=_Cache(tmp_path / "cache", files))
    assert not (out / "output").exists()            # 不留半成品


class _FakeDst:
    branch = "main"

    def __init__(self, have):
        self.have, self.calls = have, []

    def rows(self, table, ws):
        return iter([{"id": i} for i in self.have])

    def append_events(self, ws, src_path, lines, branch=None):
        self.calls.append((ws, src_path, lines, branch))
        return {"inserted": [json.loads(x)["id"] for x in lines], "duplicates": [], "import_id": 9, "rev_to": 99}


@needs_pg
def test_import_events_from_exp_branch(repo, conn, tmp_path):  # noqa: F811
    from open_guji_cv.datastore.client import PgSource
    from guji_manager.datastore.importer import import_commit
    from guji_manager.datastore.pull import import_events

    files = _workspace(tmp_path)
    files["W/feedback/events/b.jsonl"] += (_line(id="evt_b_2", batch="b", seq=2) + "\n").encode()
    import_commit(conn, repo, _commit(repo, files, "c1"))
    exp = PgSource(conn, branch="exp/GUJI-606-t")

    dst = _FakeDst(have={"evt_b_1"})
    plan = import_events(exp, dst, "tws", None, dst_branch="main", dry_run=True)
    assert plan["plan"] == {"feedback/events/b.jsonl": 1} and not dst.calls
    res = import_events(exp, dst, "tws", None, dst_branch="main")
    assert res["results"][0]["inserted"] == 1
    assert json.loads(dst.calls[0][2][0])["id"] == "evt_b_2" and dst.calls[0][3] == "main"
    with pytest.raises(SystemExit, match="找不到"):
        import_events(exp, _FakeDst(set()), "tws", {"evt_nope"}, dst_branch="main")


# ---- 经 Worker 读：假 Worker，验证分页、批量签名、旧版 Worker 退回逐张签 ----

def _fake_worker(rows: list[dict], blobs: dict[str, bytes], batch: bool):
    calls = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj=None, raw=None):
            body = raw if raw is not None else json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = dict(urllib.parse.parse_qsl(u.query))
            calls.append(("GET", u.path))
            if u.path.startswith("/blob/"):
                key = u.path.rsplit("/", 1)[1]
                if key not in blobs:
                    return self._send(404, {"error": "not_found", "message": "no such blob"})
                return self._send(200, raw=blobs[key])
            assert self.headers["authorization"] == "Bearer tok"
            if u.path == "/v1/status":
                return self._send(200, {"rev": 7})
            if u.path == "/v1/tables/source_files":
                lim = int(q["limit"])
                start = json.loads(q["after"])[0] if "after" in q else -1
                page = [r for r in rows if r["i"] > start][:lim]
                nxt = json.dumps([page[-1]["i"]]) if len(page) == lim else None
                return self._send(200, {"rows": page, "next": nxt})
            self._send(404, {"error": "not_found", "message": "x"})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            calls.append(("POST", self.path))
            base = f"http://127.0.0.1:{self.server.server_port}/blob/"
            if self.path == "/v1/assets/sign-batch" and batch:
                return self._send(200, {"items": [{"sha256": s, "url": base + s} for s in body["sha256s"]]})
            if self.path == "/v1/assets/sign":
                return self._send(200, {"url": base + body["sha256"]})
            self._send(404, {"error": "not_found", "message": "没有这个接口"})

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, calls


