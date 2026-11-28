"""执行方配 cv 改名版遇老册：先 `guji-cv decide migrate-name` 再跑 pipeline，不让收尾整册重算（CV4 11-28）。"""
import subprocess
import sys
from types import SimpleNamespace

from guji_manager.jobs import runner as R


def _job(tmp_path, cv_new: bool):
    j = object.__new__(R.Job)
    j.dry, j.dir, j.spec, j.ws = False, tmp_path, {"book": "03", "pipeline": "keben_body_v2"}, "/ws/x"
    j._cv_roots = lambda: (str(tmp_path / "products"), str(tmp_path / "feedback"))
    j.env = lambda write=False: {}
    j.calls, j.evs = [], []
    j.sh = lambda argv, **kw: j.calls.append(argv) or "03：migrated，3 页"
    j.ev = lambda msg, **kw: j.evs.append(msg)
    return j, (lambda *a, **kw: SimpleNamespace(returncode=0, stdout=("char_decide" if cv_new else "seed_admit") + "\n"))


def test_migrates_old_book_on_renamed_cv(tmp_path, monkeypatch):
    (tmp_path / "products" / "03" / "seed_admit").mkdir(parents=True)
    j, run = _job(tmp_path, True)
    monkeypatch.setattr(subprocess, "run", run)
    j._migrate_decide_name()
    # 不走 bin/guji-cv（#18361）；-w 必给（#18364）
    assert j.calls and j.calls[0][1:] == ["-m", "open_guji_cv", "decide", "migrate-name", "03", "-w", "/ws/x",
                                          "--pipeline", "keben_body_v2"]
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


def _fake_cv(root, active):
    core = root / "open_guji_cv" / "core"
    core.mkdir(parents=True)
    (root / "open_guji_cv" / "__init__.py").write_text("")
    (core / "__init__.py").write_text("")
    (core / "step.py").write_text("STEPS = {}\n")         # 和真 cv 一样：步模块没导入前注册表是空的
    if active:
        (core / "decide_names.py").write_text(f"ADMIT_STEP_ACTIVE = {active!r}\n")


def test_probe_reads_active_name_not_empty_registry(tmp_path):
    """11-28：原探针查 core.step.STEPS，裸导入时恒空，执行方配 v0.9.16 跑殿本 vol01 #18302 护栏没触发。"""
    for active, want in (("char_decide", "char_decide"), ("seed_admit", "seed_admit"), (None, "seed_admit")):
        root = tmp_path / str(active)
        _fake_cv(root, active)
        r = subprocess.run([sys.executable, "-I", "-c", "import sys;sys.path.insert(0, sys.argv[1]);exec(sys.argv[2])",
                            str(root), R.DECIDE_NAME_PROBE],
                           capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == want


import pytest


@pytest.mark.parametrize("extra", [
    {},                                                             # 整册
    {"pages": "1,5,8"},                                             # 带 --pages 的回放单
    {"book_id": "995ejelvk0"},                                      # 册号带书 id（全唐文 004，#18377）
    {"book_id": "995ejelvk0", "pages": "1-9", "pipeline": "solo_5b"},
    {"pipeline": None},                                             # 单上没写 pipeline：退回缺省
])
def test_migrate_always_passes_workspace(tmp_path, monkeypatch, extra):
    """各种单子形状下 migrate-name 都带 -w <工作区> 与 --pipeline（CV4 11-28：第三次在执行机上才暴露）。"""
    (tmp_path / "products" / "03" / "seed_admit").mkdir(parents=True)
    j, run = _job(tmp_path, True)
    j.spec.update(extra)
    monkeypatch.setattr(subprocess, "run", run)
    j._migrate_decide_name()
    argv = j.calls[0]
    assert argv[argv.index("-w") + 1] == "/ws/x"
    assert argv[argv.index("--pipeline") + 1] == (extra.get("pipeline", "keben_body_v2") or "keben_body_v2")


def test_migrate_refuses_without_workspace(tmp_path, monkeypatch):
    """没工作区不传 `-w ""`（cv 一样报缺 -w），直接判失败、说清原因。"""
    (tmp_path / "products" / "03" / "seed_admit").mkdir(parents=True)
    j, run = _job(tmp_path, True)
    j.ws = None
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(R.StageError, match="工作区"):
        j._migrate_decide_name()
    assert not j.calls
