"""换图源后的页表 rev 判据（GUJI-748，设计稿 `殿本换图源-siku-qiefen-v2.md` §六）。

切过图源的册（yaml 有 `source_rev`），指向页的事件锚里 `source_rev` 必须相符才采信；
写入拒写、所有读口同一判据，维护自身日志（压实、编号）照原样读。"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from open_guji_cv.core.event_files import (
    RevGate,
    book_source_rev,
    iter_event_dicts,
    iter_event_records,
    sibling_books_dir,
)
from open_guji_cv.feedback.events import EventLog, EventTarget, make_event


def _data(tmp_path: Path, revs: dict[str, int | None]) -> Path:
    """<数据>/books/<册>.yaml ＋ <数据>/feedback/events/"""
    books = tmp_path / "books"
    books.mkdir()
    for b, r in revs.items():
        (books / f"{b}.yaml").write_text(f"id: {b}\n" + (f"source_rev: {r}\n" if r is not None else ""),
                                         encoding="utf-8")
    (tmp_path / "feedback" / "events").mkdir(parents=True)
    return tmp_path


def _ev(seq, book="vol11", page=3, rev=None, kind="confirm", batch="b"):
    anchor = {"space": "page"} if rev is None else {"space": "page", "source_rev": rev}
    return make_event(batch, seq, kind,
                      EventTarget(step="seed_admit", unit="cell", key=f"{book}:{page}:1:{seq}",
                                  book=book, page=page, col=1, slot=seq, anchor=anchor),
                      {"v": "confirm", "shape": "之"}, source_format="server")


# ── 判据本身 ─────────────────────────────────────────────────────────


# ── EventLog ─────────────────────────────────────────────────────────

def _write_raw(d: Path, batch: str, evs) -> None:
    with open(d / "feedback" / "events" / f"{batch}.jsonl", "a", encoding="utf-8") as f:
        f.writelines(e.model_dump_json() + "\n" for e in evs)


# ── 低层读口 ─────────────────────────────────────────────────────────


# ── 读口收拢：别处不许再直接扫人裁事件文件 ────────────────────────────

#: 可以直接 glob 事件目录的地方：读口本身；只看 stat／存在的；读原样的维护工具；字形库自己的事件。
_ALLOWED = {
    "core/event_files.py", "feedback/events.py",
    "feedback/lookup.py",          # 只取文件签名做缓存键
    "review/cards.py",             # 只取 mtime 水位
    "eval/round_check.py",         # 只判有没有
    "feedback/lint.py",            # 校验原样内容
    "clustering/glyph_db.py",      # 字形库 store 的事件，不是人裁事件
    "ops/glyphlib.py",             # 扫的是字形库 instances/；人裁事件已走 iter_event_dicts
    "feedback/candidates.py",      # 候选清单文件
    "eval/llm_online_accuracy.py", # 线上调用日志
}


def test_db_status_counts_dropped(tmp_path):
    from guji_manager.cli_db import _rev_gate_dropped
    d = _data(tmp_path, {"vol11": 3})
    _write_raw(d, "a", [_ev(1, rev=2, batch="a"), _ev(2, batch="a"), _ev(3, rev=3, batch="a")])
    assert _rev_gate_dropped(d) == {"vol11": 2}


# ── 过闸结果缓存（`EventLog._gate_cached`，2026-11-04）──────────────────


