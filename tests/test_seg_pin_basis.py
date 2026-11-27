"""钉子记上游底、判过期（11-20 痛点 K3，脉经钉子在书口去除后静默切错）。"""
from guji_manager import seg_pin as sp


def _item(basis):
    return {"id": "vol01:66:1", "anchor": {"book": "vol01", "page": 66, "col": 1}, "status": "active",
            "input": {"column_basis": basis} if basis else {}}


def test_basis_status(monkeypatch):
    now = {"col_sha": "a", "cw_fp": "f2"}
    monkeypatch.setattr(sp, "column_basis", lambda *a, **k: now)
    assert sp.basis_status(_item({"col_sha": "a", "cw_fp": "f2"}))[0] == "ok"
    assert sp.basis_status(_item({"col_sha": "b", "cw_fp": "f2"}))[0] == "stale"
    assert sp.basis_status(_item({"col_sha": "a", "cw_fp": "f1"}))[0] == "maybe"
    assert sp.basis_status(_item(None))[0] == "unknown"
    monkeypatch.setattr(sp, "column_basis", lambda *a, **k: None)
    assert sp.basis_status(_item({"col_sha": "a"}))[0] == "unknown"


def test_make_item_records_basis(monkeypatch):
    monkeypatch.setattr(sp, "column_basis", lambda *a, **k: {"col_sha": "a", "cw_fp": "f"})
    d = sp.Draft("vol01", 66, 1, [], (0.0, 10.0), "row_segment", [])
    it = sp.make_item(d, "test")
    assert it["input"]["column_basis"] == {"col_sha": "a", "cw_fp": "f"}
    monkeypatch.setattr(sp, "column_basis", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert "column_basis" not in sp.make_item(d, "test")["input"]


def test_column_basis_reads_merged_windows():
    """切字五小步后 band／trim 在 2b／2c：拼回后的 sha 与拆步前整份记录相同（不误报 stale）。"""
    import hashlib
    import json
    from pydantic import BaseModel

    class Col(BaseModel):
        col: int
        left: float = 0.0
        band: list | None = None
        trim_top: int = 0
        trim_bottom: int = 0
        triage: str | None = None
        frame_residue_top: int = 0
        frame_residue_bottom: int = 0

    class Page(BaseModel):
        columns: list[Col]

        def column(self, c):
            return next((x for x in self.columns if x.col == c), None)

    full = Col(col=1, left=3.0, band=[1, 2], trim_top=5, trim_bottom=7, triage="ok",
               frame_residue_top=1, frame_residue_bottom=2)
    data = {"column_warp": Page(columns=[Col(col=1, left=3.0)]),
            "column_band": Page(columns=[Col(col=1, band=[1, 2])]),
            "column_end": Page(columns=[Col(col=1, trim_top=5, trim_bottom=7, triage="ok",
                                            frame_residue_top=1, frame_residue_bottom=2)])}

    class Store:
        def read(self, book, step, key, kind):
            return data.get(step)

        def manifest(self, book, step):
            return {}

    want = hashlib.sha256(json.dumps(full.model_dump(mode="json"), ensure_ascii=False,
                                     sort_keys=True).encode("utf-8")).hexdigest()[:16]
    assert sp.column_basis("vol01", 66, 1, Store())["col_sha"] == want


def _geom(x=10.0):
    return {"v": 1, "page_w": 100, "left": [x, 0.0, None, None, None, None],
            "right": [x + 50, 0.0, None, None, None, None], "top_y": 5.0, "bottom_y": 90.0, "ruled": False}


def test_basis_status_geom_only(monkeypatch):
    """记了 geom 的只比 geom：列窗记录别的字段变了（col_sha 变）不报 stale；几何变了才报。"""
    monkeypatch.setattr(sp, "column_basis", lambda *a, **k: {"col_sha": "z", "cw_fp": "f9", "geom": _geom()})
    assert sp.basis_status(_item({"col_sha": "a", "cw_fp": "f1", "geom": _geom()}))[0] == "ok"
    st, why = sp.basis_status(_item({"col_sha": "z", "cw_fp": "f9", "geom": _geom(12.0)}))
    assert st == "stale" and "left" in why and "right" in why


def test_column_geom():
    from types import SimpleNamespace as NS
    ln = NS(model_dump=lambda mode=None: {"x_at_top": 1.23456, "slope": 0.01, "k2": None, "k3": None,
                                          "y1": None, "y2": None})
    g = sp.column_geom(NS(left_line=ln, right_line=ln, top_y=3.0, bottom_y=9.0, ruled=False), 4296)
    assert g == {"v": 1, "page_w": 4296, "left": [1.235, 0.01, None, None, None, None],
                 "right": [1.235, 0.01, None, None, None, None], "top_y": 3.0, "bottom_y": 9.0, "ruled": False}
    assert sp.column_geom(None, 4296) is None


def test_backfill_geom(monkeypatch):
    monkeypatch.setattr(sp, "column_basis", lambda *a, **k: {"col_sha": "a", "cw_fp": "f", "geom": _geom()})
    new, _ = sp.backfill_geom(_item({"col_sha": "a", "cw_fp": "f"}))
    assert new["input"]["column_basis"]["geom"] == _geom() and new["history"][-1]["change"] == "updated"
    assert sp.backfill_geom(_item({"col_sha": "b"}))[0] is None          # 列窗不一致不补
    assert sp.backfill_geom(_item({"col_sha": "a", "geom": _geom()}))[0] is None
    assert sp.backfill_geom(_item(None))[0] is None


def test_basis_status_small_shift_ok(monkeypatch):
    """几何字段变了但钉子框位移 ≤3px → ok；位移大 → stale（QTW 11-27 outer_bar 开↔关误报）。"""
    now = {"col_sha": "z", "cw_fp": "f", "geom": _geom(10.5)}
    monkeypatch.setattr(sp, "column_basis", lambda *a, **k: now)
    it = _item({"col_sha": "a", "geom": _geom()})
    it["expected"] = {"cells": [{"slot": 1, "kind": "char", "x0": 5.0, "x1": 45.0, "y0": 10.0, "y1": 50.0}]}
    monkeypatch.setattr(sp, "pin_shift", lambda *a: 0.5)
    assert sp.basis_status(it)[0] == "ok"
    monkeypatch.setattr(sp, "pin_shift", lambda *a: 12.0)
    st, why = sp.basis_status(it)
    assert st == "stale" and "12.0px" in why
    monkeypatch.setattr(sp, "pin_shift", lambda *a: None)
    assert sp.basis_status(it)[0] == "stale"


def test_pin_shift_real_mapper():
    """用 cv 的 ColumnMapper 实算：左右线整体右移 0.5px，位移约 0.5px；上界挪 20px，位移约 20px。"""
    cells = [{"slot": 1, "kind": "char", "x0": 5.0, "x1": 45.0, "y0": 10.0, "y1": 50.0}]
    g0 = dict(_geom(), page_w=200)
    d = sp.pin_shift(cells, g0, dict(g0, left=[10.5, 0.0, None, None, None, None],
                                     right=[60.5, 0.0, None, None, None, None]))
    if d is None:
        import pytest
        pytest.skip("装的 cv 没有钉子换算（< v0.9.6）")
    assert d < 1.0
    assert sp.pin_shift(cells, g0, dict(g0, top_y=25.0)) > 15
