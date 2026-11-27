"""safe_checkout：checkout 遇未跟踪文件冲突时，只处理报出的文件、带时间戳备份到工作区外、日志记路径、不整仓 clean。"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from guji_manager.jobs import safe_checkout as SC


def _g(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """旧提交 A 不跟踪 models/m.pt；新提交 B 开始跟踪它。停在 A，本机有未跟踪的 models/m.pt（如从 R2 取回）。"""
    r = tmp_path / "seed"
    r.mkdir()
    _g(r, "init", "-q", "-b", "main")
    _g(r, "config", "user.email", "t@t")
    _g(r, "config", "user.name", "t")
    (r / "a.txt").write_text("a\n")
    _g(r, "add", ".")
    _g(r, "commit", "-qm", "A")
    _g(r, "tag", "A")
    (r / "models").mkdir()
    (r / "models" / "m.pt").write_text("tracked\n")
    (r / "fonts").mkdir()
    (r / "fonts" / "f.ttf").write_text("tracked font\n")
    _g(r, "add", ".")
    _g(r, "commit", "-qm", "B")
    _g(r, "tag", "B")
    _g(r, "checkout", "-q", "A")
    (r / "models").mkdir(exist_ok=True)
    (r / "models" / "m.pt").write_text("local copy\n")          # 冲突文件
    (r / "fonts").mkdir(exist_ok=True)
    (r / "fonts" / "f.ttf").write_text("local font\n")           # 冲突文件
    (r / "scratch.log").write_text("keep me\n")                  # 不冲突的未跟踪文件
    (r / "cache").mkdir()
    (r / "cache" / "x.bin").write_text("keep\n")                 # 不冲突的未跟踪目录
    return r


def test_conflict_paths_parses_git_message():
    err = ("error: The following untracked working tree files would be overwritten by checkout:\n"
           "\tmodels/m.pt\n\tfonts/f.ttf\n"
           "Please move or remove them before you switch branches.\nAborting\n")
    assert SC.conflict_paths(err) == ["models/m.pt", "fonts/f.ttf"]
    assert SC.conflict_paths("error: pathspec 'nope' did not match any file(s) known to git") == []


def test_only_reported_files_touched_no_clean(repo: Path, tmp_path: Path, monkeypatch):
    """第 1 条：只动报出的冲突文件；别的未跟踪文件、目录原样留着（不整仓 clean -f）。"""
    monkeypatch.setenv("GUJI_CHECKOUT_BAK", str(tmp_path / "bak"))
    moved = SC.checkout(repo, "B", say=lambda m: None)
    assert _g(repo, "rev-parse", "HEAD") == _g(repo, "rev-parse", "B")
    assert sorted(p.name for p in moved) == ["f.ttf", "m.pt"]
    assert (repo / "scratch.log").read_text() == "keep me\n"
    assert (repo / "cache" / "x.bin").read_text() == "keep\n"
    assert (repo / "models" / "m.pt").read_text() == "tracked\n"


def test_backup_outside_repo_with_timestamp(repo: Path, tmp_path: Path, monkeypatch):
    """第 2 条：先带时间戳备份到工作区外，内容原样；再切。"""
    bak = tmp_path / "bak"
    monkeypatch.setenv("GUJI_CHECKOUT_BAK", str(bak))
    moved = SC.checkout(repo, "B", say=lambda m: None)
    for p in moved:
        assert not p.resolve().is_relative_to(repo.resolve())
        assert p.resolve().is_relative_to(bak.resolve())
    stamp_dirs = list(bak.iterdir())
    assert len(stamp_dirs) == 1 and stamp_dirs[0].name[:8].isdigit() and "T" in stamp_dirs[0].name
    assert (stamp_dirs[0] / "seed" / "models" / "m.pt").read_text() == "local copy\n"
    assert (stamp_dirs[0] / "seed" / "fonts" / "f.ttf").read_text() == "local font\n"


def test_default_backup_root_outside_repo(repo: Path, tmp_path: Path, monkeypatch):
    monkeypatch.delenv("GUJI_CHECKOUT_BAK", raising=False)
    monkeypatch.setenv("GUJI_JOBS_HOME", str(tmp_path / "jobs-home"))
    assert SC.backup_root() == tmp_path / "jobs-home" / "checkout-bak"
    SC.checkout(repo, "B", say=lambda m: None)
    assert (tmp_path / "jobs-home" / "checkout-bak").is_dir()


def test_backup_path_logged(repo: Path, tmp_path: Path, monkeypatch):
    """第 3 条：日志里记下备份路径和动了哪些文件。"""
    bak = tmp_path / "bak"
    monkeypatch.setenv("GUJI_CHECKOUT_BAK", str(bak))
    said: list[str] = []
    SC.checkout(repo, "B", say=said.append)
    assert len(said) == 1
    stamp = next(bak.iterdir())
    assert str(stamp / "seed") in said[0]
    assert "models/m.pt" in said[0] and "fonts/f.ttf" in said[0]


def test_no_conflict_no_backup(repo: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GUJI_CHECKOUT_BAK", str(tmp_path / "bak"))
    (repo / "models" / "m.pt").unlink()
    (repo / "fonts" / "f.ttf").unlink()
    said: list[str] = []
    assert SC.checkout(repo, "B", say=said.append) == []
    assert said == [] and not (tmp_path / "bak").exists()


def test_other_errors_untouched(repo: Path, tmp_path: Path, monkeypatch):
    """不是未跟踪冲突的错（如改了已跟踪文件、ref 不存在）照原样失败，什么都不动。"""
    monkeypatch.setenv("GUJI_CHECKOUT_BAK", str(tmp_path / "bak"))
    with pytest.raises(SC.CheckoutError):
        SC.checkout(repo, "no-such-ref", say=lambda m: None)
    assert (repo / "models" / "m.pt").read_text() == "local copy\n"
    assert not (tmp_path / "bak").exists()


def test_unsafe_path_refuses_all(tmp_path: Path, monkeypatch):
    """报出的清单里有仓外路径就一个都不动。"""
    monkeypatch.setenv("GUJI_CHECKOUT_BAK", str(tmp_path / "bak"))
    r = tmp_path / "r"
    r.mkdir()
    (r / "ok.txt").write_text("x")
    assert not SC._safe_rel(r, "../ok.txt")
    assert not SC._safe_rel(r, "/etc/passwd")
    assert not SC._safe_rel(r, ".git/config")
    assert SC._safe_rel(r, "ok.txt")


def test_cli(repo: Path, tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("GUJI_CHECKOUT_BAK", str(tmp_path / "bak"))
    assert SC.main([str(repo), "B"]) == 0
    assert "已备份到" in capsys.readouterr().err
    assert SC.main([str(repo), "no-such-ref"]) == 1


def test_runner_checkout_uses_safe_checkout(repo: Path, tmp_path: Path, monkeypatch):
    """执行方 Job.checkout（eval／command 单只切 cv）走同一套：冲突文件备份后切成，备份路径进事件。"""
    import threading

    from guji_manager.jobs import runner as R

    monkeypatch.setenv("GUJI_CHECKOUT_BAK", str(tmp_path / "bak"))
    monkeypatch.setattr(R, "SEED", repo)
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(repo), str(origin)], check=True)
    _g(repo, "remote", "add", "origin", str(origin))
    run = object.__new__(R.Job)
    run.spec, run.dry, run.cancel, run.proc, run.stage = {"cv": "B"}, False, threading.Event(), None, "prep"
    run.dir = tmp_path
    lines: list[str] = []
    events: list[str] = []
    run._w = lines.append
    run.ev = lambda m, **k: events.append(m)
    run.env = lambda **k: None
    run.progress = None
    run.checkout()
    assert _g(repo, "rev-parse", "HEAD") == _g(repo, "rev-parse", "B")
    assert events and str(tmp_path / "bak") in events[0]
    assert (repo / "scratch.log").exists()
