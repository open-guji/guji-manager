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
    """改名版把本体搬到 steps.char_decide 后，钩子在新模块上只挂真有的函数；兼容版的转发入口一个也不挂。"""
    import importlib
    import importlib.util
    import sys
    import types

    from guji_manager import cli_perf
    fake = types.ModuleType("open_guji_cv.steps.char_decide")
    fake._opt = lambda: None
    real_spec, real_imp = importlib.util.find_spec, importlib.import_module
    monkeypatch.setitem(sys.modules, "open_guji_cv.steps.char_decide", fake)
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda n, *a: object() if n == "open_guji_cv.steps.char_decide" else real_spec(n, *a))
    h = cli_perf.all_hooks()
    assert h["open_guji_cv.steps.char_decide"]["funcs"] == ("_opt",)
    assert cli_perf.RETIRED_STAGE["seed_admit"] == "decide"


def _manifest_line(key, elapsed):
    import json
    return json.dumps({"key": key, "status": "ok", "elapsed": elapsed, "fingerprint": "x"}) + "\n"


def test_throughput_timing_counts_decide_once(tmp_path):
    """新旧目录并存（migrate-name 后旧目录残留）：step_timing 只出 char_decide 一行。"""
    from guji_manager._cv import ProductStore
    from guji_manager.eval.throughput import step_timing
    for s in ("seed_admit", "char_decide"):
        d = tmp_path / "b" / s
        d.mkdir(parents=True)
        (d / "_manifest.jsonl").write_text(_manifest_line("p0001", 1.0) + _manifest_line("p0002", 2.0), encoding="utf-8")
    rows = {r["step"]: r for r in step_timing("b", ProductStore(tmp_path))["steps"]}
    assert "seed_admit" not in rows and rows["char_decide"]["n_pages"] == 2


def test_fetch_steps_extracts_both_names_reader_picks_new(tmp_path):
    """取包 steps 过滤把两名都解出来；读端 decide_dir 以 char_decide/ 为准，不会两份都读。"""
    import io
    import tarfile

    from guji_manager.products_io import DECIDE_STEPS, decide_pages, is_decide_step
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name in ("b/seed_admit/p0001.json", "b/char_decide/p0001.json", "b/row_segment/p0001.json"):
            data = b"{}"
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
    buf.seek(0)
    want = {"seed_admit", "align_ref"}
    if any(is_decide_step(s) for s in want):
        want |= set(DECIDE_STEPS)
    from pathlib import Path
    with tarfile.open(fileobj=buf, mode="r:gz") as tf:
        mem = [m for m in tf.getmembers() if Path(m.name).parts[1] in want]
        tf.extractall(tmp_path, members=mem, filter="data")
    assert (tmp_path / "b" / "seed_admit").is_dir() and not (tmp_path / "b" / "row_segment").exists()
    assert [p.parent.name for p in decide_pages(tmp_path, "b")] == ["char_decide"]
