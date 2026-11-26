# -*- coding: utf-8 -*-
"""pins-stale「钉子改了、该页 row_segment 没重跑」（applied_status）：只比内容与 manifest 软指纹，不比时间戳。"""
from types import SimpleNamespace as NS

from guji_manager import seg_pin as sp

PIN = [{"slot": 1, "kind": "char", "y0": 10.0, "y1": 40.0, "x0": 2.0, "x1": 30.0},
       {"slot": 2, "sub": "a", "kind": "jiazhu_a", "y0": 42.0, "y1": 60.0, "x0": 16.0, "x1": 30.0}]
ITEM = {"id": "b:5:3", "anchor": {"book": "b", "page": 5, "col": 3}}


def _cells(spec, flags=("roster", "manual_cells")):
    return [NS(slot=c["slot"], sub=c.get("sub"), kind=c.get("kind", "char"),
               y0=c["y0"], y1=c["y1"], x0=c["x0"], x1=c["x1"]) for c in spec], list(flags)


class Store:
    def __init__(self, cells=None, flags=(), fp=None, col=3):
        self.pc = None if cells is None else NS(columns=[NS(col=col, cells=cells, flags=list(flags))])
        self.fp = fp

    def read(self, book, step, key, kind):
        assert (book, step, key, kind) == ("b", "row_segment", "p0005", "cells")
        return self.pc

    def manifest(self, book, step):
        return {"p0005": NS(soft={"manual_cells_fingerprint": self.fp} if self.fp else None)}


def test_fingerprint_ignores_order():
    a = {(5, 3): PIN, (7, 1): PIN[:1]}
    b = {(7, 1): PIN[:1], (5, 3): PIN}
    assert sp.book_pins_fingerprint(a) == sp.book_pins_fingerprint(b) != sp.book_pins_fingerprint({(5, 3): PIN})


def test_no_product_unknown():
    assert sp.applied_status(ITEM, Store(), {(5, 3): PIN}, "x", True)[0] == "unknown"


def test_product_without_pin_flag_unapplied():
    cells, _ = _cells(PIN)
    st, why = sp.applied_status(ITEM, Store(cells, flags=("roster",)), {(5, 3): PIN}, "x", True)
    assert st == "unapplied" and "没用上" in why
    st, _ = sp.applied_status(ITEM, Store([], flags=()), {(5, 3): PIN}, "x", True)   # 产物里没有这一列旗
    assert st == "unapplied"


def test_same_fingerprint_ok_without_compare():
    pins = {(5, 3): PIN}
    fp = sp.book_pins_fingerprint(pins)
    cells, flags = _cells(PIN[:1])                       # 内容不同但指纹相同：manifest 说当时就是这份钉子
    assert sp.applied_status(ITEM, Store(cells, flags, fp=fp), pins, fp, True)[0] == "ok"


def test_fingerprint_changed_elsewhere_but_column_matches_ok():
    pins = {(5, 3): PIN}
    cells, flags = _cells(PIN)
    assert sp.applied_status(ITEM, Store(cells, flags, fp="old"), pins, "new", True)[0] == "ok"


def test_pin_slots_changed_unapplied():
    pins = {(5, 3): PIN}
    cells, flags = _cells(PIN[:1])
    st, why = sp.applied_status(ITEM, Store(cells, flags, fp="old"), pins, "new", True)
    assert st == "unapplied" and "格号" in why


def test_pin_coords_changed_unapplied_and_tolerance():
    moved = [{**PIN[0], "y1": 38.0}, PIN[1]]
    cells, flags = _cells(moved)
    pins = {(5, 3): PIN}
    st, why = sp.applied_status(ITEM, Store(cells, flags, fp="old"), pins, "new", True)
    assert st == "unapplied" and "坐标" in why
    # 几何底变了（cv 换算过、位移 ≤3px 不打旗）：按余量比，2px 算用上了
    assert sp.applied_status(ITEM, Store(cells, flags, fp="old"), pins, "new", False)[0] == "ok"
    # 打了 manual_cells_remapped 的列不比坐标（已送人核）
    far = [{**PIN[0], "y1": 30.0}, PIN[1]]
    cells, _ = _cells(far)
    st, _ = sp.applied_status(ITEM, Store(cells, ("roster", "manual_cells", "manual_cells_remapped"), fp="old"),
                              pins, "new", False)
    assert st == "ok"
