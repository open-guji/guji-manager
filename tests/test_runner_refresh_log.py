"""runner 自更新失败要留下原因，不再静默。"""
import subprocess

from guji_manager.jobs import runner as R


def _sub(cmd):
    """git 子命令（跳过 -c 选项、-C 仓目录；safe_checkout 带 -c core.quotePath=false）。"""
    return cmd[cmd.index("-C") + 2]


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
        calls.append(_sub(cmd))
        if _sub(cmd) == "merge":
            return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="fatal: Not possible to fast-forward")
        if _sub(cmd) == "symbolic-ref":
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")      # detached HEAD
        if _sub(cmd) == "status":
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if _sub(cmd) == "checkout":
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="abc123\n", stderr="")

    monkeypatch.setattr(R.subprocess, "run", fake_run)
    assert R._refresh_runner() is True
    assert "checkout" in calls


def test_refresh_keeps_dirty_checkout(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(R, "_refresh_manager", lambda: True)
    monkeypatch.setattr(R, "RUNNER_ROOT", tmp_path)

    def fake_run(cmd, **kw):
        if _sub(cmd) == "merge":
            return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="x")
        if _sub(cmd) == "symbolic-ref":
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
        if _sub(cmd) == "status":
            return subprocess.CompletedProcess(cmd, 0, stdout=" M foo.py\n", stderr="")
        raise AssertionError("不该走到这里")

    monkeypatch.setattr(R.subprocess, "run", fake_run)
    assert R._refresh_runner() is False
    assert "未提交改动" in capsys.readouterr().out


def _g(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def _cv_with_new_tracked(tmp_path):
    """origin/dev 新提交开始跟踪 config/groups/wu/rules.yaml；执行方检出停在旧提交、本地有同名未跟踪文件（11-27 worker-24）。"""
    origin = tmp_path / "origin"
    origin.mkdir()
    _g(origin, "init", "-q", "-b", "dev")
    _g(origin, "config", "user.email", "t@t")
    _g(origin, "config", "user.name", "t")
    (origin / "a.txt").write_text("a\n")
    _g(origin, "add", ".")
    _g(origin, "commit", "-qm", "A")
    work = tmp_path / "cv"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
    (origin / "config" / "groups" / "wu").mkdir(parents=True)
    (origin / "config" / "groups" / "wu" / "rules.yaml").write_text("tracked\n")
    _g(origin, "add", ".")
    _g(origin, "commit", "-qm", "B")
    _g(work, "fetch", "-q", "origin")
    (work / "config" / "groups" / "wu").mkdir(parents=True)
    (work / "config" / "groups" / "wu" / "rules.yaml").write_text("local\n")
    (work / "scratch.log").write_text("keep\n")
    return work


def test_refresh_merge_moves_untracked_conflict(monkeypatch, tmp_path, capsys):
    """分支上 ff 被未跟踪文件挡：备份移走那一个再 ff，别的未跟踪文件不动。"""
    work = _cv_with_new_tracked(tmp_path)
    monkeypatch.setattr(R, "_refresh_manager", lambda: True)
    monkeypatch.setattr(R, "RUNNER_ROOT", work)
    monkeypatch.setenv("GUJI_CHECKOUT_BAK", str(tmp_path / "bak"))
    assert R._refresh_runner() is True
    assert _g(work, "rev-parse", "HEAD") == _g(work, "rev-parse", "origin/dev")
    assert (work / "config/groups/wu/rules.yaml").read_text() == "tracked\n"
    assert (work / "scratch.log").read_text() == "keep\n"
    baks = list((tmp_path / "bak").rglob("rules.yaml"))
    assert len(baks) == 1 and baks[0].read_text() == "local\n"
    assert "[safe_checkout]" in capsys.readouterr().out


def test_refresh_detach_moves_untracked_conflict(monkeypatch, tmp_path, capsys):
    """detached HEAD 不在 origin/dev 线上（上一单钉的 cv）：退一步 checkout --detach 也让路。"""
    work = _cv_with_new_tracked(tmp_path)
    _g(work, "checkout", "-q", "--detach", "HEAD")
    (work / "side.txt").write_text("s\n")
    _g(work, "-c", "user.email=t@t", "-c", "user.name=t", "add", "side.txt")
    _g(work, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "side")
    monkeypatch.setattr(R, "_refresh_manager", lambda: True)
    monkeypatch.setattr(R, "RUNNER_ROOT", work)
    monkeypatch.setenv("GUJI_CHECKOUT_BAK", str(tmp_path / "bak"))
    assert R._refresh_runner() is True
    assert _g(work, "rev-parse", "HEAD") == _g(work, "rev-parse", "origin/dev")
    out = capsys.readouterr().out
    assert "已切到 origin/dev" in out and "[safe_checkout]" in out
