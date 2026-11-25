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


def test_column_basis_reads_merged_windows(monkeypatch):
    """切字五小步后 band／trim 在 2b／2c：底要按拼回的列窗口算，band 变了 sha 也要变。"""
    import pytest
    pytest.importorskip("open_guji_cv")
    from guji_manager import colview
    calls = []

    class _Col:
        def __init__(self, band): self.band = band
        def model_dump(self, mode="json"): return {"col": 1, "band": self.band}

    class _Wins:
        def __init__(self, band): self.b = band
        def column(self, col): return _Col(self.b)

    class _St:
        def manifest(self, book, step): return {}

    band = {"v": [1, 2]}
    monkeypatch.setattr(colview, "merged_windows", lambda st, book, key, step="column_warp": calls.append(key) or _Wins(band["v"]))
    a = sp.column_basis("001", 3, 1, store=_St())
    band["v"] = [1, 3]
    b = sp.column_basis("001", 3, 1, store=_St())
    assert calls and a["col_sha"] != b["col_sha"]
