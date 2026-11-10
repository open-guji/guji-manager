# -*- coding: utf-8 -*-
"""排除名单上「没人看过」的格（管线 gate:crop_defect）要出卡进待审；人看过的（human:*、有人给的字）照旧不出。
2026-11-09 A31：vol01 的 5 格 gate:crop_defect 无人裁过、文本里整格掉字，谁都不管。产物自己造。"""
from __future__ import annotations

import pytest

import open_guji_cv.steps  # noqa: F401  注册产物种类


def _rec(cid, slot, why, **ev):
    from open_guji_cv.products.kinds.recog import AdmitRec
    return AdmitRec(id=cid, slot=slot, admit=False, char=None, doubts=["excluded"],
                    evidence={"excluded": why, **ev})


def test_gate_excluded_unseen_cells_get_cards(ws, tmp_path, monkeypatch):
    from open_guji_cv.core.spec import page_key
    from open_guji_cv.products.kinds.recog import ColumnAdmit, PageAdmit
    from open_guji_cv.products.store import ProductStore
    from guji_manager.review import cards as C
    monkeypatch.setenv("GUJI_FEEDBACK_DIR", str(tmp_path / "fb"))
    (tmp_path / "fb" / "events").mkdir(parents=True)
    monkeypatch.setenv("GUJI_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("GUJI_PRODUCTS_DIR", str(tmp_path / "products"))
    st = ProductStore(tmp_path / "products")
    recs = [_rec("keben:1:1:1", 1, "gate:crop_defect"),
            _rec("keben:1:1:2", 2, "gate:crop_defect", human_char="地"),
            _rec("keben:1:1:3", 3, "human:crop_defect"),
            _rec("keben:1:1:4", 4, "human:damaged", damaged=True)]
    st.write("keben", "seed_admit", page_key(1),
             {"seed_admit": PageAdmit(page=1, columns=[ColumnAdmit(col=1, chars=recs)])})
    C.clear_cards_cache()
    d = C.cards("keben", "1", 30, "review", st, gate_cut=False, skip_decided=True)
    assert {c["id"] for c in d["cards"]} == {"keben:1:1:1"}
    C.clear_cards_cache()
