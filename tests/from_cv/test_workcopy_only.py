"""路径限定的 pull／push／sync（``guji db … --only``，换包按条目对账，GM4 11-24）。"""

from __future__ import annotations

import pytest
from pg_fixtures import DSN, _commit, _line, conn, repo  # noqa: F401  (fixtures)
from test_datastore_pull import _Cache, _workspace

pytestmark = pytest.mark.skipif(not DSN, reason="没有测试库")

EV = "feedback/events/b.jsonl"
BOOK = "books/vol03.yaml"


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home"))
    for k in ("GUJI_WORKSPACE", "GUJI_GLYPH_DB", "GUJI_GLYPH_STORE", "GUJI_FEEDBACK_DIR"):
        monkeypatch.delenv(k, raising=False)


def _two(repo, conn, tmp_path, monkeypatch):  # noqa: F811
    from guji_manager.datastore.importer import import_commit
    from guji_manager.datastore.sqlsource import SqlSource
    from guji_manager.datastore.workcopy import data_dir, pull
    files = _workspace(tmp_path)
    import_commit(conn, repo, _commit(repo, files, "c1"))
    cache = _Cache(tmp_path / "cache", {k[2:]: v for k, v in files.items()})
    src = SqlSource(conn)
    out = {}
    for name in ("a", "b"):
        monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / f"home-{name}"))
        d = tmp_path / name
        d.mkdir()
        (d / "workspace.yaml").write_bytes(files["W/workspace.yaml"])
        (d / ".central.json").write_text('{"ws": "tws", "branch": "main"}')
        pull(src, d, cache=cache)
        out[name] = (d, data_dir(d))
    return src, cache, out


def _add_event(data, eid, seq):
    (data / EV).write_bytes((data / EV).read_bytes() + (_line(id=eid, batch="b", seq=seq) + "\n").encode())


def test_norm_only_rejects_glyph_store_and_bad_paths():
    from guji_manager.datastore.workcopy_only import norm_only
    assert norm_only(["feedback/events/", "./books/vol03.yaml"]) == ("books/vol03.yaml", "feedback/events/")
    for bad in ("output/glyph_store/", "output/", "config/", "config/glyph-pack/g1/manifest.json", "../x",
                "workspace.yaml", "tmp/x.jsonl"):
        with pytest.raises(SystemExit):
            norm_only([bad])


def test_push_only_leaves_out_of_range_changes(repo, conn, tmp_path, monkeypatch):  # noqa: F811
    from guji_manager.datastore.workcopy import local_changes, read_state
    from guji_manager.datastore.workcopy_only import push_only
    src, _cache, m = _two(repo, conn, tmp_path, monkeypatch)
    a, da = m["a"]
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home-a"))
    _add_event(da, "evt_b_2", 2)
    (da / BOOK).write_bytes(b"id: vol03\nx: 1\n")
    rev0 = read_state(da)["rev"]
    out = push_only(conn, a, ["feedback/events/"], actor="t")
    assert out["pushed"] == [EV]
    assert {r["id"] for r in src.rows("events", "tws")} >= {"evt_b_2"}
    assert next(src.rows("books", "tws"))["raw"] == "id: vol03\n"          # 范围外没推
    assert local_changes(a) == [BOOK]
    st = read_state(da)
    assert st["rev"] > rev0 and not st.get("only_revs")                    # 库里只有这次的改动：全局 rev 前进
    assert push_only(conn, a, ["feedback/events/"], actor="t")["action"] == "nothing"


def test_pull_only_takes_range_and_keeps_rest(repo, conn, tmp_path, monkeypatch):  # noqa: F811
    from guji_manager.datastore.workcopy import push, read_state
    from guji_manager.datastore.workcopy_only import pull_only, push_only
    src, cache, m = _two(repo, conn, tmp_path, monkeypatch)
    (a, da), (b, db_) = m["a"], m["b"]
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home-a"))
    _add_event(da, "evt_b_2", 2)
    (da / BOOK).write_bytes(b"id: vol03\nx: 1\n")
    push(conn, a, actor="a")
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home-b"))
    g = read_state(db_)["rev"]
    out = pull_only(src, b, [EV], cache=cache)
    assert out["written"] == 1 and (db_ / EV).read_bytes() == (da / EV).read_bytes()
    assert (db_ / BOOK).read_bytes() == b"id: vol03\n"                     # 范围外不拉
    st = read_state(db_)
    assert st["rev"] == g and st["only_revs"] == {EV: out["rev"]}
    _add_event(db_, "evt_b_3", 3)                                          # 范围内已是最新：可以直接推
    assert push_only(conn, b, [EV], actor="b")["pushed"] == [EV]
    assert read_state(db_)["rev"] == g                                     # 范围外库里有人改过：全局 rev 不动


def test_push_only_stale_then_sync_only_merges(repo, conn, tmp_path, monkeypatch):  # noqa: F811
    from guji_manager.datastore.workcopy import StaleBase, local_changes, push, sync
    from guji_manager.datastore.workcopy_only import push_only, sync_only
    src, cache, m = _two(repo, conn, tmp_path, monkeypatch)
    (a, da), (b, db_) = m["a"], m["b"]
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home-a"))
    _add_event(da, "evt_b_2", 2)
    push(conn, a, actor="a")
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home-b"))
    _add_event(db_, "evt_b_3", 3)
    with pytest.raises(StaleBase):
        push_only(conn, b, ["feedback/events/"], actor="b")
    out = sync_only(src, conn, b, ["feedback/events/"], actor="b", cache=cache)
    assert out["action"] == "merged+push" and out["merged"] == [EV]
    assert {"evt_b_2", "evt_b_3"} <= {r["id"] for r in src.rows("events", "tws")}
    assert sync_only(src, conn, b, ["feedback/events/"], actor="b", cache=cache)["action"] == "nothing"
    # 之后整体 sync 照常：库里只有自己推过的，没东西可拉可推
    assert sync(src, conn, b, actor="b", cache=cache)["action"] in ("nothing", "pulled")
    assert local_changes(b) == []


def test_push_only_ok_when_others_wrote_outside_range(repo, conn, tmp_path, monkeypatch):  # noqa: F811
    from guji_manager.datastore.workcopy import local_changes, push, sync
    from guji_manager.datastore.workcopy_only import push_only
    src, cache, m = _two(repo, conn, tmp_path, monkeypatch)
    (a, da), (b, db_) = m["a"], m["b"]
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home-a"))
    _add_event(da, "evt_b_2", 2)
    push(conn, a, actor="a")
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home-b"))
    (db_ / BOOK).write_bytes(b"id: vol03\ny: 2\n")
    assert push_only(conn, b, [BOOK], actor="b")["pushed"] == [BOOK]
    assert sync(src, conn, b, actor="b", cache=cache)["action"] == "pulled"  # 整体 sync 只把别人的事件拉下来
    assert local_changes(b) == [] and b"evt_b_2" in (db_ / EV).read_bytes()
