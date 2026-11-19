"""PUA 码表共享层 pua-wyg：出版布局、旧版本不可改、按钉读、没钉读本书（不连库）。"""
import json

import pytest

from guji_manager.datastore import workcopy
from guji_manager.ops import pua_table as pt


def _jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return path


ROWS = [{"code": "daizhige:U+EAA0", "verdict": "char", "char": "乖"},
        {"code": "daizhige:U+EAA1", "verdict": "pending"}]


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("GUJI_DATA_BRANCH", raising=False)


def test_parse_pin():
    assert pt.parse_pin(None) is None and pt.parse_pin("v3") == 3 and pt.parse_pin(2) == 2
    with pytest.raises(ValueError):
        pt.parse_pin("x")


def test_shared_name_registered():
    assert workcopy.is_shared_ws("pua-wyg") and "pua-wyg" in workcopy.VERSIONED_SHARED


def test_build_versions_and_read(tmp_path):
    from guji_manager._cv import central_data_dir
    ws = pt.workdir()
    src = _jsonl(tmp_path / "t.jsonl", ROWS)
    d1 = pt.build(src, ws, note="v1")
    d2 = pt.build(src, ws, note="v2")
    assert d1.name == "v1" and d2.name == "v2"
    data = central_data_dir(pt.PUA_WS)
    assert pt.versions(data) == [1, 2]
    assert set(pt.read_rows(1, data)) == {r["code"] for r in ROWS}
    (d1 / pt.TABLE_FILE).write_text("{}\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="sha256"):
        pt.read_rows(1, data)
    with pytest.raises(SystemExit, match="没有 v9"):
        pt.read_rows(9, data)


def test_build_rejects_bad_tables(tmp_path):
    ws = pt.workdir()
    _jsonl(tmp_path / "dup.jsonl", ROWS + ROWS[:1])
    with pytest.raises(SystemExit, match="重复"):
        pt.build(tmp_path / "dup.jsonl", ws)
    (tmp_path / "e.jsonl").write_text("\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="空表"):
        pt.build(tmp_path / "e.jsonl", ws)


def test_pins_in(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "books").mkdir()
    (tmp_path / "config" / "book_defaults.yaml").write_text("pua_table_pin: v2\n", encoding="utf-8")
    (tmp_path / "books" / "a.yaml").write_text("id: a\n", encoding="utf-8")
    assert pt.pins_in(tmp_path) == {2}


def test_reasons_load_pua_table_pinned_and_unpinned(tmp_path):
    from guji_manager._cv import borrowed_root
    from guji_manager.review.reasons import load_pua_table
    root = tmp_path / "book"
    (root / "config" / "pua").mkdir(parents=True)
    _jsonl(root / "config" / "pua" / "pua_table.jsonl", [{"code": "daizhige:U+0001", "verdict": "char"}])
    assert set(load_pua_table(root)) == {"daizhige:U+0001"}           # 没钉：读本书
    br = borrowed_root(pt.PUA_WS)
    d = pt.version_dir(br, 1)
    d.mkdir(parents=True)
    raw = "\n".join(json.dumps(r, ensure_ascii=False) for r in ROWS).encode()
    (d / pt.TABLE_FILE).write_bytes(raw)
    (d / pt.MANIFEST_FILE).write_text(json.dumps({"sha256": pt._sha(raw)}), encoding="utf-8")
    assert set(load_pua_table(root, pin=1)) == {r["code"] for r in ROWS}
    (root / "config" / "book_defaults.yaml").write_text("pua_table_pin: 1\n", encoding="utf-8")
    assert set(load_pua_table(root)) == {r["code"] for r in ROWS}      # book_defaults 钉了：读共享层
    (root / "config" / "book_defaults.yaml").write_text("pua_table_pin: 7\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        load_pua_table(root)                                           # 钉了没有的版本：报错不读空表
