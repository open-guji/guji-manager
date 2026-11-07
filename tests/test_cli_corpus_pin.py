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
