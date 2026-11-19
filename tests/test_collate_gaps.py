"""对勘报告带上册 yaml 的缺页（cv `doc/formats/缺页.md`）。"""
from __future__ import annotations

from types import SimpleNamespace

from guji_manager.report import run

GAP = {"after_page": 20, "what": "卷九叶九、叶十", "kind": "原书缺", "est_chars": 830}


def test_book_gaps_filters_to_pages(monkeypatch):
    monkeypatch.setattr(run, "load_book", lambda b: SimpleNamespace(gaps=[GAP, {"after_page": 0, "what": "书衣", "kind": "未拍"}]))
    assert run.book_gaps("06", [19, 20, 21]) == [GAP]
    assert run.book_gaps("06", [21, 22]) == []
    assert [g["what"] for g in run.book_gaps("06", [1, 2])] == ["书衣"]


def test_book_gaps_tolerates_old_cv_and_bad_config(monkeypatch):
    monkeypatch.setattr(run, "load_book", lambda b: SimpleNamespace())        # cv 还没有 gaps 字段
    assert run.book_gaps("06", [20]) == []

    def boom(b):
        raise ValueError("册配置写错")
    monkeypatch.setattr(run, "load_book", boom)
    assert run.book_gaps("06", [20]) == []
