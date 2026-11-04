"""跑批耗时统计 `core/perf.py`：span／count 的累加与空操作，引擎串行与并行都写出 perf 文件。"""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from pydantic import BaseModel

import open_guji_cv.steps  # noqa: F401  —— 注册 raw_page 等产物种类
from open_guji_cv.core import perf
from open_guji_cv.core.book import BookSpec
from open_guji_cv.core.engine import Engine
from open_guji_cv.core.pipeline import Pipeline
from open_guji_cv.core.spec import ProductKindSpec, StepSpec
from open_guji_cv.core.step import KINDS, STEPS, Step, register_kind, register_step
from open_guji_cv.products.cache import ImageCache
from open_guji_cv.products.store import ProductStore


class PerfP(BaseModel):
    page: int


class NoParams(BaseModel):
    pass


if "t_perf" not in KINDS:
    register_kind(ProductKindSpec(id="t_perf", title="计时", storage="numeric", unit="page", schema=PerfP))

if "t_step_perf" not in STEPS:
    @register_step
    class StepPerfT(Step):
        spec = StepSpec(id="t_step_perf", title="合成计时步", version="1", unit="page",
                        consumes=("raw_page",), produces=("t_perf",), params=NoParams,
                        parallel_safe=True)

        def run_page(self, ctx, page):
            with perf.span("外"), perf.span("内"):
                perf.count("格", 3)
            return {"t_perf": PerfP(page=page)}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.delenv("GUJI_PERF", raising=False)
    monkeypatch.delenv("GUJI_PERF_DIR", raising=False)
    raw = tmp_path / "raw"
    raw.mkdir()
    rng = np.random.default_rng(0)
    for pg in (1, 2, 3):
        cv2.imwrite(str(raw / f"{pg}.png"), rng.integers(0, 255, (20, 20), dtype=np.uint8))
    book = BookSpec(id="tperf", title="t", raw_dir=raw)
    pl = Pipeline(id="t_perf_pl", title="t", steps=["t_step_perf"])
    pl.validate()
    return book, pl, tmp_path


def test_push_rows_and_never_neon(world, monkeypatch):
    """推送只走美国机任务库：没设 JOBSDB_TOKEN 时 push_file 什么也不做、不连库；行的转换对得上。"""
    from open_guji_cv.jobs import store
    from guji_manager.jobs import perf_push
    book, pl, tmp = world
    monkeypatch.setenv("GUJI_JOB_ID", "77")
    eng = Engine(book, pl, store=ProductStore(tmp / "products"), cache=ImageCache(tmp / "cache"), log=lambda s: None)
    eng.run(pages=[1, 2, 3])
    (f,) = (tmp / "perf" / "tperf").glob("*.jsonl")
    head, steps = perf_push.rows(f)
    assert head["job_id"] == 77 and head["book"] == "tperf" and head["wall_s"] is not None
    assert [s["step"] for s in steps] == ["t_step_perf"] and steps[0]["ok"] == 3

    monkeypatch.delenv("JOBSDB_TOKEN", raising=False)
    monkeypatch.setattr(store, "connect", lambda: pytest.fail("没开美国机任务库时不许连库（会连到 Neon）"))
    assert perf_push.push_file(f) is False
    assert not f.with_suffix(".pushed").exists()
    assert perf_push.pending(tmp / "perf") == [f]
    with pytest.raises(SystemExit):
        perf_push.push_pending(tmp / "perf")
