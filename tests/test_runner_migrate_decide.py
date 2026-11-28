"""执行方配 cv 改名版遇老册：先 `guji-cv decide migrate-name` 再跑 pipeline，不让收尾整册重算（CV4 11-28）。"""
import subprocess
from types import SimpleNamespace

from guji_manager.jobs import runner as R


def _job(tmp_path, cv_new: bool):
    j = object.__new__(R.Job)
    j.dry, j.dir, j.spec = False, tmp_path, {"book": "03"}
    j._cv_roots = lambda: (str(tmp_path / "products"), str(tmp_path / "feedback"))
    j.env = lambda write=False: {}
    j.calls, j.evs = [], []
    j.sh = lambda argv, **kw: j.calls.append(argv) or "03：migrated，3 页"
    j.ev = lambda msg, **kw: j.evs.append(msg)
    return j, (lambda *a, **kw: SimpleNamespace(returncode=0, stdout=f"{cv_new}\n"))


def test_migrates_old_book_on_renamed_cv(tmp_path, monkeypatch):
    (tmp_path / "products" / "03" / "seed_admit").mkdir(parents=True)
    j, run = _job(tmp_path, True)
    monkeypatch.setattr(subprocess, "run", run)
    j._migrate_decide_name()
    assert j.calls and j.calls[0][1:] == ["decide", "migrate-name", "03"]
    assert "原地改名" in j.evs[0]


def test_skips_when_cv_old_or_already_migrated(tmp_path, monkeypatch):
    (tmp_path / "products" / "03" / "seed_admit").mkdir(parents=True)
    j, run = _job(tmp_path, False)
    monkeypatch.setattr(subprocess, "run", run)
    j._migrate_decide_name()
    assert not j.calls                                     # 旧 cv：收尾还叫 seed_admit
    (tmp_path / "products" / "03" / "char_decide").mkdir()
    j, run = _job(tmp_path, True)
    monkeypatch.setattr(subprocess, "run", run)
    j._migrate_decide_name()
    assert not j.calls                                     # 已有新目录：不再迁（并存由 cv status 警告）
