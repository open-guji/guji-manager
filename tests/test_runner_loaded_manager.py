"""执行方自更新比「本进程载入的代码」和 origin/main，不比磁盘（11-28 worker-6：准备脚本把磁盘切到 0.7.16，
进程仍是 0.7.14，旧自更新判「没过期」不 exec，于是不认 manager_min 照领 #18377/#18378）。"""
import subprocess

from guji_manager.jobs import runner as R


def _git(root, *a):
    return subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True, text=True).stdout.strip()


def _commit(root, text):
    (root / "guji_manager" / "__init__.py").write_text(text)
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", text)


def _setup(tmp_path, monkeypatch):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    seed = tmp_path / "seed"
    (seed / "guji_manager").mkdir(parents=True)
    _git(tmp_path, "init", "-q", "-b", "main", str(seed))
    _commit(seed, "v1")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-q", "origin", "main")
    monkeypatch.setattr(R, "MANAGER_ROOT", seed)
    monkeypatch.setattr(R, "_managed", lambda: True)
    monkeypatch.setattr(R, "_LOADED_MANAGER_TREE", None)
    return origin, seed


def _publish_v2(tmp_path, origin):
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
    _commit(other, "v2")
    _git(other, "push", "-q", "origin", "main")


def test_outdated_when_disk_moved_but_process_old(tmp_path, monkeypatch):
    origin, seed = _setup(tmp_path, monkeypatch)
    R._remember_loaded_manager()                 # 进程起来时载入 v1
    assert R._manager_outdated() is False
    _publish_v2(tmp_path, origin)
    # 准备脚本（ensure_manager）把磁盘检出切到 main：磁盘＝origin/main，进程还是 v1
    _git(seed, "fetch", "-q", "origin", "main")
    _git(seed, "checkout", "-q", "--detach", "FETCH_HEAD")
    assert R._manager_outdated() is True


def test_not_outdated_after_reexec(tmp_path, monkeypatch):
    origin, seed = _setup(tmp_path, monkeypatch)
    _publish_v2(tmp_path, origin)
    _git(seed, "fetch", "-q", "origin", "main")
    _git(seed, "checkout", "-q", "--detach", "FETCH_HEAD")
    R._remember_loaded_manager()                 # exec 后新进程载入 v2
    assert R._manager_outdated() is False


def test_falls_back_to_disk_head_when_not_recorded(tmp_path, monkeypatch):
    origin, _seed = _setup(tmp_path, monkeypatch)
    assert R._manager_outdated() is False
    _publish_v2(tmp_path, origin)
    assert R._manager_outdated() is True          # 磁盘 v1、origin v2：照旧判过期
