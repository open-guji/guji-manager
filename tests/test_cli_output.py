"""第五步 `guji output …`：参数解析与转交（cv 原 Step9 搬来，11-23）。"""
from __future__ import annotations

import argparse

import pytest

from guji_manager import cli_output, steps


def _parse(argv):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command")
    cli_output.add_parser(sub)
    cli_output.add_collation_parser(sub)
    return ap.parse_args(argv)


def test_output_step_lists_both_commands():
    assert steps.STEP_OF["export"] == "output"
    assert steps.STEP_OF["collation-report"] == "output"


def test_collation_report_passes_options_through():
    a = _parse(["collation-report", "--book", "vol01", "--pages", "4-6"])
    assert a.rest == ["--book", "vol01", "--pages", "4-6"]


def test_wikisource_forwards_own_args(monkeypatch):
    got = {}
    import guji_manager.output.wikisource_export as ws
    monkeypatch.setattr(ws, "main", lambda argv: got.setdefault("argv", argv) and 0)
    a = _parse(["export", "--pages", "3-5", "wikisource", "bxgb", "-w", "/ws"])
    with pytest.raises(SystemExit):
        cli_output.cmd_export(a)
    assert got["argv"] == ["bxgb", "-w", "/ws", "--pages", "3-5"]


def test_reflow_does_not_touch_products(monkeypatch):
    got = {}
    import guji_manager.output.reflow as rf
    monkeypatch.setattr(rf, "main", lambda argv: got.setdefault("argv", argv) and 0)
    monkeypatch.setattr(cli_output, "_export_pages", lambda *a: pytest.fail("reflow 不该读产物"))
    a = _parse(["export", "reflow", "a.md", "--out", "o.md"])
    with pytest.raises(SystemExit):
        cli_output.cmd_export(a)
    assert got["argv"] == ["a.md", "--out", "o.md"]
