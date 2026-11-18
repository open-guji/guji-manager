"""runner 自更新失败要留下原因，不再静默。"""
import subprocess

from guji_manager.jobs import runner as R


def test_refresh_logs_merge_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(R, "_refresh_manager", lambda: None)
    monkeypatch.setattr(R, "RUNNER_ROOT", tmp_path)

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="fatal: Not possible to fast-forward, aborting.")

    monkeypatch.setattr(R.subprocess, "run", fake_run)
    assert R._refresh_runner() is False
    assert "Not possible to fast-forward" in capsys.readouterr().out


def test_refresh_logs_timeout(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(R, "_refresh_manager", lambda: None)
    monkeypatch.setattr(R, "RUNNER_ROOT", tmp_path)

    def fake_run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 300)

    monkeypatch.setattr(R.subprocess, "run", fake_run)
    assert R._refresh_runner() is False
    assert "TimeoutExpired" in capsys.readouterr().out
