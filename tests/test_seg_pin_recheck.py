"""无几何底老钉子批量重核（CV1 11-26）。"""
from types import SimpleNamespace as NS

import numpy as np

from guji_manager import _cv
from guji_manager import seg_pin as sp
from guji_manager import seg_pin_recheck as rc

PIN = [{"slot": 1, "kind": "char", "x0": 10.0, "x1": 90.0, "y0": 10.0, "y1": 90.0},
       {"slot": 2, "kind": "char", "x0": 10.0, "x1": 90.0, "y0": 100.0, "y1": 180.0}]


def _cell(c, **kw):
    return NS(**{"sub": None, **c, **kw})


def _col(flags=("roster", "manual_cells"), cells=PIN):
    return NS(col=3, flags=list(flags), cells=[_cell(c) for c in cells], period=80.0)


def test_effective():
    assert rc.effective(PIN, _col())[0]
    assert not rc.effective(PIN, None)[0]
    assert not rc.effective(PIN, _col(flags=()))[0]                          # 不是按钉子切的
    assert not rc.effective(PIN, _col(cells=PIN[:1]))[0]                     # 格号不同
    moved = [dict(PIN[0], y1=95.0), PIN[1]]
    assert not rc.effective(PIN, _col(cells=moved))[0]                       # 框不同
    assert rc.effective(PIN, _col(flags=("manual_cells", "manual_cells_remapped"), cells=moved))[0]


class _Store:
    def __init__(self, col):
        self.col = col

    def read(self, book, step, key, kind):
        if step == "row_segment":
            return NS(columns=[self.col])
        return None


def _item(cells=PIN):
    return {"id": "b:7:3", "anchor": {"book": "b", "page": 7, "col": 3}, "status": "active",
            "expected": {"cells": cells}, "input": {}, "history": []}


def _patch(monkeypatch, geo=(), uncov=()):
    gray = np.full((200, 100), 255, np.uint8)
    fns = {"check_pin_vs_chars": lambda pin, cc: [], "column_key": lambda p, c: f"{p}:{c}",
           "imread": lambda *a: gray, "page_key": lambda p: f"p{p:04d}", "page_pitch": lambda pc: 80.0,
           "pin_geometry": lambda *a, **k: list(geo), "seal_spans_col": lambda *a: (),
           "uncovered_ink": lambda *a, **k: list(uncov)}
    for k, v in fns.items():
        monkeypatch.setattr(_cv, k, v, raising=False)
    monkeypatch.setattr(sp, "column_basis", lambda *a, **k: {"col_sha": "s", "cw_fp": "f", "geom": {"v": 1}})


CACHE = NS(get=lambda *a: "x.png")


def test_recheck_ok_fills_geom(monkeypatch):
    _patch(monkeypatch)
    r = rc.recheck_item(_item(), _Store(_col()), CACHE, judge=object())
    assert r.status == "ok" and r.item["input"]["column_basis"]["geom"] == {"v": 1}
    assert "重核补底" in r.item["history"][-1]["why"]


def test_recheck_fails(monkeypatch):
    _patch(monkeypatch, geo=[{"note": "压墨", "block": True}])
    assert rc.recheck_item(_item(), _Store(_col()), CACHE, judge=object()).status == "fail"
    _patch(monkeypatch, uncov=[{"y0": 1, "y1": 40, "h": 39, "seal": False}])
    assert rc.recheck_item(_item(), _Store(_col()), CACHE, judge=object()).status == "fail"
    _patch(monkeypatch)
    big = [dict(PIN[0]), dict(PIN[1], y1=260.0)]                              # 出了列图（高 200）
    assert rc.recheck_item(_item(big), _Store(_col(cells=big)), CACHE, judge=object()).status == "fail"
    r = rc.recheck_item(_item(), _Store(_col(flags=())), CACHE, judge=object())
    assert r.status == "fail" and "未生效" in r.problems[0]


def test_needs_recheck():
    assert rc.needs_recheck(_item())
    it = _item()
    it["input"] = {"column_basis": {"geom": {"v": 1}}}
    assert not rc.needs_recheck(it)
