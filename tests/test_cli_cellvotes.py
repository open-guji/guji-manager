"""`guji cellvotes` 命令层（拆分 P2 第二批从 open-guji-cv tests/test_web_votes.py 搬来；投票逻辑本身的测试留在 cv）。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from guji_manager import cli_cellvotes as C

BOOK, REV = "sitebk01", "004-r3"


def vote(a, choice, char="", voter="v1", ts=1, **kw):
    return {"v": 1, "book": BOOK, "vol": "004", "a": a, "rev": REV, "choice": choice,
            **({"char": char} if char else {}), "note": "", "voter": voter, "ts": ts, **kw}


def test_draft_with_pack_uses_issue_products(tmp_path, monkeypatch):
    """`--pack rev-…`：取回出单版产物包当产物根（取过就复用），不要 --cord；meta 记下产物根给 write 用。"""
    import argparse

    from guji_manager import cli_cellvotes as C
    from guji_manager.datastore import packs as PK
    ws = tmp_path / "ws"
    (ws / "feedback" / "events").mkdir(parents=True)
    monkeypatch.setenv("GUJI_WORKSPACE", str(ws))
    monkeypatch.delenv("GUJI_PRODUCTS_DIR", raising=False)
    fetched = []

    def fake_fetch(book, dest_root, label=None, force=False, src=None):
        fetched.append(label)
        (Path(dest_root) / book / "cell_shrink").mkdir(parents=True)
        return {"name": f"x/{label}", "dest": str(Path(dest_root) / book), "files": 1}

    monkeypatch.setattr(PK, "fetch_products", fake_fetch)
    votes = tmp_path / "votes.jsonl"
    votes.write_text(json.dumps(vote("1:1:1", "char", "甲")) + "\n", encoding="utf-8")
    out = tmp_path / "draft"
    args = argparse.Namespace(book="vol04", site_book=BOOK, rev=REV, cord=None, no_box_check=False, tol=8.0,
                              include_none=False, from_file=str(votes), from_kv=False, token_env="X",
                              source="测试", out=str(out), pack="rev-004-r3")
    C.cmd_draft(args)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["pack"] == "rev-004-r3" and meta["products_root"].endswith("_packs/rev-004-r3")
    assert os.environ["GUJI_PRODUCTS_DIR"] == meta["products_root"] and meta["ready"] == 1
    C.cmd_draft(args)
    assert fetched == ["rev-004-r3"]                                     # 第二次复用，不再取


def test_draft_carries_pending_reason_from_sheet(tmp_path, monkeypatch):
    """草稿事件带投票时那张单上的 pending_reason；格不在单上的写 unknown（sheldon 11-03）。"""
    import argparse

    from guji_manager import cli_cellvotes as C
    ws = tmp_path / "ws"
    (ws / "feedback" / "events").mkdir(parents=True)
    monkeypatch.setenv("GUJI_WORKSPACE", str(ws))
    sheet = tmp_path / "sheet.json"
    sheet.write_text(json.dumps({"rev": REV, "cells": [{"cell": "1:1:1", "pending_reason": "hard_pair"}]}),
                     encoding="utf-8")
    votes = tmp_path / "votes.jsonl"
    votes.write_text("\n".join(json.dumps(v) for v in (vote("1:1:1", "char", "甲"), vote("1:1:2", "char", "乙")))
                     + "\n", encoding="utf-8")
    out = tmp_path / "draft"
    args = argparse.Namespace(book="vol04", site_book=BOOK, rev=REV, cord=None, no_box_check=True, tol=8.0,
                              include_none=False, from_file=str(votes), from_kv=False, token_env="X",
                              source="测试", out=str(out), pack=None, sheet=str(sheet))
    C.cmd_draft(args)
    rows = {r["id"]: r for r in map(json.loads, (out / "drafts.jsonl").read_text(encoding="utf-8").splitlines())}
    assert rows["vol04:1:1:1"]["pending_reason"] == "hard_pair"
    assert rows["vol04:1:1:2"]["pending_reason"] == "unknown"


def test_draft_pages_parses_ids():
    rows = [{"id": "vol15:25:4:11a"}, {"id": "vol15:3:1:1"}, {"id": "vol15:25:2:2"}, {"id": "7:1:2"}, {"id": "坏"}, {}]
    assert C._draft_pages(rows) == [3, 7, 25]


def test_write_refuses_on_stale_patch_cache(monkeypatch):
    """ZM 11-17 建议 2：缓存与产物根对不上就拒写，免得静默写出指纹不符的锚。"""
    import guji_manager._cv as CV
    import guji_manager.ops.cache_verify as CVF
    called = {}

    class _B:
        id = "vol15"
    monkeypatch.setattr(CV, "load_book", lambda b: _B(), raising=False)
    monkeypatch.setattr(CV, "default_pipeline_id", lambda b: "p", raising=False)
    monkeypatch.setattr(CV, "_engine", lambda *a, **k: object(), raising=False)

    def fake_verify(eng, pages, fix=False, log=None, full=False):
        called["pages"], called["fix"] = list(pages), fix
        return {"bad_columns": 2, "bad_pages": [25]}
    monkeypatch.setattr(CVF, "verify_book", fake_verify)
    with pytest.raises(SystemExit) as e:
        C._check_patch_cache("vol15", [{"id": "vol15:25:4:11a"}])
    assert called == {"pages": [25], "fix": True}
    assert "guji cache warm --book vol15 --pages 25" in str(e.value)

    monkeypatch.setattr(CVF, "verify_book", lambda *a, **k: {"bad_columns": 0, "bad_pages": []})
    C._check_patch_cache("vol15", [{"id": "vol15:25:4:11a"}])     # 不抛


def test_write_cache_check_soft_fails_without_engine(monkeypatch, capsys):
    import guji_manager._cv as CV

    def boom(b):
        raise FileNotFoundError("没有册配置")
    monkeypatch.setattr(CV, "load_book", boom, raising=False)
    C._check_patch_cache("vol15", [{"id": "vol15:25:4:11a"}])
    assert "没核字块缓存" in capsys.readouterr().out + capsys.readouterr().err


def _empty_args(tmp_path, monkeypatch, **kw):
    import argparse
    ws = tmp_path / "ws"
    (ws / "feedback" / "events").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GUJI_WORKSPACE", str(ws))
    monkeypatch.setenv("TOK", "t")
    base = dict(book="vol04", site_book=BOOK, rev=REV, cord=None, no_box_check=True, tol=8.0, include_none=False,
                from_file=None, from_kv=True, token_env="TOK", source="测试", out=str(tmp_path / "draft"),
                pack=None, sheet=None, items=False, allow_empty=False)
    return argparse.Namespace(**{**base, **kw})


def test_draft_zero_votes_needs_allow_empty_and_full_site_read(tmp_path, monkeypatch):
    """零票（殿本 21–99 册旧单，ZM 11-18）：缺省照旧拒绝；--allow-empty 且网站按单版、按条目都读全为 0 才出空草稿。"""
    monkeypatch.setattr(C, "_fetch_kv", lambda *a, **k: [])
    monkeypatch.setattr(C, "_fetch_kv_items", lambda *a, **k: [])
    with pytest.raises(SystemExit, match="别拿空草稿"):
        C.cmd_draft(_empty_args(tmp_path, monkeypatch))
    args = _empty_args(tmp_path, monkeypatch, allow_empty=True)
    C.cmd_draft(args)
    meta = json.loads((tmp_path / "draft" / "meta.json").read_text(encoding="utf-8"))
    assert meta["ready"] == 0 and meta["n_votes"] == 0
    assert meta["empty_confirmed"]["by_rev"] == 0 and meta["empty_confirmed"]["by_item"] == 0
    assert (tmp_path / "draft" / "drafts.jsonl").read_text(encoding="utf-8") == ""


def test_draft_allow_empty_refuses_file_or_lost_item_votes(tmp_path, monkeypatch):
    votes = tmp_path / "votes.jsonl"
    votes.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit, match="只认 --from-kv"):
        C.cmd_draft(_empty_args(tmp_path, monkeypatch, from_kv=False, from_file=str(votes), allow_empty=True))
    # 网站上这一章有条目票、但条目找不到（丢掉）→ 可用票 0 条，也不算零票
    monkeypatch.setattr(C, "_fetch_kv", lambda *a, **k: [])
    monkeypatch.setattr(C, "_fetch_kv_items", lambda *a, **k: [{"vol": "004", "item": "nope", "choice": "char"}])
    with pytest.raises(SystemExit, match="不是零票"):
        C.cmd_draft(_empty_args(tmp_path, monkeypatch, allow_empty=True))


def test_bound_only_drops_rulings_not_effective_now(monkeypatch):
    """ZM 11-19：迁移锚／rebound 到别格／seed_admit 不采信的旧人裁不算「已有人裁」，同字票照写。"""
    import types
    import guji_manager._cv as cvmod
    from guji_manager import cli_cellvotes as CVT
    ev = lambda i, k, sh: types.SimpleNamespace(id=i, ts="2026-11-01T00:00:00Z", target=types.SimpleNamespace(key=k),  # noqa: E731
                                                payload={"v": "confirm", "shape": sh})
    human = {"vol18:33:4:7a": ev("e1", "vol18:33:4:7a", "兩"), "vol18:70:6:16": ev("e2", "vol18:70:6:16", "名"),
             "vol18:88:1:12a": ev("e3", "vol18:88:1:12a", "領"), "vol18:5:1:1": ev("e4", "vol18:5:1:1", "之"),
             "vol18:9:9:9": ev("e5", "vol18:9:9:9", "也")}
    rows = {"e1": {"status": "unanchored", "bound": None}, "e2": {"status": "valid", "bound": "vol18:70:6:16"},
            "e3": {"status": "rebound", "bound": "vol18:88:1:13a"}, "e4": {"status": "valid", "bound": "vol18:5:1:1"}}
    monkeypatch.setattr(cvmod, "book_bindings", lambda book, pages=None: rows, raising=False)
    monkeypatch.setattr(cvmod, "bindings_usable", lambda r, ts=None: (r or {}).get("bound") if (r or {}).get("status") in ("valid", "rebound") else None, raising=False)
    monkeypatch.setattr(cvmod, "human_chars", lambda book: {"vol18:70:6:16": "各", "vol18:5:1:1": "之"}, raising=False)
    votes = [{"a": a} for a in ("33:4:7a", "70:6:16", "88:1:12a", "5:1:1")]       # 9:9:9 没票：不动
    out, gone = CVT._bound_only("vol18", human, votes)
    assert set(out) == {"vol18:5:1:1", "vol18:9:9:9"}
    assert {a for a, _ in gone} == {"33:4:7a", "70:6:16", "88:1:12a"}
