"""guji_manager.hooks：经入口点 `guji.hooks` 给 cv 的 `guji` 命令登记钩子（拆分 P4）。"""
from __future__ import annotations

from importlib.metadata import entry_points
from types import SimpleNamespace

from guji_manager import hooks as H


def test_entry_point_registered():
    assert any(ep.value == "guji_manager.hooks:register" for ep in entry_points(group="guji.hooks"))


def test_register_fills_all_points():
    got = {}
    H.register(SimpleNamespace(add=lambda point, fn: got.setdefault(point, []).append(fn)))
    assert set(got) == {"startup", "prepare", "finished", "status"}


def test_prepare_skips_rare_index_unless_step_runs(monkeypatch):
    calls = []
    for name in ("ensure_glyph_pin", "ensure_model_pin", "ensure_corpus_files"):
        monkeypatch.setattr(H.prep, name, lambda book, n=name: calls.append(n))
    monkeypatch.setattr(H.prep, "ensure_rare_index", lambda book_id, jobs=1: calls.append(("rare", jobs)))
    book = SimpleNamespace(id="vol01")
    H.prepare(book, ["glyph_match"], 2)
    assert calls == ["ensure_glyph_pin", "ensure_model_pin", "ensure_corpus_files"]
    calls.clear()
    H.prepare(book, ["rare_candidates"], 3)
    assert calls[-1] == ("rare", 3)


def test_finished_packs_only_when_ok(monkeypatch):
    calls = []
    monkeypatch.setattr(H.prep, "auto_pack", lambda *a: calls.append("pack"))
    monkeypatch.setattr(H.prep, "print_unpacked", lambda book, store: calls.append("note"))
    eng = SimpleNamespace(book=SimpleNamespace(id="vol01"), store=None)
    H.finished(SimpleNamespace(), eng, ["a"], False)
    assert calls == ["note"]
    calls.clear()
    H.finished(SimpleNamespace(), eng, ["a"], True)
    assert calls == ["pack", "note"]


def test_status_rows_keys(monkeypatch):
    monkeypatch.setattr(H, "_closure_gaps", lambda b, p, s: ([], []))
    monkeypatch.setattr(H, "_vision_pending", lambda b, p, s: None)
    rows = H.status("vol01", [1], None)
    assert [r[0] for r in rows] == ["closure_gaps", "closure_mismatches", "vision_pending", None]
    assert all(callable(r[2]) for r in rows)
