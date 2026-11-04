# -*- coding: utf-8 -*-
"""已裁却不出字（overview#403 缺口 A、C）。产物与绑定行都自己造，不读工作区。

A：`decided_cells` 只收**现在仍有效**的裁决——最新绑定行 `usable(...)` 非空、或没有绑定行
   （非 confirm 事件／还没进绑定表）。老事件 `anchor:null` 判 `unanchored`、`bound=None` 的格回到
   待审队列，卡片带 `stale_verdict` 当预勾。排除名单格带字仍算已裁（缺口 B 口径），失效了也回队列。
C：`closure_gaps`：「有定字裁决」∩「seed_admit `admit=False` 且没出字」，收尾前必须为空。
"""
from __future__ import annotations

import pytest

import open_guji_cv.steps  # noqa: F401  注册产物种类
from open_guji_cv.feedback.events import EventLog, EventTarget, make_event
from open_guji_cv.review.verdict_view import closure_gaps, closure_mismatches, decided_cells, decided_view


def _ev(key: str, payload: dict, seq: int, *, kind: str = "confirm", batch: str = "b"):
    book, pg, col, slot = key.split(":")
    return make_event(batch, seq, kind,
                      EventTarget(step="seed_admit", unit="cell", key=key, book=book,
                                  page=int(pg), col=int(col), slot=int(slot)),
                      payload, source_format="server")


def _row(e, status: str, bound: str | None):
    return {"event": e.id, "key": e.target.key, "ts": e.ts, "bound": bound,
            "shape": (e.payload or {}).get("shape"), "status": status}


# ── A：decided_view ──────────────────────────────────────────────────


# ── A：cards(skip_decided=True) ──────────────────────────────────────

def _rec(cid, slot, *, doubts=None, admit=False, char="因", evidence=None):
    from open_guji_cv.products.kinds.recog import AdmitRec
    return AdmitRec(id=cid, slot=slot, admit=admit, char=char, doubts=doubts or ["上下文 margin 不足(0.1)"],
                    evidence=evidence or {})


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
    st = ProductStore(tmp_path / "products")
    recs = [
        _rec("keben:1:1:3", 3),                                                       # 失效老裁决「困」
        _rec("keben:1:1:4", 4),                                                       # 有效裁决
        _rec("keben:1:1:5", 5, char=None, doubts=["excluded"],
             evidence={"excluded": "human:seg_defect"}),                              # 名单 + 失效带字
        _rec("keben:1:1:6", 6, char=None, doubts=["excluded"],
             evidence={"excluded": "human:seg_defect", "human_char": "地"}),          # 名单 + 有效带字（缺口 B）
        _rec("keben:1:1:7", 7),                                                       # 没裁过
    ]
    st.write("keben", "seed_admit", page_key(1),
             {"seed_admit": PageAdmit(page=1, columns=[ColumnAdmit(col=1, chars=recs)])})
    evs = [_ev("keben:1:1:3", {"v": "confirm", "shape": "困"}, 1, batch="keben-old"),
           _ev("keben:1:1:4", {"v": "confirm", "shape": "天"}, 2),
           _ev("keben:1:1:5", {"v": "seg_defect", "quality": "truncated", "shape": "玄"}, 3, batch="keben-old"),
           _ev("keben:1:1:6", {"v": "seg_defect", "quality": "truncated", "shape": "地"}, 4)]
    EventLog().append(evs)
    status = {"keben:1:1:3": ("unanchored", None), "keben:1:1:4": ("valid", "keben:1:1:4"),
              "keben:1:1:5": ("unanchored", None), "keben:1:1:6": ("valid", "keben:1:1:6")}
    rows = {e.id: _row(e, *status[e.target.key]) for e in evs}
    import open_guji_cv.feedback.bindings as B
    monkeypatch.setattr(B, "book_bindings", lambda book, log=None, **kw: rows)
    C.clear_cards_cache()
    yield st
    C.clear_cards_cache()


