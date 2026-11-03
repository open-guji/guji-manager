"""`guji cellvotes` 命令层（拆分 P2 第二批从 open-guji-cv tests/test_web_votes.py 搬来；投票逻辑本身的测试留在 cv）。"""

from __future__ import annotations

import json
import os
from pathlib import Path

BOOK, REV = "sitebk01", "004-r3"


def vote(a, choice, char="", voter="v1", ts=1, **kw):
    return {"v": 1, "book": BOOK, "vol": "004", "a": a, "rev": REV, "choice": choice,
            **({"char": char} if char else {}), "note": "", "voter": voter, "ts": ts, **kw}


def test_draft_with_pack_uses_issue_products(tmp_path, monkeypatch):
    """`--pack rev-…`：取回出单版产物包当产物根（取过就复用），不要 --cord；meta 记下产物根给 write 用。"""
    import argparse

    from guji_manager import cli_cellvotes as C
    from open_guji_cv.datastore import packs as PK
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
