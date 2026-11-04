"""`guji check` 命令层（拆分 P2 第三批从 open-guji-cv tests/test_cli_papercuts.py、test_rulers.py 搬来）。"""

from __future__ import annotations

import argparse
import json


def test_check_pages_default_is_all_and_reports_which_pageset(monkeypatch, capsys):
    """`--pages` 缺省曾经是 `dev_set`：书级 `dev_set` 为空时悄悄退化成全书
    （凑巧对），非空时悄悄只算子集、不报警。改成默认 `all`；且不论默不默认，
    都要把「用了哪个页集、算了几页」打出来（走 stderr，别混进 `_out` 的
    JSON，管道接 jq 的人不受影响）。"""
    import open_guji_cv.core.book as book_mod
    import guji_manager.eval.quality as quality_mod
    import open_guji_cv.eval.rulers as rulers_mod
    from open_guji_cv.core.book import BookSpec
    from guji_manager import cli_eval

    from pathlib import Path as _P
    fake = BookSpec(id="fakebook", title="t", raw_dir=_P("does-not-matter"),
                    pages=[1, 2, 3], dev_set=[1])   # 非空 dev_set：旧默认会悄悄只算这一页
    # cmd_check 是函数内局部 import（`from .core.book import load_book` 等），
    # 每次调用都现从源模块取绑定，所以补丁要打在源模块上，不是 cli_eval 模块本身。
    monkeypatch.setattr(book_mod, "load_book", lambda *_a, **_k: fake)
    monkeypatch.setattr(quality_mod, "quality",
                        lambda book, pages, store: {"book": book, "pages": len(fake.resolve_pages(pages))})
    monkeypatch.setattr(rulers_mod, "measure",
                        lambda book, pages, store, full=False:
                            {"book": book, "n_pages": len(pages), "rulers": [], "full": full})

    args = argparse.Namespace(action="quality", book="fakebook", pages=None,
                              snapshot=False, note="", all_pages=False, full=False,
                              drift=False, out="")
    cli_eval.cmd_check(args)
    out, err = capsys.readouterr()
    assert json.loads(out)["pages"] == len(fake.all_pages())   # all，不是 dev_set 的 1 页
    assert "all" in err and "页" in err

    args2 = argparse.Namespace(action="rulers", book="fakebook", pages=None,
                               snapshot=False, note="", all_pages=False, full=False,
                               drift=False, out="")
    cli_eval.cmd_check(args2)
    out2, err2 = capsys.readouterr()
    assert json.loads(out2)["n_pages"] == len(fake.all_pages())
    assert "all" in err2 and "页" in err2


def test_check_rulers_detail_flag_prints_rows(monkeypatch, capsys):
    from guji_manager import cli_eval
    from open_guji_cv.eval import rulers
    fake = {"book": "b", "n_pages": 1, "rulers": [
        {"key": "R2c", "title": "缝后仍穿墨", "num": 2, "den": 9, "value": 22.2, "unit": "%",
         "detail": [{"page": 149, "col": 3, "y": 400, "why": "无缝"},
                    {"page": 149, "col": 7, "y": 88, "why": "缝上有墨", "px": 4}],
         "by_page": {"149": {"n": 2, "cols": [3, 7]}}}]}
    seen = {}

    def fake_measure(book, pages, st, full=False):
        seen["full"] = full
        return fake
    monkeypatch.setattr(rulers, "measure", fake_measure)
    monkeypatch.setattr("open_guji_cv.core.book.load_book",
                        lambda b: type("B", (), {"resolve_pages": lambda self, s: [149]})())
    args = type("A", (), {"action": "rulers", "book": "b", "pages": None, "full": False, "detail": "r2c"})()
    cli_eval.cmd_check(args)
    out = capsys.readouterr().out
    assert seen["full"] is True
    assert "p149    2 条  列 3,7" in out
    assert "p149\tc7\ty=88  why=缝上有墨  px=4" in out


def test_eval_run_allow_passes_through(monkeypatch, capsys):
    """`--allow heavy` 要真传进 run_eval；以前写死只放行 products，点名跑 heavy 的也全 skipped。"""
    from guji_manager import _cv, cli_eval

    seen = {}

    class _R:
        status = "ok"
        error = ""

        def summary_line(self):
            return "x"

        def warnings(self):
            return []

    def fake_run_eval(k, timeout=900, from_raw=False, allow=("products",)):
        seen[k] = allow
        return _R()

    monkeypatch.setattr(_cv, "run_eval", fake_run_eval, raising=False)
    base = dict(action="run", evals=["match_pairs"], timeout=1, json=False, strict=False, from_raw=False)
    import pytest
    with pytest.raises(SystemExit):                        # 跑完总是 sys.exit
        cli_eval.cmd_eval(argparse.Namespace(**base, allow="heavy, bench"))
    assert seen["match_pairs"] == ("products", "heavy", "bench")
    with pytest.raises(SystemExit):                        # 程序化调用没有 allow 键也不炸
        cli_eval.cmd_eval(argparse.Namespace(**base))
    assert seen["match_pairs"] == ("products",)