def test_cards_skip_decided_shows_stale_with_prefill(env):
    from guji_manager.review.cards import cards
    d = cards("keben", "1", 30, "review", env, gate_cut=False, skip_decided=True)
    by = {c["id"]: c for c in d["cards"]}
    assert set(by) == {"keben:1:1:3", "keben:1:1:5", "keben:1:1:7"}
    assert by["keben:1:1:3"]["stale_verdict"]["verdict"]["shape"] == "困"
    assert by["keben:1:1:5"]["stale_verdict"]["verdict"] == {"shape": "玄", "done": "truncated"}
    assert by["keben:1:1:7"]["stale_verdict"] is None
    assert d["n_decided"] == 2


def test_cards_without_skip_still_carries_stale(env):
    from guji_manager.review.cards import cards
    d = cards("keben", "1", 30, "review", env, gate_cut=False, skip_decided=False)
    by = {c["id"]: c for c in d["cards"]}
    assert "keben:1:1:4" in by and by["keben:1:1:4"]["stale_verdict"] is None
    assert by["keben:1:1:3"]["stale_verdict"]["verdict"]["shape"] == "困"
    assert "keben:1:1:6" not in by          # 名单上、有效带字：照旧不出卡（缺口 B）


def _write_list(name, ids):
    from open_guji_cv.core.workspace import feedback_root
    f = feedback_root() / "lists" / f"{name}.txt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("\n".join(ids) + "\n", encoding="utf-8")
    return f


def test_list_mode_default_skips_valid_decided(env):
    """GUJI-525（#74）：点名清单默认跳过现行有效已裁；失效老裁决与没裁的照出。"""
    from guji_manager.review.cards import cards
    _write_list("t525", ["keben:1:1:3", "keben:1:1:4", "keben:1:1:7"])
    d = cards("keben", "list:t525", 30, "review", env, gate_cut=False)
    assert {c["id"] for c in d["cards"]} == {"keben:1:1:3", "keben:1:1:7"}
    assert not any("decided" in c for c in d["cards"])


def test_list_mode_marks_valid_decided_when_not_skipping(env):
    """GUJI-525：skip_decided=false 时点名清单出全部格，现行有效已裁的带 decided；失效老裁决与没裁的不带。"""
    from guji_manager.review.cards import cards
    _write_list("t525", ["keben:1:1:3", "keben:1:1:4", "keben:1:1:7"])
    d = cards("keben", "list:t525", 30, "review", env, gate_cut=False, skip_decided=False)
    by = {c["id"]: c for c in d["cards"]}
    assert set(by) == {"keben:1:1:3", "keben:1:1:4", "keben:1:1:7"}
    assert by["keben:1:1:4"]["decided"] is True
    assert "decided" not in by["keben:1:1:3"]       # 老裁决已失效：回待审
    assert "decided" not in by["keben:1:1:7"]


def test_non_list_modes_never_carry_decided_on_skipped_pool(env):
    from guji_manager.review.cards import cards
    d = cards("keben", "1", 30, "review", env, gate_cut=False, skip_decided=True)
    assert not any("decided" in c for c in d["cards"])         # 已裁的压根没出
    d2 = cards("keben", "1", 30, "review", env, gate_cut=False, skip_decided=False)
    assert {c["id"] for c in d2["cards"] if c.get("decided")} == {"keben:1:1:4"}   # 复核模式同样带标记


def test_list_edit_in_place_changes_cache_key(env):
    """清单原地改（同名、行数不同）不命中旧缓存：键里有清单文件的大小与 mtime。"""
    from guji_manager.review.cards import cards_cache_key
    f = _write_list("t525b", ["keben:1:1:3"])
    req = {"pages": "list:t525b", "limit": 30}
    k1 = cards_cache_key("keben", req, env)
    f.write_text("keben:1:1:3\nkeben:1:1:7\n", encoding="utf-8")
    assert cards_cache_key("keben", req, env) != k1


# ── C：closure_gaps ──────────────────────────────────────────────────

def test_closure_gaps_lists_decided_but_silent(env):
    gaps = closure_gaps("keben", [1], env)
    # 3：失效 → admit=False 没出字；5：名单 + 失效带字、没挂 human_char；6：挂了 human_char 算出字；
    # 4：有效裁决但产物还没重跑（admit=False）——闸照样报，提醒重跑 Step7
    assert [(g["id"], g["shape"], g["excluded"]) for g in gaps] == [
        ("keben:1:1:3", "困", False), ("keben:1:1:4", "天", False), ("keben:1:1:5", "玄", True)]


