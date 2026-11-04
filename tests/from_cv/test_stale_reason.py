# -*- coding: utf-8 -*-
"""`guji status` 的过期原因（overview #174）：改了 yaml 的 `period_prior`（`book_deps`），
status 要说清「册配置 period_prior 180.0→204.0，须重跑」，而不只是报一个过期数；
`calibrate` 在先验漂了时要提示哪些步会过期。合成步骤、纯 tmp 数据，不碰真书。"""
from __future__ import annotations

import dataclasses

import cv2
import numpy as np
import pytest
from pydantic import BaseModel

import open_guji_cv.steps  # noqa: F401  —— 注册 raw_page 等产物种类

from open_guji_cv.core.book import BookSpec
from open_guji_cv.core.engine import FRESH, STALE, Engine
from open_guji_cv.core.pipeline import Pipeline
from open_guji_cv.core.spec import ProductKindSpec, StepSpec
from open_guji_cv.core.step import KINDS, STEPS, Step, register_kind, register_step
from open_guji_cv.products.cache import ImageCache
from open_guji_cv.products.store import ProductStore


class _Per(BaseModel):
    page: int
    period: float


class _P(BaseModel):
    gain: float = 1.0
    corpus_fingerprint: str = ""        # 共享输入的指纹字段（close-check 1a 按字段名分类）


if "t_sr_per" not in KINDS:
    register_kind(ProductKindSpec(id="t_sr_per", title="per", storage="numeric", unit="page", schema=_Per))
    register_kind(ProductKindSpec(id="t_sr_down", title="down", storage="numeric", unit="page", schema=_Per))

if "t_sr_gate" not in STEPS:
    @register_step
    class _Gate(Step):
        spec = StepSpec(id="t_sr_gate", title="合成闸2", version="1", unit="page",
                        consumes=("raw_page",), produces=("t_sr_per",), params=_P,
                        book_deps=("period_prior",))

        def run_page(self, ctx, page):
            return {"t_sr_per": _Per(page=page, period=float(ctx.book.period_prior or 0))}

    @register_step
    class _Down(Step):
        spec = StepSpec(id="t_sr_down", title="下游", version="1", unit="page",
                        consumes=("t_sr_per",), produces=("t_sr_down",), params=_P)

        def run_page(self, ctx, page):
            return {"t_sr_down": ctx.product("t_sr_per", page)}


@pytest.fixture
def world(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    for pg in (1, 2):
        cv2.imwrite(str(raw / f"{pg}.png"), np.full((20, 20), 200, np.uint8))
    book = BookSpec(id="tsr", title="t", raw_dir=raw, dev_set=[1, 2], period_prior=180.0)
    pl = Pipeline(id="tsr", title="t", steps=["t_sr_gate", "t_sr_down"])
    pl.validate()
    return book, pl, ProductStore(tmp_path / "products"), ImageCache(tmp_path / "cache")


def _eng(book, pl, store, cache, params=None):
    return Engine(book, pl, store=store, cache=cache, params=params, log=lambda s: None)


def _code_only_stale(store, cv_version, steps=("t_sr_gate",)):
    """把指定步的条目改成「只是代码变了」：指纹作废，其余（参数、册配置、上游）原样；记上 cv_version。"""
    for sid in steps:
        m = store.manifest("tsr", sid)
        for k, e in m.all().items():
            m.put(dataclasses.replace(e, fingerprint="0" * 24, cv_version=cv_version))


def test_close_check_1a_code_only_and_strict_cv(world):
    from guji_manager.ops import close_check as CC
    book, pl, store, cache = world
    _eng(book, pl, store, cache).run()
    _code_only_stale(store, "0.4.4")
    eng = _eng(book, pl, store, cache)
    it = CC._fresh(eng, [1, 2])
    assert it["status"] == CC.PASS and "2 页只是代码" in it["detail"] and "0.4.4×2" in it["detail"]
    assert CC._fresh(eng, [1, 2], strict_cv=True)["status"] == CC.FAIL


def test_close_check_1a_separates_shared_inputs(world):
    """复盘 I（册 005，10-23）：只因共享输入（语料、证人、格位表……）被别处更新而过期，1a 单列不算失败；
    本册参数一起变了就照旧失败，两类都报。旧条目分不出字段的照旧失败。"""
    from guji_manager.ops import close_check as CC
    book, pl, store, cache = world
    _eng(book, pl, store, cache).run()
    shared = _eng(book, pl, store, cache, params={"t_sr_gate": {"corpus_fingerprint": "v2"}})
    st = shared.status()
    assert st["steps"]["t_sr_gate"]["stale_reasons"] == {"参数变了：corpus_fingerprint": 2}
    it = CC._fresh(shared, [1, 2])
    assert it["status"] == CC.PASS and "共享输入被别处更新：corpus_fingerprint×2" in it["detail"]
    assert it["data"] == {"shared_inputs": {"corpus_fingerprint": 2}}
    both = _eng(book, pl, store, cache, params={"t_sr_gate": {"corpus_fingerprint": "v2", "gain": 2.0}})
    it = CC._fresh(both, [1, 2])
    assert it["status"] == CC.FAIL and it["data"]["t_sr_gate"]["reasons"] == {"参数变了：corpus_fingerprint、gain": 2}
    own = _eng(book, pl, store, cache, params={"t_sr_gate": {"gain": 2.0}})
    it = CC._fresh(own, [1, 2])
    assert it["status"] == CC.FAIL and "共享" not in it["detail"]
    m = store.manifest("tsr", "t_sr_gate")
    for k, e in m.all().items():
        m.put(dataclasses.replace(e, param_parts=None))
    assert CC._fresh(shared, [1, 2])["status"] == CC.FAIL


def test_shared_only_parses_reason():
    from guji_manager.ops.close_check import _shared_only
    assert _shared_only("参数变了：layout_fingerprint、witness_fingerprint") == ["layout_fingerprint", "witness_fingerprint"]
    assert _shared_only("参数变了：layout_fingerprint、human_fingerprint") is None
    assert _shared_only("参数变了") is None and _shared_only("册配置 groups a→b") is None
