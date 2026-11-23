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


def test_cleans_raw_images_of_this_book_only(tmp_path):
    ws = tmp_path / "ws"
    raw79, raw68 = _mk(ws, "data_full", "vol79", 50), _mk(ws, "data_full", "vol68", 50)
    freed = R._clean_book_artifacts(str(ws), "vol79")
    assert freed == 50 and not raw79.exists() and raw68.exists()


def test_sweep_cleans_all_books_but_not_other_dirs(tmp_path, monkeypatch):
    import json
    home = tmp_path / "home"
    ws = home / "repo"
    ws.mkdir(parents=True)
    (ws / ".central.json").write_text(json.dumps({"ws": "wsid1"}), encoding="utf-8")
    data = home / ".guji-data" / "main" / "wsid1" / "books"
    data.mkdir(parents=True)
    for v in ("vol01", "vol02"):
        (data / f"{v}.yaml").write_text("x", encoding="utf-8")
    a, b = _mk(ws, "cache", "vol01", 20), _mk(ws, "data_full", "vol02", 30)
    judge, other = _mk(ws, "cache", "_judge"), _mk(ws, "cache", "glyph-derived")
    monkeypatch.setattr(R.Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("GUJI_DATA_HOME", raising=False)
    freed = R._sweep_book_dirs(lambda m: None)
    assert freed == 50 and not a.exists() and not b.exists() and judge.exists() and other.exists()


def test_disk_gate_sweep_cooldown(monkeypatch):
    """剩余空间低于清扫阈值但高于领单门槛、又清不出东西时：只扫一次，冷却期内不重扫，且照常放行领单。"""
    calls = []
    monkeypatch.setattr(R, "_clean_job_dirs", lambda: None)
    monkeypatch.setattr(R, "_prune_glyph_dbs", lambda say, keep_recent=None: None)
    monkeypatch.setattr(R, "_free_gb", lambda: 7.9)
    monkeypatch.setattr(R, "_sweep_book_dirs", lambda say=print: calls.append(1) or 0)
    monkeypatch.setattr(R, "_sweep_at", 0.0)
    msgs = []
    assert R._disk_gate(msgs.append) is None
    assert R._disk_gate(msgs.append) is None
    assert len(calls) == 1
    assert any("没有可清的" in m for m in msgs)


def test_clean_blob_cache_removes_root_and_keeps_data_home(tmp_path, monkeypatch):
    cache = tmp_path / "gdcache"
    blob = cache / "sha256" / "ab" / "abc.png"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"y" * 7)
    data = tmp_path / "gdata" / "main" / "wsid1" / "feedback"
    data.mkdir(parents=True)
    (data / "x.jsonl").write_text("人裁", encoding="utf-8")
    monkeypatch.setenv("GUJI_DATA_CACHE", str(cache))
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "gdata"))
    assert R._clean_blob_cache() == 7
    assert not cache.exists() and (data / "x.jsonl").exists()
    assert R._clean_blob_cache() == 0


def test_clean_blob_cache_keep_switch(tmp_path, monkeypatch):
    cache = tmp_path / "gdcache"
    cache.mkdir()
    monkeypatch.setenv("GUJI_DATA_CACHE", str(cache))
    monkeypatch.setenv("GUJI_JOBS_KEEP_ARTIFACTS", "1")
    assert R._clean_blob_cache() == 0 and cache.exists()
