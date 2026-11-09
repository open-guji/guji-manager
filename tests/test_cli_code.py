# -*- coding: utf-8 -*-
"""guji code：书级代码清单与 import 护栏（cv core/book_code，2026-11-09）。"""
import argparse
import json

import pytest

pytest.importorskip("open_guji_cv.core.book_code")

from guji_manager import cli_code  # noqa: E402


def _args(**kw):
    d = {"workspace": None, "version": None, "note": "", "samples": ""}
    d.update(kw)
    return argparse.Namespace(**d)


def _book(tmp_path, files):
    code = tmp_path / "code"
    code.mkdir()
    (code / "code.yaml").write_text("name: tb\nbase: keben\n", encoding="utf-8")
    for k, v in files.items():
        (code / k).write_text(v, encoding="utf-8")
    return code


def test_import_guard(tmp_path):
    code = _book(tmp_path, {"a.py": "from open_guji_cv.seg import seam\nfrom open_guji_cv.steps import x\n"
                                    "from ...core import y\nimport guji_book.other.z\n"})
    bad = cli_code.import_problems(code, "tb")
    assert len(bad) == 3 and "open_guji_cv.steps" in bad[0]
    (code / "tests").mkdir()
    (code / "tests" / "test_a.py").write_text("from open_guji_cv.steps import x\n", encoding="utf-8")
    assert len(cli_code.import_problems(code, "tb")) == 3          # tests/ 不查


def test_release_verify(tmp_path, capsys):
    code = _book(tmp_path, {"a.py": "A = 1\n"})
    cli_code.cmd_code(_args(code_cmd="release", workspace=str(tmp_path)))
    assert (code / "releases" / "k1.json").is_file()
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        cli_code.cmd_code(_args(code_cmd="verify", workspace=str(tmp_path)))
    assert e.value.code == 0 and json.loads(capsys.readouterr().out)["clean"] is True
    (code / "a.py").write_text("A = 2\n")
    with pytest.raises(SystemExit) as e:
        cli_code.cmd_code(_args(code_cmd="verify", workspace=str(tmp_path)))
    assert e.value.code == 1


def test_status_without_code(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        cli_code.cmd_code(_args(code_cmd="status", workspace=str(tmp_path)))
    assert e.value.code == 0 and json.loads(capsys.readouterr().out)["code"] is None
