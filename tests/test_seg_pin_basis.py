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
