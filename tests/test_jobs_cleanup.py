"""成功存包后清本机该册缓存和产物副本（_clean_book_artifacts）。"""
from __future__ import annotations

from guji_manager.jobs import runner as R


def _mk(ws, rel, name, size=10):
    d = ws / rel / name
    d.mkdir(parents=True)
    (d / "a.bin").write_bytes(b"x" * size)
    return d


def test_cleans_only_book_dirs(tmp_path):
    ws = tmp_path / "ws"
    c79, p79 = _mk(ws, "cache", "vol79"), _mk(ws, "products", "vol79", 30)
    c68, judge = _mk(ws, "cache", "vol68"), _mk(ws, "cache", "_judge")
    (ws / "feedback").mkdir()
    freed = R._clean_book_artifacts(str(ws), "vol79")
    assert freed == 40
    assert not c79.exists() and not p79.exists()
    assert c68.exists() and judge.exists() and (ws / "feedback").exists()


def test_rejects_bad_book_names(tmp_path):
    ws = tmp_path / "ws"
    keep = _mk(ws, "cache", "vol79")
    for bad in ("", "..", "../ws", "a/b", "_judge"):
        assert R._clean_book_artifacts(str(ws), bad) == 0
    assert keep.exists() and (ws / "cache").exists()


def test_keep_switch(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    d = _mk(ws, "cache", "vol79")
    monkeypatch.setenv("GUJI_JOBS_KEEP_ARTIFACTS", "1")
    assert R._clean_book_artifacts(str(ws), "vol79") == 0 and d.exists()


def test_missing_dirs_ok(tmp_path):
    assert R._clean_book_artifacts(str(tmp_path / "nope"), "vol79") == 0
