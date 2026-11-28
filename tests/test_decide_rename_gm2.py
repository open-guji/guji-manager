# -*- coding: utf-8 -*-
"""cv P3 seed_admit→char_decide：GM2 名下读口两名并认（冻结比对、包导入降级检查、按页重放、取包、perf）。"""
from __future__ import annotations

import hashlib

from guji_manager.jobs.auto_pages import REPLAY_FROM
from guji_manager.ops.freeze import compare_products
from guji_manager.snap.importer import downgraded_steps


def test_freeze_compare_follows_rename(tmp_path):
    data = b'{"seed_admit": {}}'
    base = {"files": {"products/b/seed_admit/p0001.json": {"sha256": hashlib.sha256(data).hexdigest()}}}
    d = tmp_path / "b" / "char_decide"
    d.mkdir(parents=True)
    (d / "p0001.json").write_bytes(data)                 # migrate-name 原地改名后
    r = compare_products(base, tmp_path)
    assert r["same"] == 1 and not r["missing"] and not r["changed"]


def test_downgrade_check_across_names():
    before = {"char_decide": {"fresh": 10}}
    assert downgraded_steps(before, {"char_decide": {"fresh": 10}}, ["seed_admit"]) == {}
    assert downgraded_steps(before, {"char_decide": {"fresh": 7}}, ["seed_admit"]) == {"seed_admit": "新鲜 10 → 7"}


def test_replay_from_both_names():
    assert "seed_admit" in REPLAY_FROM and "char_decide" in REPLAY_FROM


def test_perf_hooks_mirror_new_module(monkeypatch):
    import importlib.util

    from guji_manager import cli_perf
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda n, *a: object() if n.startswith("open_guji_cv.steps.char_decide") else real(n, *a))
    h = cli_perf.all_hooks()
    assert h["open_guji_cv.steps.char_decide"]["funcs"] == h["open_guji_cv.steps.seed_admit"]["funcs"]
    assert cli_perf.RETIRED_STAGE["seed_admit"] == "decide"
