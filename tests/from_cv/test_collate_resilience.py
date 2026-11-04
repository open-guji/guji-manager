# -*- coding: utf-8 -*-
"""对勘的两道防线（2026-09-27，CV 总管追加）：

1. `report/run.py::collate_book` 单页崩溃不拖垮整册——`collate_page` 抛异常
   时记进 `page_errors`，跳过这一页，继续跑剩下的页。
2. `report/collate.py::diff_page` 入口挡坏数据——字位 `char`/`guess` 长度
   不是 1 的（真实案例：vol01 一批人裁事件 UTF-8 误当 cp1252 解码，一个字位
   存成 3 个 code point 的假"字"）按阙文处理，不让下标错位越界崩溃。

两条根因都在别处（`collate_page` 之外的异常、上游数据乱码），这里只测
「挡不挡得住」，不测「怎么修根因」——根因分别是另一个 bug（page_errors）
和 H 道要修的上游数据（乱码本身）。
"""
from __future__ import annotations

from dataclasses import replace

from open_guji_cv.clustering.align_eval import build_ngram_index
from open_guji_cv.report.collate import PLACEHOLDER, _sanitize_slots, diff_page
from guji_manager.report.run import collate_book
from open_guji_cv.report.slots import SlotRec
from open_guji_cv.report.witness import Witness

TRUTH = "皇帝二年秋七月甲子詔曰朕承天命撫馭萬方今澤及蒼生宜加恩賚布告天下咸使聞知"


def _slot(i: int, char: str | None, *, admit: bool = True, guess: str | None = None,
         book: str = "vol01", page: int = 24, col: int = 7) -> SlotRec:
    return SlotRec(id=f"{book}:{page}:{col}:{i}", page=page, col=col, slot=i, sub=None,
                  kind="char", char=char, admit=admit, channel=("human" if admit else None),
                  excluded=False, unreadable=False, human=admit, guess=guess)


def _witness(text: str = TRUTH) -> Witness:
    return Witness(name="w", label="w", quality="best", text=text,
                  index=build_ngram_index(text), text_norm=text)


# ── 1. collate_book 单页崩溃不拖垮整册 ──────────────────────────────

def test_collate_book_skips_the_crashing_page_and_keeps_the_rest(monkeypatch):
    from open_guji_cv.report.collate import PageResult

    def fake_collate_page(store, book, page, witnesses, stale):
        if page == 2:
            raise IndexError("list index out of range")
        return {w.label: PageResult(page=page, anchored=True, n_equal=3) for w in witnesses}

    monkeypatch.setattr("guji_manager.report.run.collate_page", fake_collate_page)
    w = _witness()
    doc = collate_book("tbook", [1, 2, 3], [w])

    assert [pe["page"] for pe in doc["page_errors"]] == [2]
    assert doc["page_errors"][0]["error_type"] == "IndexError"
    assert "list index out of range" in doc["page_errors"][0]["message"]
    assert [rec["page"] for rec in doc["page_stats"]] == [1, 3], "崩溃页跳过，其余页照样出结果"
    assert doc["summary"]["n_page_errors"] == 1


def test_collate_book_with_no_crashes_reports_zero_page_errors(monkeypatch):
    from open_guji_cv.report.collate import PageResult

    def fake_collate_page(store, book, page, witnesses, stale):
        return {w.label: PageResult(page=page, anchored=True, n_equal=1) for w in witnesses}

    monkeypatch.setattr("guji_manager.report.run.collate_page", fake_collate_page)
    w = _witness()
    doc = collate_book("tbook", [1, 2], [w])
    assert doc["page_errors"] == []
    assert doc["summary"]["n_page_errors"] == 0


# ── 2. diff_page 挡坏数据（长度≠1 的假字） ──────────────────────────


