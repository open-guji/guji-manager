# -*- coding: utf-8 -*-
"""交单核册名（11-28 北行 #18319 bxgb→1、殿本 #18292 01≠vol01）。"""
from __future__ import annotations

import json

from guji_manager.jobs import book_check as B
from guji_manager.jobs import runner as R

BX = [("1", ["bxgb"])]
ZM = [(f"vol{i:02d}", []) for i in range(1, 100)]
MJ = [(str(i), ["%02d" % i]) for i in range(1, 7)]


def test_current_name_passes():
    assert B.resolve_name("1", BX) == ("1", "")


def test_alias_maps_to_new_name():
    name, msg = B.resolve_name("bxgb", BX)
    assert name == "1" and "改名" in msg


def test_numeric_equal_maps():
    assert B.resolve_name("001", MJ)[0] == "1"


def test_unknown_rejected_with_hint():
    name, msg = B.resolve_name("01", ZM)
    assert name is None and "vol01" in msg


def test_unknown_lists_names():
    name, msg = B.resolve_name("xx", ZM)
    assert name is None and "共 99 册" in msg


def test_find_ws_by_id_or_dir():
    rows = [("beixing-guben", "988g7gsqhd-北行日錄"), ("988g3f0wsu", "sjws")]
    assert B.find_ws(rows, "988g7gsqhd-*") == "beixing-guben"
    assert B.find_ws(rows, "988g3f0wsu-*") == "988g3f0wsu"
    assert B.find_ws(rows, "96mid1ogzk-*") is None


class _Cur:
    def __init__(self):
        self.q = None

    def execute(self, sql, args=None):
        self.q = sql

    def fetchall(self):
        if "workspaces" in self.q:
            return [("beixing-guben", "988g7gsqhd-北行日錄")]
        return [("1", json.dumps({"id": "1", "aliases": ["bxgb"]}))]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Conn(_Cur):
    def cursor(self):
        return _Cur()


def test_check_rewrites_raw():
    raw = {"book": "bxgb", "ws_glob": "988g7gsqhd-*"}
    assert B.check(raw, default_glob="96mid1ogzk-*", connect=_Conn) is None
    assert raw["book"] == "1"


def test_check_rejects():
    raw = {"book": "2", "ws_glob": "988g7gsqhd-*"}
    assert "没有" in B.check(raw, default_glob="96mid1ogzk-*", connect=_Conn)


def test_check_offline_passes():
    def boom():
        raise SystemExit("no db")
    raw = {"book": "bxgb", "ws_glob": "988g7gsqhd-*"}
    assert B.check(raw, default_glob="x", connect=boom) is None and raw["book"] == "bxgb"


def test_runner_missing_book_yaml_is_config_error():
    err = ("bash /root/.guji-jobs/prep/rerun_prep.sh bxgb 退出码 2：ls: cannot access "
           "'/root/.guji-data/main/beixing-guben/books/bxgb.yaml': No such file or directory")
    assert R._CONFIG_ERR.search(err)
    assert R._NO_BOOK_YAML.search(err).group(1) == "bxgb"
