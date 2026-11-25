"""字块随包存 R2（datastore/patch_packs.py，2026-11-25）：打包、核对、取回、存、清理。不连网，假 Worker。"""
from __future__ import annotations

import io
import json
import tarfile
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from guji_manager._cv import ImageCache
from guji_manager.datastore import patch_packs as PP

FP = "0123456789abcdef"


def _cache(tmp_path):
    c = ImageCache(root=tmp_path / "cache")
    for k in ("p0024c01s1", "p0024c01s2", "p0024c02s1a"):
        c.put("bk", "char_patch", k, np.full((8, 8), 7, np.uint8), stamp="S1")
    c.put("bk", "char_patch", "p00241c01s1", np.zeros((8, 8), np.uint8))     # 别的页（五位页号），不能混进来
    return c


class FakeSrc:
    def __init__(self):
        self.objs: dict[str, bytes] = {}
        self.calls: list[tuple[str, str]] = []

    def _call(self, method, path, query=None, data=None, raw=False, **kw):
        self.calls.append((method, path))
        if path == "/v1/packs":
            pre = query["prefix"]
            return {"packs": [{"key": k, "bytes": len(v)} for k, v in sorted(self.objs.items()) if k.startswith(pre)]}
        key = path[len("/v1/packs/"):]
        if method == "PUT":
            self.objs[key] = data
            return {}
        if method == "DELETE":
            self.objs.pop(key, None)
            return {}
        return self.objs[key]


def test_page_files_skip_other_pages(tmp_path):
    names = [p.name for p in PP._page_files(_cache(tmp_path), "bk", 24)]
    assert names == ["p0024c01s1.png", "p0024c01s2.png", "p0024c02s1a.png"]


def test_roundtrip_and_checks(tmp_path):
    src = _cache(tmp_path)
    data = PP.build_tar(src, "bk", 24, FP, "S1")
    assert PP.build_tar(src, "bk", 25, FP, "S1") is None
    dst = ImageCache(root=tmp_path / "other")
    assert PP.unpack(data, dst, "bk", 24, FP, "S1") == 3
    for k in ("p0024c01s1", "p0024c01s2", "p0024c02s1a"):
        assert dst.get("bk", "char_patch", k, stamp="S1").read_bytes() == src.path("bk", "char_patch", k).read_bytes()
    assert dst.page_stamp("bk", "char_patch", "p0024") == "S1"
    with pytest.raises(ValueError, match="戳"):
        PP.unpack(data, ImageCache(root=tmp_path / "x1"), "bk", 24, FP, "S2")
    with pytest.raises(ValueError):
        PP.unpack(data, ImageCache(root=tmp_path / "x2"), "bk", 24, "f" * 16, "S1")
    # 改一张图的字节 → sha 对不上，一张都不写
    buf = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(data)) as tf, tarfile.open(fileobj=buf, mode="w") as out:
        for m in tf.getmembers():
            b = tf.extractfile(m).read()
            if m.name == "p0024c01s2.png":
                b = b[:-1] + bytes([b[-1] ^ 1])
            m.size = len(b)
            out.addfile(m, io.BytesIO(b))
    x3 = ImageCache(root=tmp_path / "x3")
    with pytest.raises(ValueError, match="sha256"):
        PP.unpack(buf.getvalue(), x3, "bk", 24, FP, "S1")
    assert not (tmp_path / "x3" / "bk").exists()


def test_fetcher(tmp_path, monkeypatch):
    fake = FakeSrc()
    fake.objs[PP.object_key("ws1", "bk", 24, FP, "20261120")] = PP.build_tar(_cache(tmp_path), "bk", 24, FP, "S1")
    monkeypatch.setattr(PP, "_SRC", {"r": fake, "ws": "ws1"})
    monkeypatch.setattr(PP, "_INDEX", {})
    dst = ImageCache(root=tmp_path / "dst")
    assert PP.fetcher("bk", "char_patch", 24, FP, dst, "S1") is True
    assert dst.get("bk", "char_patch", "p0024c01s1", stamp="S1") is not None
    assert PP.fetcher("bk", "char_patch", 24, "f" * 16, dst, "S1") is False      # 指纹不同 = 切分变了，不取
    assert PP.fetcher("bk", "char_patch", 25, FP, dst, "S1") is False
    assert PP.fetcher("bk", "column_image", 24, FP, dst, "S1") is False
    assert sum(1 for m, p in fake.calls if p == "/v1/packs") == 1                  # 每册只列一次


def test_fetcher_no_token(monkeypatch, tmp_path):
    monkeypatch.setattr(PP, "_SRC", {})
    for k in ("GUJI_DATA_TOKEN_READ", "GUJI_DATA_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    assert PP.fetcher("bk", "char_patch", 24, FP, ImageCache(root=tmp_path), None) is False


def test_install_registers_fetcher(monkeypatch):
    from guji_manager._cv import core_derived as derived
    if not hasattr(derived, "PAGE_FETCHER"):
        pytest.skip("cv 太旧，没有 PAGE_FETCHER")
    monkeypatch.setattr(derived, "PAGE_FETCHER", None)
    assert PP.install() is True and derived.PAGE_FETCHER is PP.fetcher


def _ent(sha):
    return SimpleNamespace(status="ok", sha256=sha, fingerprint="x")


def test_push_book(tmp_path, monkeypatch):
    cache = _cache(tmp_path)
    cache.put("bk", "char_patch", "p0025c01s1", np.zeros((8, 8), np.uint8), stamp="OLD")
    man = {"p0024": _ent("S1"), "p0025": _ent("S2")}                 # p0025 缓存戳是旧的：不存
    ctx = SimpleNamespace(book=SimpleNamespace(id="bk"), cache=cache,
                          store=SimpleNamespace(manifest=lambda b, s: man),
                          chain_fingerprint=lambda s, p: FP)
    monkeypatch.setattr("guji_manager.datastore.packs._ws_name", lambda: "ws1")
    fake = FakeSrc()
    res = PP.push_book(ctx, [24, 25, 26], src=fake)
    assert (res["pushed"], res["stale_cache"], res["no_product"]) == (1, 1, 1)
    (key,) = fake.objs
    o = PP.parse_key(key)
    assert (o.ws, o.book, o.page, o.fp) == ("ws1", "bk", "p0024", FP)
    res = PP.push_book(ctx, [24], src=fake)                           # 再存一次：已有，不重传
    assert (res["pushed"], res["already"]) == (0, 1) and len(fake.objs) == 1


def test_gc_plan():
    def o(page, fp, day):
        return PP.parse_key(f"derived/patch/w/bk/{page}.{fp}.{day}.tar", 10)
    objs = [o("p0001", "a" * 16, "20261101"), o("p0001", "b" * 16, "20261110"),   # 旧、过了 7 天 → 删
            o("p0001", "c" * 16, "20261120"),                                      # 7 天内 → 留
            o("p0001", "d" * 16, "20261124"),                                      # 最新 → 留
            o("p0002", "a" * 16, "20261001")]                                      # 这页只有它（最新）→ 留
    drop = PP.gc_plan(objs, keep_days=7, now=datetime(2026, 11, 25, tzinfo=timezone.utc))
    assert [x.fp[0] for x in drop] == ["a", "b"] and all(x.page == "p0001" for x in drop)


def test_key_shape():
    k = PP.object_key("ws1", "bk", 24, FP, "20261125")
    assert k == f"derived/patch/ws1/bk/p0024.{FP}.20261125.tar" and PP.parse_key(k).day == "20261125"
