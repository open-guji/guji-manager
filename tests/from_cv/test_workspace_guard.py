# -*- coding: utf-8 -*-
"""跑批前必须显式声明库来源（`core/workspace.py::assert_workspace_declared`）。

2026-09-09 实锤：控制台在本机重启时漏带 `GUJI_WORKSPACE`，静默退回到仓内
那份几百条记录的示例库，vol02 101-150 页对着它跑了一遍——库匹配全给
`unsure`、上下文兜底救不回来、连 8-gram 锚定整理本都锚不上，而产物全程
`status: ok`，直到翻 `code_rev`/`params_hash` 才看出问题。根治：没声明
`GUJI_WORKSPACE`/`GUJI_GLYPH_DB`、又没显式放行时，跑批直接拒绝。
"""
from __future__ import annotations

import os

import pytest

from open_guji_cv.core import workspace as W
from open_guji_cv.core.workspace import (assert_workspace_declared,
                                         using_sample_db)

_RUNTIME_ENV = ("GUJI_PRODUCTS_DIR", "GUJI_CACHE_DIR", "GUJI_BATCHES_DIR",
                "GUJI_EXCLUSIONS", "GUJI_FEEDBACK_DIR")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """相关环境变量本测试内独立，不受运行环境影响、不泄漏出去。"""
    for k in ("GUJI_WORKSPACE", "GUJI_GLYPH_DB", "GUJI_ALLOW_SAMPLE_DB", *_RUNTIME_ENV):
        monkeypatch.delenv(k, raising=False)
    yield


# ── 运行时数据五个根全部跟着 GUJI_WORKSPACE 走（用户 2026-09-13 裁定） ──

_RUNTIME_ROOTS = [
    (W.products_root, "GUJI_PRODUCTS_DIR", W.PRODUCTS_REL),
    (W.cache_root, "GUJI_CACHE_DIR", W.CACHE_REL),
    (W.batches_root, "GUJI_BATCHES_DIR", W.BATCHES_REL),
    (W.exclusions_path, "GUJI_EXCLUSIONS", W.EXCLUSIONS_REL),
    (W.feedback_root, "GUJI_FEEDBACK_DIR", W.FEEDBACK_REL),
]


def test_default_stores_resolve_workspace_at_call_time(monkeypatch, tmp_path):
    """默认根在**调用时**解析，不在导入时定死——GUJI_WORKSPACE 常在模块导入之后才设。"""
    from open_guji_cv.products.cache import ImageCache
    from open_guji_cv.products.store import ProductStore
    from guji_manager.review.batches import default_batches_root
    from open_guji_cv.clustering.exclusions import default_path
    monkeypatch.setenv("GUJI_WORKSPACE", str(tmp_path))
    assert ProductStore().root == tmp_path / "products"
    assert ImageCache().root == tmp_path / "cache"
    assert default_batches_root() == tmp_path / "review" / "batches"
    assert default_path() == tmp_path / "config" / "crop_exclusions.jsonl"


