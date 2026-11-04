# -*- coding: utf-8 -*-
"""看图结论事件通道（overview#428）：模型看图判的结论**不是人裁**。

- 落 `feedback/vision/`，不进 `feedback/events/`；事件 `actor="model"`、`payload.source="vision"`、`judge`；
- 不进字形库、`human_chars` 不认、不算已裁、不进绑定表（误写进 events/ 的 `source="vision"` 也不认）；
  但 events/ 里早有的 `actor="model"` 人裁机械更正（码位统一、乱码还原）照旧生效；
- 金标 `label_origin="vision"`；
- 判 wrong 的格回待审队列（doubt `vision_flag`），人裁过 / 字已改的不再送。
数据全部自己造，不读工作区。
"""
from __future__ import annotations

import json

import pytest

import open_guji_cv.steps  # noqa: F401  注册产物种类
from open_guji_cv.feedback.events import EventLog, EventTarget, counts_as_human, make_event
from open_guji_cv.feedback.vision import (VISION_DOUBT, VISION_SHARD, VisionLog, flag_active, import_vision,
                                          parse_jsonl, vision_checks, vision_pending)


def _ev(key: str, payload: dict, seq: int, *, kind: str = "confirm", actor: str = "user", batch: str = "b"):
    book, pg, col, slot = key.split(":")
    return make_event(batch, seq, kind,
                      EventTarget(step="seed_admit", unit="cell", key=key, book=book,
                                  page=int(pg), col=int(col), slot=int(slot)),
                      payload, actor=actor, source_format="server")


def _jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return path


ROWS = [
    {"cell": "keben:1:1:3", "v": "wrong", "char": "曰", "shown": "日", "judge": "m1", "note": "中横不贯"},
    {"cell": "keben:1:1:4", "v": "ok", "shown": "人", "judge": "m1"},
    {"cell": "keben:1:1:5", "v": "unsure", "judge": "m1", "group": "入人八"},
]


# ── 写入 ─────────────────────────────────────────────────────────────


# ── 不当人裁用 ───────────────────────────────────────────────────────


# ── 金标 ─────────────────────────────────────────────────────────────


# ── 送人审 ───────────────────────────────────────────────────────────


def _rec(cid, slot, *, admit=True, char="日", doubts=None):
    from open_guji_cv.products.kinds.recog import AdmitRec
    return AdmitRec(id=cid, slot=slot, admit=admit, char=char, doubts=doubts or [], evidence={})


@pytest.fixture
def env(ws, tmp_path, monkeypatch):
    from open_guji_cv.core.spec import page_key
    from open_guji_cv.products.kinds.recog import ColumnAdmit, PageAdmit
    from open_guji_cv.products.store import ProductStore
    from guji_manager.review import cards as C
    fb = tmp_path / "fb"
    (fb / "events").mkdir(parents=True)
    monkeypatch.setenv("GUJI_FEEDBACK_DIR", str(fb))
    monkeypatch.setenv("GUJI_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("GUJI_PRODUCTS_DIR", str(tmp_path / "products"))
    import open_guji_cv.feedback.bindings as B
    monkeypatch.setattr(B, "book_bindings", lambda book, log=None, **kw: {})
    st = ProductStore(tmp_path / "products")
    recs = [_rec("keben:1:1:3", 3),                    # 放行「日」，看图判错（该是「曰」）→ 回队列
            _rec("keben:1:1:4", 4, char="人"),         # 看图判对 → 不出
            _rec("keben:1:1:5", 5, char="曰"),         # 看图判错，但现行字已是看图认的字 → 不出
            _rec("keben:1:1:6", 6),                    # 看图判错，人已裁过 → 不出
            _rec("keben:1:1:7", 7)]                    # 没看过 → 放行的照旧不出
    st.write("keben", "seed_admit", page_key(1),
             {"seed_admit": PageAdmit(page=1, columns=[ColumnAdmit(col=1, chars=recs)])})
    _jsonl(tmp_path / "v.jsonl", [
        {"cell": "keben:1:1:3", "v": "wrong", "char": "曰", "shown": "日", "judge": "m1"},
        {"cell": "keben:1:1:4", "v": "ok", "shown": "人", "judge": "m1"},
        {"cell": "keben:1:1:5", "v": "wrong", "char": "曰", "shown": "日", "judge": "m1"},
        {"cell": "keben:1:1:6", "v": "wrong", "char": "曰", "shown": "日", "judge": "m1"}])
    from open_guji_cv.gold.store import GoldStore
    assert import_vision(tmp_path / "v.jsonl", gold_store=GoldStore(tmp_path / "verdicts"))["written"] == 4
    EventLog().append([_ev("keben:1:1:6", {"v": "confirm", "shape": "日"}, 1)])
    C.clear_cards_cache()
    yield st
    C.clear_cards_cache()


def test_vision_wrong_cell_enters_review_queue(env):
    from guji_manager.review.cards import cards
    d = cards("keben", "1", 30, "review", env, gate_cut=False, skip_decided=True, doubt="*")
    by = {c["id"]: c for c in d["cards"]}
    assert set(by) == {"keben:1:1:3"}
    c = by["keben:1:1:3"]
    assert VISION_DOUBT in c["doubts"] and c["char"] == "日" and c["admit"] is True   # 不改字
    assert c["vision"]["char"] == "曰" and c["vision"]["judge"] == "m1"
    assert d["doubt_counts"].get(VISION_DOUBT) == 1
    d2 = cards("keben", "1", 30, "review", env, gate_cut=False, skip_decided=True, doubt=VISION_DOUBT)
    assert [c["id"] for c in d2["cards"]] == ["keben:1:1:3"]


def test_vision_pending_report(env):
    rows = vision_pending("keben", [1], env)
    assert [(r["id"], r["char"], r["vision"]) for r in rows] == [("keben:1:1:3", "日", "曰")]
    assert set(vision_checks("keben")) == {"keben:1:1:3", "keben:1:1:4", "keben:1:1:5", "keben:1:1:6"}


