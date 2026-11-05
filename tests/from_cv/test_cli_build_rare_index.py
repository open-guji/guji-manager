# -*- coding: utf-8 -*-
"""`guji cache build-rare-index`（`cli_runs._cmd_cache_build_rare_index`）：自 cv #1053 搬来，
测试原在 cv `tests/test_rare_coldstart_mem.py`，命令搬走后那条在装了 torch 的机器上一直红。

打桩 `book_charsets` 回几个字的小表，只验证 CLI 把它接到 `emb_index_key`／`_emb_index` 的路径没接错、
文件写到预期位置、第二次调用（缓存已在）不重建。checkpoint 拷到 tmp，不碰真实 `models/glyph_cnn_r5/`。
"""
from __future__ import annotations

import shutil
from argparse import Namespace

import pytest

cc = pytest.importorskip("open_guji_cv.clustering.cnn_candidates")


@pytest.fixture
def ckpt_copy(tmp_path):
    src = cc.DEFAULT_CKPT
    if not src.exists() or not cc.CnnCandidates(ckpt=src).available:
        pytest.skip(f"没有 checkpoint（{src}）或没装 torch")
    p = tmp_path / "best.pt"
    shutil.copy(src, p)
    return p


def test_cli_build_rare_index_uses_book_charsets_and_dedupes(monkeypatch, ckpt_copy):
    from guji_manager import _cv, cli_runs

    monkeypatch.setattr(cc, "DEFAULT_CKPT", ckpt_copy)
    cs_base, cs_esc = tuple("一二三十土王"), tuple("人之")
    # _cv 走模块 __getattr__ 取 cv 的函数；模块字典里有同名属性时先用它
    monkeypatch.setattr(_cv, "book_charsets",
                        lambda book, corpus: (cs_base, cs_esc, {"base": "fake-base", "escalate": "fake-esc"}),
                        raising=False)
    monkeypatch.setattr(_cv, "book_corpus", lambda book: None, raising=False)

    args = Namespace(book="keben")
    cli_runs._cmd_cache_build_rare_index(args)

    inst = cc.CnnCandidates(ckpt=ckpt_copy)
    _, f_base, _ = inst.emb_index_key(cs_base)
    _, f_esc, _ = inst.emb_index_key(cs_esc)
    assert f_base.exists(), "CLI 应该已经把基集索引建出来了"
    assert f_esc.exists(), "CLI 应该已经把升级档索引也建出来了"

    mtime = f_base.stat().st_mtime_ns
    cli_runs._cmd_cache_build_rare_index(args)
    assert f_base.stat().st_mtime_ns == mtime
