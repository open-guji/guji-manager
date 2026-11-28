# -*- coding: utf-8 -*-
"""改册名后 R2 原图登记（11-28 北行 bxgb→1，#18346 取原图 404）。"""
from __future__ import annotations

from guji_manager import cli_source as C
from guji_manager.datastore import sources as S
from guji_manager.ops import rename_volume as RV


class _Fake:
    def __init__(self, have):
        self.have = dict(have)          # (ws, 册) → (书 id, 册号)

    def resolve(self, src, ws, book):
        if (ws, book) not in self.have:
            raise FileNotFoundError(book)
        return self.have[(ws, book)]


def test_resolve_falls_back_to_alias(monkeypatch):
    f = _Fake({("beixing-guben", "bxgb"): ("988g7gsqhd", "01")})
    monkeypatch.setattr(C, "_aliases", lambda b: ["bxgb"])
    assert C._resolve_alias(None, f, "beixing-guben", "1") == ("988g7gsqhd", "01")


def test_resolve_no_alias_still_raises(monkeypatch):
    f = _Fake({})
    monkeypatch.setattr(C, "_aliases", lambda b: ["bxgb"])
    try:
        C._resolve_alias(None, f, "beixing-guben", "1")
    except FileNotFoundError:
        return
    raise AssertionError("应报找不到")


def test_r2_pointers_writes_new_name(monkeypatch):
    wrote = []
    monkeypatch.setattr(S, "resolve", lambda src, ws, b: ("988g7gsqhd", "01") if b == "bxgb" else (_ for _ in ()).throw(FileNotFoundError(b)))
    monkeypatch.setattr(S, "write_pointer", lambda src, ws, b, bid, v: wrote.append((ws, b, bid, v)))
    out = RV.r2_pointers({"bxgb": "1", "yy": "2"}, "beixing-guben", src=object())
    assert wrote == [("beixing-guben", "1", "988g7gsqhd", "01")]
    assert "跳过" in out[1]


def test_r2_pointers_dry_run(monkeypatch):
    monkeypatch.setattr(S, "resolve", lambda src, ws, b: ("x", "01"))
    monkeypatch.setattr(S, "write_pointer", lambda *a: (_ for _ in ()).throw(AssertionError("不该写")))
    assert "要写" in RV.r2_pointers({"a": "1"}, "w", write=False, src=object())[0]
