# -*- coding: utf-8 -*-
"""近似字（overview#276）：人裁卡「无匹配（近似字）」→ 事件 → 侧表 `approx_labels` → 导出/同步 → 闸与文本。

钉住：
1. 老事件（不带 approx）行为完全不变：读回形状、进库结果、库内容、指纹、seed_admit 参数哈希；
2. 带 approx 的 confirm 写侧表（ids/note/reviewer 可空），人改口撤掉并记 `approx_clears`，撤例跟着删；
3. 库指纹（`db_fingerprint`）空表不变、有行也不变（建议见 HANDOFF_H276）；
4. 查询「某字有没有近似例」与字表角标计数；
5. seed_admit：匹配到近似例缺省照常放行、evidence 标注（用户 09-29 裁定 #277 选 C）；开闸则落人审；
6. 文本：缺省正文照填 + 侧表（来源 人裁/匹配），`inline_ids` 选项括注；
7. 前端 `verdictRow`（node 跑 reviewClass.ts）。
导出签名见 `ops.central_glyph.export_signature`（中心库 push／sync 前据此决定要不要先导出）。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import cv2
import numpy as np
import pytest

import open_guji_cv.steps  # noqa: F401
from open_guji_cv.clustering.audit import evict_instance
from open_guji_cv.clustering.glyph_db import GlyphDB
from open_guji_cv.feedback.consumers import glyphdb_admit
from open_guji_cv.feedback.events import EventLog, EventTarget, make_event
from guji_manager.review.verdict_view import review_verdicts

BOOK = "abook"


def _png(k: int = 0) -> bytes:
    img = np.full((80, 80), 255, np.uint8)
    cv2.rectangle(img, (6 + k % 20, 10), (70, 70 - k % 15), 0, 4)
    cv2.line(img, (10, 10 + k % 30), (70, 40), 0, 3)
    return cv2.imencode(".png", img)[1].tobytes()


def _ev(key: str, payload: dict, seq: int = 1, ts: str | None = None, actor: str = "user",
        reviewer: str | None = None, batch: str = "b"):
    _b, pg, col, slot = key.split(":")
    return make_event(batch, seq, "confirm",
                      EventTarget(step="seed_admit", unit="cell", key=key, book=_b,
                                  page=int(pg), col=int(col), slot=int(slot)),
                      payload, actor=actor, ts=ts, reviewer=reviewer)


@pytest.fixture
def db(tmp_path, monkeypatch):
    """空库里已有一格人裁（`v2:abook:1:1:1` 定「之」）：消费者走「缓存里没有 → 用库里那张」的路，
    不必现跑 Step1→Step4。"""
    monkeypatch.setenv("GUJI_CACHE_DIR", str(tmp_path / "cache"))
    p = tmp_path / "g.db"
    g = GlyphDB(p)
    assert g.admit_instance(f"v2:{BOOK}:1:1:1", "之", _png(1), provenance="human",
                            page="1", col=1, idx=1)
    g.conn.commit()
    g.close()
    return p


def _dump(p: Path) -> dict:
    c = sqlite3.connect(p)
    try:
        out = {}
        for t in ("instances", "admissions", "exemplars", "glyphs", "evictions",
                  "approx_labels", "approx_clears"):
            cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
            keep = [x for x in cols if x not in ("patch_png", "updated_at", "admitted_at",
                                                 "added_at", "at")]
            out[t] = sorted(c.execute(f"SELECT {','.join(keep)} FROM {t}").fetchall(), key=repr)
        return out
    finally:
        c.close()


# ── 1. 读回 ──────────────────────────────────────────────────────────────


# ── 2. 进库 ──────────────────────────────────────────────────────────────


# ── 3. 指纹 ──────────────────────────────────────────────────────────────


# ── 4. 查询 ──────────────────────────────────────────────────────────────


# ── 5. seed_admit 闸 ─────────────────────────────────────────────────────


def _run_seed(tmp_path, monkeypatch, db_path, recs, **params):
    from helpers import make_book, make_ctx, page_decision, write_product
    from open_guji_cv.core.step import STEPS, RunContext
    from open_guji_cv.products.kinds.cells import CellRec, ColumnCells, PageCells
    from open_guji_cv.products.kinds.recog import ColumnMatch, PageAlignRef, PageMatch
    from open_guji_cv.steps.seed_admit import SeedAdmitParams
    monkeypatch.setenv("GUJI_FEEDBACK_DIR", str(tmp_path / "fb"))
    img = np.full((600, 600), 255, np.uint8)
    ctx = make_ctx(tmp_path, make_book("tbook"), raw={1: img}, monkeypatch=monkeypatch)
    ctx = RunContext(ctx.book, ctx.store, ctx.cache,
                     params={"seed_admit": SeedAdmitParams(db_path=str(db_path), **params)},
                     log=lambda s: None)
    ctx._raw[1] = img
    cells = [CellRec(slot=s, pos=s, y0=0, y1=10, x0=0, x1=10, kind="char", order=s) for s in (1, 2, 3)]
    write_product(ctx, "glyph_match", 1,
                  glyph_match=PageMatch(page=1, columns=[ColumnMatch(col=3, ok=True, chars=recs)]))
    write_product(ctx, "context_decide", 1, context_decision=page_decision(1, "tbook", recs=[], col=3))
    write_product(ctx, "row_segment", 1,
                  cells=PageCells(page=1, period=10.0, ref_w=10.0,
                                  columns=[ColumnCells(col=3, ok=True, n_body_slots=3, period=10.0,
                                                       border_top=0.0, cells=cells)]))
    write_product(ctx, "align_ref", 1, align_ref=PageAlignRef(page=1, anchored=False, coord=[]))
    sa = STEPS["seed_admit"].run_page(ctx, 1)["seed_admit"]
    return {r.slot: r for cc in sa.columns for r in cc.chars}


# ── 6. 文本 ──────────────────────────────────────────────────────────────

def test_text_sidecar_default_and_inline_option(tmp_path):
    from guji_manager.render.approx import approx_marks, inline_ids_map, sidecar_rows, sidecar_tsv
    from guji_manager.render.guji_markdown import _char_text
    from open_guji_cv.report.slots import SlotRec
    log = EventLog(tmp_path)
    log.append([_ev(f"{BOOK}:3:2:5", {"v": "confirm", "shape": "乃", "approx": True, "ids": "⿱丿乃",
                                      "note": "多一撇"}, 1, ts="2026-09-29T01:00:00Z")])
    log.append([_ev(f"{BOOK}:3:2:6", {"v": "confirm", "shape": "之", "approx": True}, 2,
                    ts="2026-09-29T01:00:00Z")])
    log.append([_ev(f"{BOOK}:3:2:6", {"v": "confirm", "shape": "之"}, 3, ts="2026-09-29T02:00:00Z")])
    log.append([_ev(f"{BOOK}:4:1:1", {"v": "confirm", "shape": "乎", "approx": True}, 4,
                    ts="2026-09-29T01:00:00Z")])
    marks = approx_marks(BOOK, log)
    assert set(marks) == {f"{BOOK}:3:2:5", f"{BOOK}:4:1:1"}, "改口的那格撤掉"
    rows = sidecar_rows(marks, [3])
    assert [(r["pos"], r["ids"], r["note"], r["source"]) for r in rows] == [("3:2:5", "⿱丿乃", "多一撇", "human")]
    assert sidecar_tsv(rows) == "pos\tshape\tids\tnote\tsource\n3:2:5\t乃\t⿱丿乃\t多一撇\thuman\n"

    def slot(key, ch):
        _b, pg, col, s = key.split(":")
        return SlotRec(id=key, page=int(pg), col=int(col), slot=int(s), sub=None, kind="char",
                       char=ch, admit=True, channel="human", excluded=False, unreadable=False, human=True)
    rec = slot(f"{BOOK}:3:2:5", "乃")
    assert _char_text(rec) == "乃", "缺省：正文照填"
    inline = inline_ids_map(marks)
    assert _char_text(rec, inline) == "乃{ids=⿱丿乃}"
    assert _char_text(slot(f"{BOOK}:4:1:1", "乎"), inline) == "乎", "没填 IDS 的不括注"
    assert _char_text(slot(f"{BOOK}:3:2:5", "及"), inline) == "及", "正文已不是那个字就不括注"


# ── 7. 前端事件行 ─────────────────────────────────────────────────────────


def test_text_sidecar_includes_matched_cells(tmp_path, monkeypatch):
    """Step7 靠近似例放行的格进侧表（来源 matched）；没放行的不进；人裁同格覆盖。"""
    from helpers import make_book, make_ctx, write_product
    from open_guji_cv.products.kinds.recog import AdmitRec, ColumnAdmit, PageAdmit
    from guji_manager.render.approx import book_marks, sidecar_rows
    ctx = make_ctx(tmp_path, make_book(BOOK), monkeypatch=monkeypatch)
    apx = {"source": "matched", "via": "matched_id", "exemplar": "v2:lib:1:1:1", "ids": "⿰亻衡", "note": None}
    recs = [AdmitRec(id=f"{BOOK}:3:1:{s}", slot=s, admit=adm, channel="match_solo" if adm else None,
                     char="衡", evidence={"approx": apx}) for s, adm in ((1, True), (2, False), (3, True))]
    write_product(ctx, "seed_admit", 3,
                  seed_admit=PageAdmit(page=3, columns=[ColumnAdmit(col=1, ok=True, chars=recs)]))
    log = EventLog(tmp_path / "ev")
    log.append([_ev(f"{BOOK}:3:1:3", {"v": "confirm", "shape": "衡", "approx": True, "note": "人看过"}, 1)])
    rows = sidecar_rows(book_marks(ctx.store, BOOK, [3], log))
    assert [(r["pos"], r["source"], r["ids"], r["note"]) for r in rows] == [
        ("3:1:1", "matched", "⿰亻衡", ""), ("3:1:3", "human", "", "人看过")]


pytestmark = pytest.mark.usefixtures("seed_admit_switches_off")   # 老测试按「放行开关缺省全关」造的数据，见 conftest
