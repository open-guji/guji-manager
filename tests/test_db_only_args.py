"""db --only 一次跟多个路径；pull/push/sync 多出的位置参数不再静默吞掉（11-26 全唐文救回人裁只推了第一个文件）。"""
import argparse

import pytest

from guji_manager import cli_db


def _parse(argv):
    ap = argparse.ArgumentParser()
    cli_db.add_parser(ap.add_subparsers(dest="cmd"))
    return ap.parse_args(argv)


def test_only_takes_many():
    a = _parse(["db", "push", "--only", "a.jsonl", "b.jsonl", "--only", "c/"])
    assert a.only == ["a.jsonl", "b.jsonl", "c/"] and a.args == []


def test_stray_positional_rejected():
    a = _parse(["db", "push", "x.jsonl", "--only", "a.jsonl"])
    with pytest.raises(SystemExit, match="不收这些参数"):
        cli_db.cmd_db(a)
