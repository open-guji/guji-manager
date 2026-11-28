"""配置组共享层 group-<组>（cv 组层，CV0 2026-11-28）：登记、出版布局、禁写、pull 时拉组（不连库）。"""
import pytest
import yaml

from guji_manager.datastore import workcopy
from guji_manager.ops import group_config as gc


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("GUJI_DATA_BRANCH", raising=False)


def _y(p, doc):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return p


def test_group_ws_is_shared_and_versioned():
    assert workcopy.is_shared_ws("group-wyg")
    assert workcopy.versioned_prefix("group-wyg") == "config/group/"
    assert workcopy.versioned_prefix("pua-wyg") == "config/pua-wyg/"
    assert workcopy.versioned_prefix("988g3f0wsu") is None


def test_parse_and_refs(tmp_path):
    assert gc.parse_ref("wyg@1") == ("wyg", 1) and gc.parse_ref("wyd@v2") == ("wyd", 2)
    for bad in ("wyg", "wyg@0", "W@1"):
        with pytest.raises(SystemExit):
            gc.parse_ref(bad)
    assert gc.config_refs(tmp_path) == []
    _y(tmp_path / "config" / "book_defaults.yaml", {"groups": {"config": "wyg@1", "glyph": ["wyg"]}})
    assert gc.config_refs(tmp_path) == [("wyg", 1)]


def test_build_versions_and_forbidden(tmp_path):
    from guji_manager._cv import central_data_dir
    pytest.importorskip("open_guji_cv.core.book_config").check_group_layer
    ws = gc.workdir("wyg")
    src = _y(tmp_path / "wyg.yaml", {"expected_cols": 8, "params": {"align_ref": {"coord_dp": True}}})
    f1 = gc.build("wyg", src, ws, note="首版")
    f2 = gc.build("wyg", src, ws)
    assert (f1.name, f2.name) == ("v1.yaml", "v2.yaml")
    d = yaml.safe_load(f1.read_text(encoding="utf-8"))
    assert d["meta"]["version"] == 1 and d["expected_cols"] == 8
    assert gc.versions(central_data_dir("group-wyg")) == [1, 2]
    with pytest.raises(SystemExit):
        gc.build("wyg", _y(tmp_path / "bad.yaml", {"corpus": 3}), ws)
    with pytest.raises(SystemExit):
        gc.build("wyg", _y(tmp_path / "bad2.yaml", {"params": {"char_decide": {"follow_ref": "a=b"}}}), ws)
    with pytest.raises(SystemExit, match="meta"):
        gc.build("wyg", _y(tmp_path / "m.yaml", {"meta": {}, "expected_cols": 8}), ws)


def test_pull_requires_group_copy(tmp_path, monkeypatch):
    """书钉了组：库里没有组 → 报错；有组但没有那一版 → 报错；有 → 记 rev。没钉 → 不拉。"""
    from guji_manager.datastore.materialize import MaterializeError
    wsd = tmp_path / "ws"
    wsd.mkdir()
    (wsd / ".central.json").write_text('{"ws": "988g3f0wsu", "branch": "main"}', encoding="utf-8")
    data = workcopy.data_dir(wsd)
    assert workcopy.refresh_group_configs(None, wsd) == {}
    _y(data / "config" / "book_defaults.yaml", {"groups": {"config": "wyg@1"}})

    def missing(*a, **k):
        raise MaterializeError("没有")
    monkeypatch.setattr(workcopy, "readonly_copy", missing)
    with pytest.raises(SystemExit, match="group publish"):
        workcopy.refresh_group_configs(None, wsd)

    monkeypatch.setattr(workcopy, "readonly_copy", lambda *a, **k: (7, True))
    with pytest.raises(SystemExit, match="没有 v1"):
        workcopy.refresh_group_configs(None, wsd)
    _y(gc.version_file(workcopy.borrowed_root("group-wyg", "main"), 1), {"expected_cols": 8})
    assert workcopy.refresh_group_configs(None, wsd) == {"group-wyg": 7}
