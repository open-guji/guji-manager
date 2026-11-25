"""耗时统计按 cv 四大步分组、冷缓存再生、任务阶段与准备分段（2026-11-25 重整）。"""
from __future__ import annotations

import datetime as dt
import json

import pytest

from guji_manager import cli_perf
from guji_manager.jobs import d1, perf_push, runner
from guji_manager.jobs import store as S


def test_stage_map_covers_pipeline_steps_and_gates():
    m = cli_perf.stage_map()
    assert m["border_detect"] == "layout" and m["border_detect_gate"] == "layout"     # 闸归它挂的那一步
    assert m["column_band"] == "cut" and m["column_end"] == "cut" and m["cut_gate"] == "cut"
    assert m["glyph_match"] == "read" and m["rare_candidates"] == "read"
    assert m["seed_admit"] == "decide"
    assert m["row_segment_gate"] == "cut"                                              # 已退役的仍归对


def test_every_pipeline_step_has_a_stage():
    from open_guji_cv.core.pipeline import list_pipelines, load_pipeline
    m = cli_perf.stage_map()
    missing = sorted({s for pid in list_pipelines() for s in load_pipeline(pid).steps if s not in m})
    assert not missing, f"这些步不在任何大步里（管线骨架 stages: 漏了？）：{missing}"


def test_by_stage_groups_in_pipeline_order():
    rows = [{"step": "seed_admit", "wall_s": 5}, {"step": "row_segment", "wall_s": 3},
            {"step": "t_x", "wall_s": 1}, {"step": "cell_shrink", "wall_s": 4}]
    g = cli_perf._by_stage(rows)
    assert [s for s, _, _ in g] == ["cut", "decide", cli_perf.OTHER]
    assert g[0][1] == 7 and [r["step"] for r in g[0][2]] == ["cell_shrink", "row_segment"]


def test_regen_takes_outermost_render_only():
    spans = {"glyph_match._patch": 10.0,
             "glyph_match._patch/RunContext.image": 9.0,
             "glyph_match._patch/RunContext.image/CellShrinkStep.render": 8.0,
             "glyph_match._patch/RunContext.image/CellShrinkStep.render/RunContext.image/ColumnWarpStep.render": 5.0,
             "ColumnWarpStep.render": 1.0}
    assert cli_perf.regen_of(spans) == {"CellShrinkStep.render": 8.0, "ColumnWarpStep.render": 1.0}


def test_render_hooks_listed_from_steps():
    h = cli_perf._render_hooks()
    assert h["open_guji_cv.steps.cell_shrink"]["methods"]["CellShrinkStep"] == ("render",)
    allh = cli_perf.all_hooks()        # 与 PERF_HOOKS 同模块的合并，不丢原有的
    assert "_column_chars" in allh["open_guji_cv.steps.cell_shrink"]["methods"]["CellShrinkStep"]
    assert "render" in allh["open_guji_cv.steps.cell_shrink"]["methods"]["CellShrinkStep"]


def test_no_push_under_pytest(monkeypatch):
    monkeypatch.setattr(S, "enabled", lambda: True)
    assert perf_push.enabled() is False          # PYTEST_CURRENT_TEST 在：测试不往正式任务库推
    monkeypatch.setenv("GUJI_PERF_PUSH_IN_TESTS", "1")
    assert perf_push.enabled() is True


def test_prep_parts_parses_summary():
    out = "== cv\n...\n== 准备耗时\n" + "%-14s %4ss\n" % ("cv", 3) + "%-14s %4ss\n" % ("db-pull", 120) \
          + "%-14s %4ss\n" % ("db-pull", 5) + "%-14s %4ss\n" % ("取原图", 40) + "之后的命令先 source ~/.guji_env\n"
    assert runner.prep_parts(out) == {"cv": 3, "db-pull": 125, "取原图": 40}
    assert runner.prep_parts("老脚本没有分段") == {}


@pytest.fixture()
def conn(monkeypatch):
    c = d1.connect({"driver": "sqlite", "path": ":memory:"})

    class Keep:                        # 查询用完会 close，别关掉测试的库
        is_d1 = True
        q = staticmethod(c.q)

        def close(self):
            pass
    monkeypatch.setattr(S, "connect", lambda: Keep())
    yield c
    c.close()


def test_remote_phases_spans_and_prep_parts_on_d1(conn):
    j = S.submit(conn, {"kind": "rerun", "book": "vol01", "steps": {"from": "seg", "to": "seg"}, "cv_ref": "abcdef12",
                        "pages": "all"}, "h1", by="CV0", why="测")["id"]
    for stage, secs, data in (("prep", 100.0, None), ("prep", None, {"prep_parts": {"db-pull": 60, "cv": 3}}),
                              ("run", 900.0, None), ("run", 300.0, None)):
        S.event(conn, j, None, stage, "x", secs=secs, data=data)
    ph = {p["stage"]: p for p in perf_push.remote_phases(1)}
    assert ph["run"]["secs"] == 1200.0 and ph["run"]["n"] == 2 and ph["prep"]["secs"] == 100.0
    assert perf_push.remote_phases(1, book="vol02") == []
    parts = perf_push.remote_prep_parts(1)
    assert [(p["part"], p["secs"]) for p in parts] == [("db-pull", 60), ("cv", 3)]

    t = dt.datetime.now(dt.timezone.utc)
    head = {"run_id": "r1", "grp": None, "book": "vol01", "book_id": None, "pipeline": "p", "steps": ["glyph_match"],
            "n_pages": 2, "jobs": 1, "force": False, "job_id": j, "cv_version": "0.9.0", "cv_commit": "x",
            "host": "h", "machine": "{}", "argv": "[]", "started_at": t, "finished_at": t, "wall_s": 9.0,
            "stopped": False}
    step = {"run_id": "r1", "step": "glyph_match", "pages": 2, "ok": 2, "skipped": 0, "failed": 0, "jobs": 1,
            "wall_s": 9.0, "compute_s": 8.0, "p50_s": 4.0, "p90_s": 4.0, "max_s": 4.0, "parallel_eff": None,
            "cpu_s": 1.0, "child_cpu_s": 0.0, "peak_rss_mb": 100, "overhead": None, "counts": None, "slowest": "[]",
            "spans": json.dumps({"glyph_match._patch": [10, 4.0, 3.9],
                                 "glyph_match._patch/RunContext.image/CellShrinkStep.render": [3, 2.5, 2.4]})}
    perf_push._push_d1(conn, head, [step])
    sp = perf_push.remote_spans(1, "glyph_match")["glyph_match"]
    assert sp["ok"] == 2 and sp["spans"]["glyph_match._patch"] == 4.0
    assert cli_perf.regen_of(sp["spans"]) == {"CellShrinkStep.render": 2.5}
