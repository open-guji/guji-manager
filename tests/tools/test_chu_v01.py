"""tools/开书/出v01.py 的章号推法（SJ 11-19：册号 01 被直接当章号）。"""
import importlib.util
from pathlib import Path

import pytest

_P = Path(__file__).resolve().parents[2] / "tools" / "开书" / "出v01.py"


def _mod():
    spec = importlib.util.spec_from_file_location("chu_v01", _P)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_chapter_given_padded(tmp_path):
    assert _mod().chapter_for("01", tmp_path, "7") == "007"


def test_chapter_from_book_digits(tmp_path, monkeypatch):
    m = _mod()
    monkeypatch.setitem(__import__("sys").modules, "open_guji_cv.core.volume_id", None)   # cv 推不出时退到册号数字
    assert m.chapter_for("01", tmp_path) == "001"
    assert m.chapter_for("vol12", tmp_path) == "012"
    with pytest.raises(SystemExit):
        m.chapter_for("abc", tmp_path)


def _bt(tmp_path):
    """最小 book-text 条目 + 一章导出（char/cord/norm）。"""
    import json
    tid = "abc123"
    d = tmp_path / "bt" / "Book" / "1" / "2" / "3" / tid
    (d / "default").mkdir(parents=True)
    (d / "default" / "index.json").write_text(json.dumps({"chapters": []}), encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps({"versions": [{"key": "default"}]}), encoding="utf-8")
    ex = tmp_path / "export"
    ex.mkdir()
    (ex / "009.char.json").write_text(json.dumps({"version": "0.1.0"}), encoding="utf-8")
    (ex / "009.cord.json").write_text(json.dumps({"pages": [{"page": 3}, {"page": 5}]}), encoding="utf-8")
    (ex / "009.norm.json").write_text("{}", encoding="utf-8")
    return tmp_path / "bt", tid, d / "default", ex


def _entry(dd):
    import json
    return json.loads((dd / "index.json").read_text(encoding="utf-8"))["chapters"][0]


def test_bt_add_chapter_copies_gaps(tmp_path):
    """Web 11-23：章有 NNN.gaps.json 就拷进版本目录、条目写 gaps_file。"""
    bt, tid, dd, ex = _bt(tmp_path)
    body = '{"schema": "guji-gaps/0.1", "gaps": []}'
    (ex / "009.gaps.json").write_text(body, encoding="utf-8")
    _mod().bt_add_chapter(bt, tid, "009", ex, "卷九", "t")
    ent = _entry(dd)
    assert ent["gaps_file"] == "009.gaps.json" and ent["cord_file"] == "009.cord.json"
    assert (dd / "009.gaps.json").read_text(encoding="utf-8") == body


def test_bt_add_chapter_no_gaps(tmp_path):
    """没有缺页文件就不写 gaps_file；重出时缺页已撤，旧文件删掉。"""
    bt, tid, dd, ex = _bt(tmp_path)
    (dd / "009.gaps.json").write_text("{}", encoding="utf-8")        # 上一次出的旧文件
    _mod().bt_add_chapter(bt, tid, "009", ex, "卷九", "t")
    assert "gaps_file" not in _entry(dd)
    assert not (dd / "009.gaps.json").exists()


def test_no_retired_cv_scripts():
    """cv #1974 删了 republish／proof_cycle／auto_cycle 等整张换单脚本：出v01 不再以子进程调它们，导出走 land_text.export_cmd。"""
    src = _P.read_text(encoding="utf-8")
    code = "\n".join(l.split("#", 1)[0] for l in src.splitlines())
    assert "scripts/zhengli/" not in code
    assert "LT.export_cmd(" in code
