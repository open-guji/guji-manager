"""护栏「未验证」按原因分开报、缺脚本提示 cv 版本、超时可配置（GM4 11-27 史記补跑 17 条只过 2）。自造数据。"""
import pytest

from guji_manager.eval import runner
from guji_manager.eval.guards import (
    GuardResult,
    GuardSummary,
    check_report,
    load_guards,
)
from guji_manager.eval.registry import EVALS, EvalSpec, find_eval
from guji_manager.eval.report import EvalReport


def _repo(tmp_path, monkeypatch, scripts: dict[str, str]):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    for name, body in scripts.items():
        (repo / "scripts" / name).write_text(body, encoding="utf-8")
    monkeypatch.setattr(runner, "repo_root", lambda: repo)
    return repo


def _ds(tmp_path):
    d = tmp_path / "ds" / "fake-shard"
    d.mkdir(parents=True, exist_ok=True)
    (d / "items.jsonl").write_text('{"id":"a","expected":{"v":1}}\n', encoding="utf-8")
    return tmp_path / "ds"


def test_missing_script_says_which_cv_to_use(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch, {})
    monkeypatch.setitem(EVALS, "fake", EvalSpec(id="fake", script="eval_advset.py", shard="fake-shard", out_flag=""))
    r = runner.run_eval("fake", dataset_root=_ds(tmp_path))
    assert r.status == "failed" and r.fail_kind == "missing_script"
    assert "scripts/eval_advset.py" in r.error and "cv ≥0.9.2" in r.error and "v0.9.10" in r.error
    monkeypatch.setenv("GUJI_EVAL_CV_SUGGEST", "v0.9.12")
    assert "v0.9.12" in runner.run_eval("fake", dataset_root=_ds(tmp_path)).error


def test_timeout_is_its_own_reason(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch, {"eval_fake.py": "import time\ntime.sleep(5)\n"})
    monkeypatch.setitem(EVALS, "fake", EvalSpec(id="fake", script="eval_fake.py", shard="fake-shard", out_flag=""))
    r = runner.run_eval("fake", dataset_root=_ds(tmp_path), timeout_for={"fake": 1})
    assert r.status == "failed" and r.fail_kind == "timeout" and "--timeout-for fake=" in r.error


def test_missing_weight_gets_fetch_hint(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch, {"eval_fake.py": "import sys\nprint('FileNotFoundError: models/glyph_cnn_r5/model.pt')\nsys.exit(1)\n"})
    monkeypatch.setitem(EVALS, "fake", EvalSpec(id="fake", script="eval_fake.py", shard="fake-shard", out_flag=""))
    r = runner.run_eval("fake", dataset_root=_ds(tmp_path))
    assert r.fail_kind == "missing_asset" and "model fetch" in r.error
    assert "pull-rare-index" in runner.missing_asset_hint("找不到向量包 emb_unicode-cjk-ab.npz")
    assert runner.missing_asset_hint("ZeroDivisionError") == ""


def test_timeout_resolution_order(monkeypatch):
    rare, plain = find_eval("rare_shiji"), find_eval("advset")
    monkeypatch.delenv("GUJI_EVAL_TIMEOUT", raising=False)
    monkeypatch.delenv("GUJI_EVAL_TIMEOUT_FOR", raising=False)
    assert rare.timeout and runner.eval_timeout(rare) == rare.timeout > 900
    assert runner.eval_timeout(plain) == 900
    assert runner.eval_timeout(rare, 600) == 600                                   # 统一 --timeout 盖默认
    assert runner.eval_timeout(rare, 600, {"rare_": 3600}) == 3600                 # 前缀覆盖最优先
    assert runner.eval_timeout(rare, None, {"rare_*": 100, "rare_shiji": 200}) == 200
    monkeypatch.setenv("GUJI_EVAL_TIMEOUT_FOR", "rare_=4000")
    assert runner.eval_timeout(rare) == 4000 and runner.eval_timeout(plain) == 900
    monkeypatch.setenv("GUJI_EVAL_TIMEOUT", "1200")
    assert runner.eval_timeout(plain) == 1200
    with pytest.raises(ValueError):
        runner.parse_timeout_for(["rare_:3600"])


def test_summary_splits_unverified_by_reason(tmp_path):
    (tmp_path / "guards").mkdir()
    (tmp_path / "guards" / "x.yaml").write_text(
        "guards:\n  - {eval: advset, metric: m, dir: max, limit: 1}\n"
        "  - {eval: rare_shiji, metric: m, dir: min, limit: 1}\n", encoding="utf-8")
    g1, g2 = load_guards(tmp_path)
    s = GuardSummary(check_report(EvalReport("advset", "", status="failed", fail_kind="missing_script"), [g1])
                     + check_report(EvalReport("rare_shiji", "", status="failed", fail_kind="timeout"), [g2])
                     + [GuardResult(g1, None, "unverified", why="missing_lib")])
    assert s.unverified_by_why() == {"missing_script": 1, "timeout": 1, "missing_lib": 1}
    t = s.table()
    assert "未验证 3（缺库 1／缺脚本 1／超时 1）" in t and "cv ≥0.9.2" in t and "--timeout-for" in t
    assert "model fetch" in t                                                       # 缺库提示顺带补权重／索引
    assert s.results[0].to_dict()["why"] == "missing_script" and not s.ok
