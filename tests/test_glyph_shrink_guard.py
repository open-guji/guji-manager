"""字形库导出缩水闸（2026-11-09）：本机 glyph.db 是空库／没重建时，导出不能把数据目录里的字形账本写成空。"""
from __future__ import annotations

from pathlib import Path

import pytest

from guji_manager.datastore import workcopy as W


def _hooks(tmp_path, rows: dict[str, int]):
    db = tmp_path / "glyph.db"
    db.write_bytes(b"x")

    def export(db_path, store):
        store.mkdir(parents=True, exist_ok=True)
        for name, n in rows.items():
            (store / name).write_text("".join('{"i":%d}\n' % i for i in range(n)), encoding="utf-8")
        return {}

    return W.GlyphHooks(fingerprint=lambda p: "new-fp", export=export, rebuild=lambda *a, **k: {}, db_path=db)


def _seed(data: Path, rows: dict[str, int]) -> Path:
    store = data / W.GS.rstrip("/")
    store.mkdir(parents=True)
    for name, n in rows.items():
        (store / name).write_text("".join('{"i":%d}\n' % i for i in range(n)), encoding="utf-8")
    return store


def test_problems_pure():
    assert W.glyph_shrink_problems({"a.jsonl": 10}, {"a.jsonl": 0}) == ["a.jsonl：10 → 0 行"]
    assert W.glyph_shrink_problems({"a.jsonl": 10}, {"a.jsonl": 4})
    assert not W.glyph_shrink_problems({"a.jsonl": 10}, {"a.jsonl": 6})
    assert not W.glyph_shrink_problems({"a.jsonl": 0}, {"a.jsonl": 0})        # 原来就空：不拦
    assert not W.glyph_shrink_problems({}, {"a.jsonl": 3})


def test_empty_db_export_blocked_and_restored(tmp_path, monkeypatch):
    monkeypatch.delenv(W.ALLOW_GLYPH_SHRINK_ENV, raising=False)
    store = _seed(tmp_path / "data", {"glyphs.jsonl": 100, "exemplars.jsonl": 50})
    with pytest.raises(SystemExit, match="缩水"):
        W._export_if_changed(_hooks(tmp_path, {"glyphs.jsonl": 0, "exemplars.jsonl": 0}), tmp_path / "data", {"glyph_db_fp": "old"})
    assert W._jsonl_rows(store) == {"exemplars.jsonl": 50, "glyphs.jsonl": 100}     # 已还原


def test_normal_growth_passes(tmp_path):
    store = _seed(tmp_path / "data", {"glyphs.jsonl": 100})
    assert W._export_if_changed(_hooks(tmp_path, {"glyphs.jsonl": 120}), tmp_path / "data", {"glyph_db_fp": "old"})
    assert W._jsonl_rows(store) == {"glyphs.jsonl": 120}


def test_allow_env_lets_shrink_through(tmp_path, monkeypatch):
    monkeypatch.setenv(W.ALLOW_GLYPH_SHRINK_ENV, "1")
    store = _seed(tmp_path / "data", {"glyphs.jsonl": 100})
    assert W._export_if_changed(_hooks(tmp_path, {"glyphs.jsonl": 10}), tmp_path / "data", {"glyph_db_fp": "old"})
    assert W._jsonl_rows(store) == {"glyphs.jsonl": 10}


def test_unchanged_fingerprint_skips(tmp_path):
    store = _seed(tmp_path / "data", {"glyphs.jsonl": 5})
    h = _hooks(tmp_path, {"glyphs.jsonl": 0})
    assert not W._export_if_changed(h, tmp_path / "data", {"glyph_db_fp": "new-fp"})
    assert W._jsonl_rows(store) == {"glyphs.jsonl": 5}
