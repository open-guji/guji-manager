"""`guji <步> <命令> …` 步骤前缀（steps.py，用户 2026-11-22 定）。"""
from __future__ import annotations

import pytest

from guji_manager import steps
from guji_manager.commands import COMMANDS


def test_route_strips_prefix_for_member():
    assert steps.route(["start", "source", "pull", "vol01", "-w", "ws"]) == ["source", "pull", "vol01", "-w", "ws"]
    assert steps.route(["feedback", "pending", "--json"]) == ["pending", "--json"]


def test_route_leaves_non_step_and_real_pipeline_alone():
    assert steps.route(["db", "sync"]) is None
    assert steps.route([]) is None
    assert steps.route(["pipeline", "keben_body_v2", "vol01", "-w", "ws"]) is None   # 跑管线
    assert steps.route(["pipeline", "-h"]) is None                                   # cv 的帮助
    assert steps.route(["pipeline", "seg", "check"]) == ["seg", "check"]


def test_route_rejects_command_of_other_step(capsys):
    with pytest.raises(SystemExit) as e:
        steps.route(["text", "source", "pull"])
    assert e.value.code == 2 and "guji start source" in capsys.readouterr().err


def test_route_lists_step_commands(capsys):
    with pytest.raises(SystemExit) as e:
        steps.route(["text", "commands"])
    assert e.value.code == 0 and "final-review" in capsys.readouterr().out


def test_every_member_belongs_to_one_step_and_deleted_ones_are_gone():
    members = [c for _, _, cs in steps.STEPS.values() for c in cs]
    assert len(members) == len(set(members))
    for gone in ("deploy", "release", "batch", "label-batch", "cards", "store"):
        assert gone not in COMMANDS and gone not in steps.STEP_OF
    manager_only = set(COMMANDS) - set(steps.STEPS) - {"db", "archive", "snap", "central-gc", "datastore"}
    assert manager_only <= set(steps.STEP_OF), sorted(manager_only - set(steps.STEP_OF))
