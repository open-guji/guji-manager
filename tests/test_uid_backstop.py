"""字格身份账兜底（11-25）：uidsync 单的规格、执行机铺 main 底后补入账。"""
from __future__ import annotations

import types

import pytest

from guji_manager.jobs import runner as R
from guji_manager.jobs import spec as SP

C1 = "a" * 40


def test_uidsync_spec():
    s = SP.normalize({"kind": "uidsync", "book": "10", "cv": C1, "base": "L1", "ws_glob": "988g3f0wsu-*"},
                     resolve=lambda r: C1)
    assert s["kind"] == "uidsync" and s["base"] == "L1" and s["output"]["pack"] is False and s["run"] is None
    h = SP.spec_hash(s)
    s2 = SP.normalize({"kind": "uidsync", "book": "10", "cv": C1, "base": "L2", "ws_glob": "988g3f0wsu-*"},
                      resolve=lambda r: C1)
    assert SP.spec_hash(s2) != h                       # 同册换了 main 标签是另一张单
    for bad in ({"base": "main"}, {"base": None}, {"base": "L1", "output": {"pack": True}}):
        with pytest.raises(SP.SpecError):
            SP.normalize({"kind": "uidsync", "book": "10", "cv": C1, "ws_glob": "988g3f0wsu-*", **bad},
                         resolve=lambda r: C1)


def _fake(base, fail=False):
    ev, calls = [], []

    def guji(*a, **k):
        calls.append((a, k))
        if fail:
            raise R.StageError("failed", "boom")
        return '{"status": "entered", "entered": 3}'
    return types.SimpleNamespace(spec={"book": "vol01", "base": base}, ws="/w", guji=guji,
                                 ev=lambda m, **k: ev.append((m, k))), ev, calls


def test_runner_uid_sync_after_main_base():
    f, ev, calls = _fake("main")
    R.Job.uid_sync(f)
    (args, kw), = calls
    assert args[:3] == ("uid", "sync", "vol01") and "--local" in args and "--label" not in args and kw["write"] is True
    f, ev, calls = _fake("L9")
    R.Job.uid_sync(f, strict=True)
    assert calls[0][0][-2:] == ("--label", "L9")
    f, ev, calls = _fake("main", fail=True)
    R.Job.uid_sync(f)                                   # rerun 里失败只记一笔
    assert ev and ev[-1][1].get("level") == "warn"
    with pytest.raises(R.StageError):
        R.Job.uid_sync(_fake("L9", fail=True)[0], strict=True)
