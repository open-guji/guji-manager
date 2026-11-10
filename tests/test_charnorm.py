"""归一表里每一对 (x, y)：(x,x)、(x,y)、(y,x) 行为必须一致，且 (x,y) 绝不产生复审／推翻（审视文档建议 6）。"""
import pytest

from guji_manager.charnorm import CharNorm, IDENT
from guji_manager.swap.overlay_edits import overlay
from guji_manager.swap.resolve import resolve, HUMAN_KEEP, SAME, PENDING_SAME, PROTECTED_CONFLICT, MACHINE_CHANGE

PAIRS = {"别": "別", "釆": "采", "宮": "宫"}
N = CharNorm(PAIRS)
ORDERED = [(x, y) for x, y in PAIRS.items()] + [(y, x) for x, y in PAIRS.items()]


def test_canon_and_ident():
    assert N.same("别", "別") and N.same("別", "别") and not N.same("官", "宮")
    assert not IDENT.same("别", "別") and IDENT.same("a", "a") and not N.same(None, "a")
    assert CharNorm({"甲": "乙", "乙": "丙"}).canon("甲") == "丙"
    assert CharNorm({"甲": "乙", "乙": "甲"}).canon("甲") in ("甲", "乙")   # 环不死循环


@pytest.mark.parametrize("x,y", ORDERED)
def test_resolve_pairs(x, y):
    assert resolve(x, x, x, same=N.same).kind == HUMAN_KEEP
    d = resolve(x, y, x, same=N.same)
    assert d.kind == HUMAN_KEEP and d.auto and d.action == "keep"
    d = resolve(x, y, None, same=N.same)
    assert d.kind == SAME
    d = resolve(x, y, None, new_pending=True, same=N.same)
    assert d.kind == PENDING_SAME
    # 不带 same：旧行为（字面比）
    assert resolve(x, y, x).kind == PROTECTED_CONFLICT or resolve(x, y, None).kind == MACHINE_CHANGE


@pytest.mark.parametrize("x,y", ORDERED)
def test_same_verdict_and_overlay(x, y):
    pytest.importorskip("open_guji_cv")      # feedback 包要 cv；执行机有
    from guji_manager.feedback.web_votes import same_verdict
    assert same_verdict({"v": "confirm", "shape": x}, {"v": "confirm", "shape": y}, N.same)
    assert not same_verdict({"v": "confirm", "shape": x}, {"v": "confirm", "shape": y})


@pytest.mark.parametrize("x,y", ORDERED)
def test_overlay_pairs(x, y):
    char = {"pages": [{"columns": [{"cells": [{"a": "1:1:1", "c": y}]}]}]}
    _, rep = overlay(char, [{"anchor": "1:1:1", "old": "旧", "new": x}], {"1:1:1": "1:1:1"}, N.same)
    assert len(rep.already) == 1 and not rep.overturned
