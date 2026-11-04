"""切分样页单与对比命令（切分模块化第 4 步）：每套书都有一份能读的样页单，牵动判断按套书分得开。"""

from cv_paths import CV_REPO  # cv 仓根（本测试从 cv tests/ 搬来）
import importlib.util
from pathlib import Path

import pytest

from open_guji_cv.core.seg_set import SEG_SETS
from guji_manager.jobs import spec as SP

_spec = importlib.util.spec_from_file_location(
    "seg_samples", CV_REPO / "scripts" / "seg_samples.py")
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

P = "open_guji_cv."


def test_job_specs_normalize():
    for seg_set in SEG_SETS:
        for old, new in S.job_specs(seg_set, "a" * 40, "b" * 40, "单测"):
            o = SP.normalize(old, resolve=lambda r: r)
            n = SP.normalize({**new, "compare_to": {"job": 1}}, resolve=lambda r: r)
            assert o["kind"] == "rerun" and o["output"]["pack"] and o["force"]
            assert n["kind"] == "ab" and n["pages"] == o["pages"] and n["steps"] == o["steps"]
            assert SP.spec_hash(o) != SP.spec_hash(n)
