"""回库贴错图核查：分类、真写、回退（ops/rebind_audit.py）。"""
import cv2
import numpy as np

import open_guji_cv.steps  # noqa: F401
from open_guji_cv.clustering.glyph_db import GlyphDB
from guji_manager.ops import rebind_audit as RA

T = "2026-11-26T20:09:00+00:00"


def _png(w=40):
    img = np.full((80, 80), 255, np.uint8)
    cv2.rectangle(img, (6, 10), (6 + w, 70), 0, 4)
    return cv2.imencode(".png", img)[1].tobytes()


class _Cache:
    def __init__(self, d):
        self.d = d

    def get(self, book, kind, key):
        p = self.d / f"{key}.png"
        return p if p.exists() else None


def _db(tmp_path):
    g = GlyphDB(tmp_path / "g.db")
    g.require_book_edition = False
    for i, (k, ch) in enumerate([("03:94:5:2", "應"), ("03:94:5:3", "故"), ("03:94:5:4", "甲"), ("03:94:5:5", "乙"), ("03:95:1:1", "丙")]):
        assert g.admit_instance("v2:" + k, ch, _png(20 + i), provenance="human", shape=ch,
                                evidence={"event": f"e{i}"}, page=k.split(":")[1], col=5, idx=int(k.split(":")[3]))
    g.conn.execute("UPDATE admissions SET admitted_at=?", (T,))
    g.conn.commit()
    return g


BIND = {"e0": {"status": "rebound", "bound": "03:94:5:1"},   # 顺移到别格 → rebind
        "e1": {"status": "valid", "bound": "03:94:5:3"},     # 同键 → keep
        "e2": {"status": "review", "bound": None}}           # 不可用 → withdraw
# e3 无行 → no_row；e4 页 95 无产物 → no_products


def test_plan_apply_undo(tmp_path):
    g = _db(tmp_path)
    rows = RA.plan(g, "2026-11-26T19:00", "2026-11-26T21:30", bindings_of=lambda b: BIND,
                   has_products=lambda b, p: p == 94)
    act = {r["char"]: r["action"] for r in rows}
    assert act == {"應": "rebind", "故": "keep", "甲": "withdraw", "乙": "no_row", "丙": "no_products"}
    assert [r["new_instance"] for r in rows if r["char"] == "應"] == ["v2:03:94:5:1"]
    tsv = tmp_path / "p.tsv"
    RA.write_tsv(rows, tsv)
    assert RA.read_tsv(tsv)[0]["instance"].startswith("v2:03:94")

    (tmp_path / "c").mkdir()
    cv2.imwrite(str(tmp_path / "c" / "p0094c05s1.png"), cv2.imdecode(np.frombuffer(_png(33), np.uint8), 0))
    import pytest
    with pytest.raises(ValueError):
        RA.apply(g, rows, "", tmp_path / "u.jsonl", cache=_Cache(tmp_path / "c"))
    r = RA.apply(g, rows, "Sheldon", tmp_path / "u.jsonl", cache=_Cache(tmp_path / "c"))
    assert r["withdrawn"] == 1 and r["rebound"] == 1
    have = {x[0] for x in g.conn.execute("SELECT instance_id FROM admissions")}
    assert have == {"v2:03:94:5:1", "v2:03:94:5:3", "v2:03:94:5:5", "v2:03:95:1:1"}

    n = RA.undo(g, tmp_path / "u.jsonl")
    have = {x[0] for x in g.conn.execute("SELECT instance_id FROM admissions")}
    assert have == {"v2:03:94:5:2", "v2:03:94:5:3", "v2:03:94:5:4", "v2:03:94:5:5", "v2:03:95:1:1"} and n["restored"] == 2


def test_rebind_without_image_keeps_old(tmp_path):
    g = _db(tmp_path)
    rows = RA.plan(g, "2026-11-26T19:00", "2026-11-26T21:30", bindings_of=lambda b: BIND, has_products=lambda b, p: True)
    (tmp_path / "c").mkdir()
    r = RA.apply(g, rows, "Sheldon", tmp_path / "u.jsonl", cache=_Cache(tmp_path / "c"))
    assert r["rebind_no_image"] == 1
    assert g.conn.execute("SELECT 1 FROM admissions WHERE instance_id='v2:03:94:5:2'").fetchone()
