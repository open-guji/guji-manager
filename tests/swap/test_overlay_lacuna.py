"""人改字叠到新包：新包这格是 □ 阙文时，改成字要去掉 lacuna（sheldon 11-18：只有真的阙字才显示阙文）。"""
from guji_manager.swap.overlay_edits import overlay


def _char(cells):
    return {"pages": [{"page": 1, "columns": [{"col": 1, "cells": cells}]}]}


def test_overlay_drops_lacuna_when_edit_fills_blank():
    char = _char([{"a": "1:1:1", "c": "□", "lacuna": True}, {"a": "1:1:2", "c": "□", "lacuna": True, "guess_c": "日"},
                  {"a": "1:1:3", "c": "甲"}])
    edits = [{"anchor": "1:1:1", "old": "□", "new": "官"},          # applied
             {"anchor": "1:1:2", "old": "曰", "new": "日"}]         # overturned（机器现是 □）
    out, rep = overlay(char, edits, {"1:1:1": "1:1:1", "1:1:2": "1:1:2"})
    cells = out["pages"][0]["columns"][0]["cells"]
    assert cells[0] == {"a": "1:1:1", "c": "官"}
    assert cells[1] == {"a": "1:1:2", "c": "日"}
    assert len(rep.applied) == 1 and len(rep.overturned) == 1


def test_overlay_edit_to_blank_keeps_flags():
    char = _char([{"a": "1:1:1", "c": "甲", "lacuna": True}])
    out, _ = overlay(char, [{"anchor": "1:1:1", "old": "甲", "new": "□"}], {"1:1:1": "1:1:1"})
    assert out["pages"][0]["columns"][0]["cells"][0] == {"a": "1:1:1", "c": "□", "lacuna": True}
