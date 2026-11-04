# -*- coding: utf-8 -*-
"""K 引擎卡手五处（卡 #54）几条零碎修复的回归测试：cli_runs.cmd_product /
cmd_check 的具体行为，跟 `core/step.py`、`eval/rulers.py` 那几条更大的
单测分开放，图的是改一条查一条、不用陪跑整条链。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

import pytest

import open_guji_cv.steps  # noqa: F401  注册 v2 步骤与产物种类


# ── K7：`guji cards groups` 曾经 `KeyError: 未注册的产物种类: seed_admit` ──


# ── K20：`guji product raw` 曾经 NameError（缺 import cv_imread）──────────
def test_cmd_product_raw_no_nameerror(tmp_path, ws, capsys):
    """2026-09-27 起 `cmd_product` action=raw 分支直接崩 `NameError:
    name 'cv_imread' is not defined`（局部 import 只带了 cv2，没带
    `utils.image_io.imread as cv_imread`）。跑一次真页确认不再崩、且真的
    编出了 PNG。"""
    from guji_manager.cli_runs import cmd_product

    out = tmp_path / "raw.png"
    args = argparse.Namespace(action="raw", book="keben", step="", page=1,
                              key="", col=0, slot=0, sub="", scale=0.35, out=str(out))
    cmd_product(args)
    assert out.exists() and out.stat().st_size > 0
    capsys.readouterr()


# ── K9：`guji product patch` 缺缓存时应现场 materialize，不该直接报错退出 ──
def test_cmd_product_patch_materializes_on_cache_miss(tmp_path, monkeypatch, ws, capsys):
    from open_guji_cv.core.book import load_book
    from open_guji_cv.core.pipeline import load_pipeline
    from open_guji_cv.core.engine import Engine
    from open_guji_cv.products.cache import ImageCache
    from open_guji_cv.products.store import ProductStore
    from guji_manager.cli_runs import cmd_product

    monkeypatch.setenv("GUJI_PRODUCTS_DIR", str(tmp_path / "products"))
    monkeypatch.setenv("GUJI_CACHE_DIR", str(tmp_path / "cache"))
    pl = load_pipeline("keben_body_v2")
    book = load_book("keben")
    store, cache = ProductStore(tmp_path / "products"), ImageCache(tmp_path / "cache")
    eng = Engine(book, pl, store=store, cache=cache, log=lambda s: None)
    rep = eng.run(steps=["border_detect", "column_warp", "row_segment", "cell_shrink"],
                  pages=[1])
    assert not rep.to_dict()["failed"], rep.to_dict()["failed"]

    chars = store.read(book.id, "cell_shrink", "p0001", "char_index")
    col, ch = next((c, r) for c in chars.columns for r in c.chars if r.patch_key)
    key = ch.patch_key
    cache_path = cache.path(book.id, "char_patch", key)
    assert cache_path.exists()
    cache_path.unlink()   # 模拟「拿了快照，products/ 有、cache/ 没有」

    out = tmp_path / "patch.png"
    args = argparse.Namespace(action="patch", book="keben", step="", page=1, key="",
                              col=col.col, slot=ch.slot, sub=(ch.sub or ""), scale=0.35,
                              out=str(out))
    cmd_product(args)   # 之前这里会直接 print("没有字块 …") 后 sys.exit(1)
    assert out.exists() and out.stat().st_size > 0
    capsys.readouterr()


def test_cmd_product_patch_still_errors_when_materialize_cant(tmp_path, ws, capsys):
    """真的没有这个格（page/col/slot 瞎编）时，materialize 也补不出来，
    仍然要清楚报错退出，不能吞掉异常裸崩。"""
    from guji_manager.cli_runs import cmd_product

    args = argparse.Namespace(action="patch", book="keben", step="", page=1, key="",
                              col=99, slot=99, sub="", scale=0.35, out=str(tmp_path / "x.png"))
    with pytest.raises(SystemExit):
        cmd_product(args)
    err = capsys.readouterr().out
    assert "没有字块" in err


# ── K6：`Ruler.to_dict()` 加 `full=True`，做全量错例不再需要 monkeypatch ──


# ── K3：两处裸相对路径改按工作区/GUJI_CACHE_DIR 解析 ──────────────────────


# ── K21：`context_decide`(step_id) 与 `context_decision`(kind_id) 不同名，
#     按 kind_id 误当 step_id 查会静默 0 条 ─────────────────────────────


def test_cmd_product_manifest_autocorrects_kind_id_and_warns(tmp_path, monkeypatch, ws, capsys):
    """`guji product manifest <book> context_decision` 曾经悄悄查到空
    manifest（`context_decide` 才是真正的目录名）。现在要自动纠正并在
    stderr 提示，而不是让人以为『这本书还没有 Step6 产物』。"""
    from open_guji_cv.core.book import load_book
    from open_guji_cv.core.pipeline import load_pipeline
    from open_guji_cv.core.engine import Engine
    from open_guji_cv.products.cache import ImageCache
    from open_guji_cv.products.store import ProductStore
    from open_guji_cv.steps.align_ref import AlignRefParams
    from open_guji_cv.steps.context_decide import ContextDecideParams
    from guji_manager.cli_runs import cmd_product
    import argparse

    monkeypatch.setenv("GUJI_PRODUCTS_DIR", str(tmp_path / "products"))
    monkeypatch.setenv("GUJI_CACHE_DIR", str(tmp_path / "cache"))
    pl = load_pipeline("keben_body_v2")
    book = load_book("keben")
    store, cache = ProductStore(tmp_path / "products"), ImageCache(tmp_path / "cache")
    eng = Engine(book, pl, store=store, cache=cache, log=lambda s: None)
    corpus = ws / "corpus" / "reference.txt"
    eng.ctx.params["align_ref"] = AlignRefParams(corpus=str(corpus))
    eng.ctx.params["context_decide"] = ContextDecideParams(
        corpus=str(corpus), general_corpus_dir=str(tmp_path / "no_general_corpus"))
    # 只跑 context_decide 真正硬依赖的那几步（`consumes=("glyph_match",)`）——
    # 不带 rare_candidates/align_ref：一装了 torch，rare_candidates
    # 就会去建「unicode-cjk-a」那张几万字的 CNN embedding 索引，几分钟起步，
    # 这条用例只想测 CLI 的 kind_id/step_id 纠错，不该陪跑那条冷启动。
    rep = eng.run(steps=["border_detect", "column_warp", "row_segment", "cell_shrink",
                        "glyph_match", "context_decide"], pages=[1])
    assert not rep.to_dict()["failed"], rep.to_dict()["failed"]

    args = argparse.Namespace(action="manifest", book="keben", step="context_decision",
                              key="", page=0, col=0, slot=0, sub="", scale=0.35, out="")
    cmd_product(args)
    out, err = capsys.readouterr()
    assert json.loads(out), "自动纠正后应该读到 context_decide 目录下真有的产物"
    assert "context_decide" in err and "kind_id" in err


# ── K2：`round_check.load_verdicts()` 缺省先认工作区，不再直落 DATASET ────


# ── K13：`glyph-db` 认 `-w`，没有工作区时报错退出（不再静默写进 cv 仓 output/） ──


# ── K15：`eval_frame_residue.py --pages all` 的 max_page 硬编码 300 改按书实际页数 ──


# ── K10：`status`／`collate` 缺 -w 时认 GUJI_WORKSPACE（其余命令仍必须显式 -w） ──


# ── K11：quality()／round_check.accuracy() 比对前按书级 codepoints 归一 ──


