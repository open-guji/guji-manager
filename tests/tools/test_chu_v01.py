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
