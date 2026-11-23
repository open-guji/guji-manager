"""runner 自更新失败要留下原因，不再静默。"""
import subprocess

from guji_manager.jobs import runner as R


def test_refresh_logs_merge_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(R, "_refresh_manager", lambda: True)
    monkeypatch.setattr(R, "RUNNER_ROOT", tmp_path)

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="fatal: Not possible to fast-forward, aborting.")

    monkeypatch.setattr(R.subprocess, "run", fake_run)
    assert R._refresh_runner() is False
    assert "Not possible to fast-forward" in capsys.readouterr().out


def test_refresh_logs_timeout(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(R, "_refresh_manager", lambda: True)
    monkeypatch.setattr(R, "RUNNER_ROOT", tmp_path)

    def fake_run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 300)

    monkeypatch.setattr(R.subprocess, "run", fake_run)
    assert R._refresh_runner() is False
    assert "TimeoutExpired" in capsys.readouterr().out


def test_refresh_detaches_when_clean(monkeypatch, tmp_path, capsys):
    """ff 失败（HEAD 在别的提交上）但工作区干净：切到 origin/dev。"""
    monkeypatch.setattr(R, "_refresh_manager", lambda: True)
    monkeypatch.setattr(R, "RUNNER_ROOT", tmp_path)
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd[3])
        if cmd[3] == "merge":
            return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="fatal: Not possible to fast-forward")
        if cmd[3] == "symbolic-ref":
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")      # detached HEAD
        if cmd[3] == "status":
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[3] == "checkout":
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="abc123\n", stderr="")

    monkeypatch.setattr(R.subprocess, "run", fake_run)
    assert R._refresh_runner() is True
    assert "checkout" in calls


def test_refresh_keeps_dirty_checkout(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(R, "_refresh_manager", lambda: True)
    monkeypatch.setattr(R, "RUNNER_ROOT", tmp_path)

    def fake_run(cmd, **kw):
        if cmd[3] == "merge":
            return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="x")
        if cmd[3] == "symbolic-ref":
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
        if cmd[3] == "status":
            return subprocess.CompletedProcess(cmd, 0, stdout=" M foo.py\n", stderr="")
        raise AssertionError("不该走到这里")

    monkeypatch.setattr(R.subprocess, "run", fake_run)
    assert R._refresh_runner() is False
    assert "未提交改动" in capsys.readouterr().out
