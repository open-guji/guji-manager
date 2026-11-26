"""`guji corpus pin` 命令层：argparse 定义的参数与 cmd_corpus 读的属性要对得上。

曾经 cmd_corpus 读 `args.shift_book_ver`（parser 只定义了 `--book-ver`），pin 一跑就 AttributeError（A31 11-07 报）。
这里走真 parser＋真 append_pin（--dev 跳过各层清单存在检查），不用 SimpleNamespace 手拼 args。"""

from __future__ import annotations

import argparse
import json

import pytest

from guji_manager import cli_glyph


def _parse(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    cli_glyph.add_parser(ap.add_subparsers(dest="cmd"))
    return ap.parse_args(argv)


@pytest.fixture
def ws(tmp_path):
    from open_guji_cv.core.corpus_pin import pins_path
    p = pins_path(tmp_path, "vol05")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"rows": [{"n": 3, "global": 7, "book": 16, "vol": None,
                                       "date": "2026-10-01", "note": ""}]}), encoding="utf-8")
    return tmp_path


def _rows(ws):
    from open_guji_cv.core.corpus_pin import load_pins
    return load_pins(ws, "vol05")


@pytest.mark.parametrize("flags, want", [
    (["--book-ver", "18"], {"global": 7, "book": 18, "vol": None}),
    (["--global-ver", "8"], {"global": 8, "book": 16, "vol": None}),
    (["--vol-ver", "2"], {"global": 7, "book": 16, "vol": 2}),
    (["--global-ver", "8", "--book-ver", "18", "--vol-ver", "1"], {"global": 8, "book": 18, "vol": 1}),
])
def test_pin_reads_each_layer_flag(ws, capsys, flags, want):
    args = _parse(["corpus", "pin", "--vol", "vol05", "--dev", "-w", str(ws), *flags])
    cli_glyph.cmd_corpus(args)
    last = _rows(ws)[-1]
    assert {k: last.get(k) for k in want} == want
    assert last["n"] == 4 and last["dev"] is True
    assert "corpus: 4" in capsys.readouterr().out


def test_pin_same_layers_refused_not_crash(ws, capsys):
    args = _parse(["corpus", "pin", "--vol", "vol05", "--dev", "-w", str(ws), "--book-ver", "16"])
    with pytest.raises(SystemExit) as e:
        cli_glyph.cmd_corpus(args)
    assert e.value.code == 1 and "不空升" in capsys.readouterr().err
    assert len(_rows(ws)) == 1


def test_vol_default_pin_follows_book_yaml_not_ledger_tail(ws, monkeypatch):
    """钉子账末行可能是撤掉没用的号（W1 试跑后殿本各册账末行 b35、yaml 已指回原号）：verify／upload 缺省按 yaml。"""
    from open_guji_cv.core.corpus_pin import pins_path
    from guji_manager._cv import load_pins
    p = pins_path(ws, "vol05")
    rows = json.loads(p.read_text(encoding="utf-8"))["rows"]
    rows.append({"n": 4, "global": 9, "book": 16, "vol": None, "date": "2026-11-25", "note": "W1"})
    p.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    books = ws / "books"
    books.mkdir()
    monkeypatch.setattr("guji_manager._cv.books_dir", lambda w=None: books, raising=False)
    assert cli_glyph._vol_current_pin(ws, "vol05", load_pins) == 4          # 没 yaml：退回账末行
    (books / "vol05.yaml").write_text("id: vol05\ncorpus: 3\n", encoding="utf-8")
    assert cli_glyph._vol_current_pin(ws, "vol05", load_pins) == 3          # yaml 为准


def test_vol_default_pin_honors_run_override(ws, monkeypatch):
    """rerun_prep 换语料号走 GUJI_BOOK_OVERRIDE、不改 yaml：verify 缺省号要认覆盖（#17727 用了 yaml 的旧号）。"""
    from open_guji_cv.core.book_config import OVERRIDE_ENV
    from guji_manager._cv import load_pins
    books = ws / "books"
    books.mkdir()
    monkeypatch.setattr("guji_manager._cv.books_dir", lambda w=None: books, raising=False)
    (books / "vol05.yaml").write_text("id: vol05\ncorpus: 3\n", encoding="utf-8")
    monkeypatch.delenv(OVERRIDE_ENV, raising=False)
    assert cli_glyph._vol_current_pin(ws, "vol05", load_pins) == 3
    monkeypatch.setenv(OVERRIDE_ENV, json.dumps({"corpus": 4}))
    assert cli_glyph._vol_current_pin(ws, "vol05", load_pins) == 4
