"""评测护栏（guji_manager.eval.guards，CV3 2026-11-23）：dataset guards/*.yaml 的读取与比对，自造数据。"""
import pytest

from guji_manager.eval.guards import GuardSummary, check_report, guards_for, load_guards
from guji_manager.eval.report import EvalReport, Metric
from guji_manager.eval import runner


def _ds(tmp_path, text):
    (tmp_path / "guards").mkdir()
    (tmp_path / "guards" / "read.yaml").write_text(text, encoding="utf-8")
    return tmp_path


YAML = """guards:
  - {eval: advset, book: 殿本, metric: 形近误认, dir: max, baseline: 34, limit: 37}
  - {eval: match_bench_qtw, book: 全唐文, metric: same 精度, dir: min, baseline: 99.83, limit: 99.5, lib: 995ejelvk0}
"""


def test_load_and_check_directions(tmp_path):
    gs = load_guards(_ds(tmp_path, YAML))
    assert [g.eval for g in gs] == ["advset", "match_bench_qtw"] and gs[1].lib == "995ejelvk0"
    ok = EvalReport("advset", "", metrics=[Metric("形近误认", 37)])
    bad = EvalReport("advset", "", metrics=[Metric("形近误认", 38)])
    assert check_report(ok, guards_for(gs, "advset"))[0].verdict == "pass"
    assert check_report(bad, guards_for(gs, "advset"))[0].verdict == "fail"
    low = EvalReport("match_bench_qtw", "", metrics=[Metric("same 精度", 99.4)])
    assert check_report(low, guards_for(gs, "match_bench_qtw"))[0].verdict == "fail"


def test_missing_metric_and_failed_run_never_pass(tmp_path):
    gs = load_guards(_ds(tmp_path, YAML))
    no = EvalReport("advset", "", metrics=[Metric("别的", 1)])
    dead = EvalReport("advset", "", status="failed")
    s = GuardSummary(check_report(no, gs[:1]) + check_report(dead, gs[:1]))
    assert [r.verdict for r in s.results] == ["missing", "unverified"] and not s.ok
    assert "不能发版" in s.table()


def test_bad_guard_raises(tmp_path):
    with pytest.raises(ValueError):
        load_guards(_ds(tmp_path, "guards:\n  - {eval: advset, metric: x, dir: up, limit: 1}\n"))


def test_runner_marks_regressed_when_guard_crossed(tmp_path):
    ds = _ds(tmp_path, YAML)
    rep = EvalReport("advset", "", metrics=[Metric("形近误认", 40)])
    runner._apply_guards(rep, ds)
    assert rep.status == "regressed" and rep.gate == "失败" and rep.guards[0]["verdict"] == "fail"
    rep2 = EvalReport("rare_qtw", "", metrics=[Metric("x", 1)])
    runner._apply_guards(rep2, ds)
    assert rep2.status == "ok" and rep2.guards == []
