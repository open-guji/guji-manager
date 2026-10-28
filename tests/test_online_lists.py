import os

from guji_manager import online_lists as OL


def test_on_promote_skips_non_volume(capsys, monkeypatch):
    called = []
    monkeypatch.setattr(OL.subprocess, "Popen", lambda *a, **k: called.append(a))
    OL.on_promote("not-a-vol", "x", ws="/tmp")
    assert not called and capsys.readouterr().out == ""


def test_on_promote_reports_missing_env(capsys, monkeypatch):
    monkeypatch.delenv("GUJI_DATA_TOKEN_PROD", raising=False)
    monkeypatch.setenv("GUJI_DATA_TOKEN_READ", "r")
    called = []
    monkeypatch.setattr(OL.subprocess, "Popen", lambda *a, **k: called.append(a))
    OL.on_promote("vol13", "lbl", ws="/tmp")
    out = capsys.readouterr().out
    assert "GUJI_DATA_TOKEN_PROD" in out and not called


def test_on_promote_can_be_disabled(capsys, monkeypatch):
    monkeypatch.setenv("GUJI_AUTO_ONLINE_LISTS", "0")
    OL.on_promote("vol13", "lbl", ws="/tmp")
    assert capsys.readouterr().out == ""


def test_on_promote_starts_detached_job(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GUJI_DATA_TOKEN_PROD", "p")
    monkeypatch.setenv("GUJI_DATA_TOKEN_READ", "r")
    monkeypatch.setenv("GUJI_BOOK_TEXT", str(tmp_path))
    monkeypatch.setenv("GUJI_CV_REPO", str(tmp_path))
    seen = {}
    monkeypatch.setattr(OL.subprocess, "Popen", lambda cmd, **k: seen.update(cmd=cmd, kw=k))
    OL.on_promote("vol13", "lbl", ws=str(tmp_path))
    assert "--vol" in seen["cmd"] and "vol13" in seen["cmd"] and seen["kw"]["start_new_session"] is True
    assert os.path.exists(tmp_path / "reports" / "vol13" / "_publish" / "auto_issue.log")
    assert "后台" in capsys.readouterr().out


def test_on_promote_never_raises(monkeypatch):
    monkeypatch.setenv("GUJI_DATA_TOKEN_PROD", "p")
    monkeypatch.setenv("GUJI_DATA_TOKEN_READ", "r")
    monkeypatch.setattr(OL.os, "makedirs", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    OL.on_promote("vol13", "lbl", ws="/tmp")
