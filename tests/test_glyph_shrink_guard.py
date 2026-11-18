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
    assert W.glyph_shrink_problems({"a.jsonl": 6465}, {"a.jsonl": 3554})      # 2026-11-10 史記：55% 也要拦
    assert W.glyph_shrink_problems({"a.jsonl": 100}, {"a.jsonl": 90})
    assert not W.glyph_shrink_problems({"a.jsonl": 100}, {"a.jsonl": 96})     # 缩不到 5%
    assert not W.glyph_shrink_problems({"a.jsonl": 10}, {"a.jsonl": 8})       # 少不到 3 行
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


# ---- 2026-11-18：glyph.db 比账本旧（db pull --no-rebuild）时不许导出 ----

def test_stale_db_changed_export_refused(tmp_path, monkeypatch):
    monkeypatch.delenv(W.ALLOW_STALE_GLYPH_ENV, raising=False)
    store = _seed(tmp_path / "data", {"glyphs.jsonl": 100})
    with pytest.raises(SystemExit, match="比数据目录的字形账本旧"):
        W._export_if_changed(_hooks(tmp_path, {"glyphs.jsonl": 98}), tmp_path / "data",
                             {"glyph_db_fp": "old", W.GLYPH_DB_STALE: True})
    assert W._jsonl_rows(store) == {"glyphs.jsonl": 100}           # 没导出


def test_stale_db_allow_env(tmp_path, monkeypatch):
    monkeypatch.setenv(W.ALLOW_STALE_GLYPH_ENV, "1")
    _seed(tmp_path / "data", {"glyphs.jsonl": 100})
    assert W._export_if_changed(_hooks(tmp_path, {"glyphs.jsonl": 101}), tmp_path / "data",
                                {"glyph_db_fp": "old", W.GLYPH_DB_STALE: True})


def test_stale_db_untouched_is_rebuilt(tmp_path):
    data = tmp_path / "data"
    _seed(data, {"glyphs.jsonl": 3})
    calls = []
    db = tmp_path / "glyph.db"
    db.write_bytes(b"x")
    fp = {"v": "old"}
    h = W.GlyphHooks(fingerprint=lambda p: fp["v"], export=lambda *a: {},
                     rebuild=lambda *a, **k: (calls.append(a), fp.update(v="rebuilt")), db_path=db)
    ws = tmp_path / "ws"
    ws.mkdir()
    st = W._refresh_stale_db(h, ws, data, {"glyph_db_fp": "old", W.GLYPH_DB_STALE: True, "ws": "x"})
    assert calls and st["glyph_db_fp"] == "rebuilt" and W.GLYPH_DB_STALE not in st
    assert W.read_state(data)["glyph_db_fp"] == "rebuilt"


def test_stale_db_touched_not_rebuilt(tmp_path):
    db = tmp_path / "glyph.db"
    db.write_bytes(b"x")
    h = W.GlyphHooks(fingerprint=lambda p: "changed", export=lambda *a: {},
                     rebuild=lambda *a, **k: pytest.fail("库被改过，不该重建"), db_path=db)
    st = {"glyph_db_fp": "old", W.GLYPH_DB_STALE: True}
    assert W._refresh_stale_db(h, tmp_path, tmp_path / "data", st) is st


def test_foreign_glyph_db(tmp_path, monkeypatch):
    from guji_manager.ops import central_glyph as CG
    monkeypatch.setattr(CG, "_db_path", lambda ws: tmp_path / "own" / "glyph.db")
    monkeypatch.delenv("GUJI_GLYPH_DB", raising=False)
    assert CG.foreign_glyph_db(tmp_path) is None
    monkeypatch.setenv("GUJI_GLYPH_DB", str(tmp_path / "own" / "glyph.db"))
    assert CG.foreign_glyph_db(tmp_path) is None
    monkeypatch.setenv("GUJI_GLYPH_DB", str(tmp_path / "siku" / "glyph.db"))
    assert "不是本工作区的字形库" in CG.foreign_glyph_db(tmp_path)
    import os
    assert os.environ["GUJI_GLYPH_DB"] == str(tmp_path / "siku" / "glyph.db")      # 环境变量原样还回去
    with pytest.raises(SystemExit, match="unset GUJI_GLYPH_DB"):
        CG.glyph_hooks(tmp_path)


# ---- 2026-11-18：增量推（只扫改了的文件）与清单 sha 缓存 ----

def test_incremental_ok():
    assert W.incremental_ok({"feedback/events/a.jsonl", "books/vol01.yaml", "feedback/consumed/x.jsonl"})
    assert not W.incremental_ok({"feedback/events/a.jsonl", "output/glyph_store/glyphs.jsonl"})   # 字形库照旧全量


def test_manifest_sha_cache(tmp_path, monkeypatch):
    monkeypatch.delenv("GUJI_DB_NO_SHA_CACHE", raising=False)
    data = tmp_path / "data"
    f = data / "feedback" / "events" / "a.jsonl"
    f.parent.mkdir(parents=True)
    f.write_text('{"id": 1}\n', encoding="utf-8")
    ws = tmp_path / "ws"
    ws.mkdir()
    m1 = W.manifest(ws, data)
    assert (data / W.SHA_CACHE).exists()
    assert W.manifest(ws, data) == m1
    f.write_text('{"id": 2}\n', encoding="utf-8")                       # 同大小、改了内容：mtime 变了就重算
    import os
    st = f.stat()
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1000))
    m2 = W.manifest(ws, data)
    assert m2["feedback/events/a.jsonl"] != m1["feedback/events/a.jsonl"]
    assert m2["feedback/events/a.jsonl"] == W.sha256(f.read_bytes())
