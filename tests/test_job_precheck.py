"""`guji job precheck`：交单前逐册核生效钉子（册 yaml 压基础配置、与本轮要钉的不一致、全批不一致）。"""
from __future__ import annotations

from pathlib import Path

import pytest

import guji_manager._cv as CV
from guji_manager.jobs import precheck as P


def _ws(tmp_path: Path, defaults: str, vols: dict[str, str]) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "books").mkdir()
    (tmp_path / "config" / "book_defaults.yaml").write_text(defaults, encoding="utf-8")
    for v, body in vols.items():
        (tmp_path / "books" / f"{v}.yaml").write_text(f"id: {v}\nraw_dir: raw/{v}\n" + body, encoding="utf-8")
    return tmp_path


@pytest.fixture
def ws(tmp_path, monkeypatch):
    w = _ws(tmp_path, 'cv_version: "0.7.58"\ncode: 3\nglyph_pin: 24\n',
            {"vol01": "", "vol02": "", "vol03": "glyph_pin: 22\n"})
    monkeypatch.setattr(CV, "book_yaml_path", lambda b, *_: w / "books" / f"{b}.yaml", raising=False)
    monkeypatch.setattr(P, "code_problems", lambda n, ws: [])
    return w


def test_parse_books():
    assert P.parse_books("vol01-vol03,vol07", []) == ["vol01", "vol02", "vol03", "vol07"]
    assert P.parse_books("001-003", []) == ["001", "002", "003"]
    assert P.parse_books("all", ["a", "b"]) == ["a", "b"]


def test_pins_come_with_their_layer(ws):
    p = P.pins_of("vol03")
    assert p["glyph_pin"] == (22, "册 yaml")
    assert p["code"] == (3, "基础配置")
    assert p["cv_version"] == ("0.7.58", "基础配置")


def test_flags_volume_pin_overriding_defaults(ws):
    res = P.check(["vol01", "vol02", "vol03"], {"cv_version": "0.7.58", "code": "k3", "glyph_pin": "g24", "corpus": None})
    msgs = "\n".join(res["problems"])
    assert "vol03：glyph_pin 生效 22（册 yaml），本轮要 24" in msgs
    assert "glyph_pin 全批不一致" in msgs
    assert "cv_version" not in msgs and "code" not in msgs
    assert "22*" in P.render(res)


def test_clean_batch_passes(ws):
    res = P.check(["vol01", "vol02"], {"cv_version": "v0.7.58", "code": 3, "glyph_pin": None, "corpus": None})
    assert res["problems"] == []


def test_missing_yaml_is_a_problem(ws):
    res = P.check(["vol09"], {})
    assert res["problems"] and "vol09：读不了册配置" in res["problems"][0]


def test_code_release_checked_once_per_pinned_k(ws, monkeypatch):
    seen = []
    monkeypatch.setattr(P, "code_problems", lambda n, w: seen.append(n) or [f"没有 k{n}"])
    res = P.check(["vol01", "vol02"], {})
    assert seen == [3] and "没有 k3" in res["problems"]
