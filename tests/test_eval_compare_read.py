"""评测套展开与两次结果对比（A23，2026-11-23）。"""
import json

import pytest

from guji_manager.eval.compare import compare_dirs
from guji_manager.eval.registry import EVALS, SUITES, expand_suites
from guji_manager.eval.report import EvalReport, Metric


def test_suites_expand_and_ids_exist():
    assert expand_suites(["@read-3a", "advset"])[0] == "advset"
    assert len(expand_suites(["@read-3a", "advset"])) == len(SUITES["read-3a"])
    for ids in SUITES.values():
        assert set(ids) <= set(EVALS)
    with pytest.raises(SystemExit):
        expand_suites(["@nope"])


def test_compare_metrics_flips_and_lock(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir(); new.mkdir()
    o = EvalReport(eval_id="advset_shiji", shard="x", metrics=[Metric(name="形近误认", value=7)],
                   lock={"cv": "aaa"})
    (old / "advset_shiji.report.json").write_text(json.dumps(o.to_dict()), encoding="utf-8")
    (old / "advset_shiji.json").write_text(json.dumps({"flips": {"cov|形近": ["q1", "q2"]}}), encoding="utf-8")
    (new / "advset_shiji.json").write_text(json.dumps({"flips": {"cov|形近": ["q2", "q3"]}}), encoding="utf-8")
    n = EvalReport(eval_id="advset_shiji", shard="x", metrics=[Metric(name="形近误认", value=5)],
                   lock={"cv": "bbb"})
    txt = compare_dirs(old, [n], new)
    assert "7→5" in txt and "钉版不同" in txt
    assert "新错 1、改对 1" in txt and "+ q3" in txt and "- q1" in txt
