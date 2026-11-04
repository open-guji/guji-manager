# -*- coding: utf-8 -*-
"""K 引擎卡手五处（卡 #54）几条零碎修复的回归测试：cli_v2.cmd_product /
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
def test_group_view_module_registers_seed_admit_kind_standalone():
    """`review/group_view.py` 读 `seed_admit` 产物前没 import
    `products.kinds`（那才是真正注册 `ProductKindSpec` 的地方），只要进程里
    还没有别的模块先注册过，`st.read(book, "seed_admit", …)` 就会
    `KeyError: 未注册的产物种类: seed_admit`。这条在**干净子进程**里跑，
    不然 pytest 一个进程导入几十个测试文件，早被别人注册过，测不出回归。"""
    code = (
        "import guji_manager.review.group_view\n"
        "from open_guji_cv.core.step import KINDS\n"
        "assert 'seed_admit' in KINDS, KINDS.keys()\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── K20：`guji product raw` 曾经 NameError（缺 import cv_imread）──────────


# ── K9：`guji product patch` 缺缓存时应现场 materialize，不该直接报错退出 ──


# ── K6：`Ruler.to_dict()` 加 `full=True`，做全量错例不再需要 monkeypatch ──


# ── K3：两处裸相对路径改按工作区/GUJI_CACHE_DIR 解析 ──────────────────────


# ── K21：`context_decide`(step_id) 与 `context_decision`(kind_id) 不同名，
#     按 kind_id 误当 step_id 查会静默 0 条 ─────────────────────────────


# ── K2：`round_check.load_verdicts()` 缺省先认工作区，不再直落 DATASET ────


# ── K13：`glyph-db` 认 `-w`，没有工作区时报错退出（不再静默写进 cv 仓 output/） ──
def test_glyph_db_requires_workspace_or_explicit_sample_db_opt_in():
    from guji_manager.cli_glyph_db import cmd_glyph_db

    args = argparse.Namespace(action="stats", workspace=None, allow_sample_db=False,
                              store=None, no_others=False, apply=False, path=None,
                              edition=None, manifest="config/fonts/manifest.json",
                              vertical=False, charset=None, limit=None, jobs=1,
                              collection=None, script_style=None, title=None)
    with pytest.raises(RuntimeError, match="没设 GUJI_WORKSPACE"):
        cmd_glyph_db(args)


def test_glyph_db_dash_w_overrides_and_is_respected(tmp_path, monkeypatch):
    """`-w` 传了之后要真的落到 `GUJI_WORKSPACE`，`glyph_db_path()` 按它解析
    ——以前这个命令只认环境变量，`-w` 传了也没用。"""
    from guji_manager.cli_glyph_db import cmd_glyph_db
    from open_guji_cv.core.workspace import glyph_db_path

    monkeypatch.delenv("GUJI_WORKSPACE", raising=False)
    ws = tmp_path / "myws"
    ws.mkdir()
    args = argparse.Namespace(action="stats", workspace=str(ws), allow_sample_db=False,
                              store=None, no_others=False, apply=False, path=None,
                              edition=None, manifest="config/fonts/manifest.json",
                              vertical=False, charset=None, limit=None, jobs=1,
                              collection=None, script_style=None, title=None)
    cmd_glyph_db(args)
    assert glyph_db_path() == (ws / "output" / "glyph.db").resolve()


def test_glyph_db_allow_sample_db_opt_in_does_not_error(tmp_path, monkeypatch, capsys):
    from guji_manager.cli_glyph_db import cmd_glyph_db

    monkeypatch.delenv("GUJI_WORKSPACE", raising=False)
    monkeypatch.chdir(tmp_path)   # 别真的碰 cv 仓自己的 output/
    args = argparse.Namespace(action="stats", workspace=None, allow_sample_db=True,
                              store=None, no_others=False, apply=False, path=None,
                              edition=None, manifest="config/fonts/manifest.json",
                              vertical=False, charset=None, limit=None, jobs=1,
                              collection=None, script_style=None, title=None)
    cmd_glyph_db(args)   # 不该抛
    capsys.readouterr()


# ── K15：`eval_frame_residue.py --pages all` 的 max_page 硬编码 300 改按书实际页数 ──


# ── K10：`status`／`collate` 缺 -w 时认 GUJI_WORKSPACE（其余命令仍必须显式 -w） ──


# ── K11：quality()／round_check.accuracy() 比对前按书级 codepoints 归一 ──
def test_quality_treats_book_codepoints_pair_as_match(tmp_path, monkeypatch):
    """內/内 这类本书 `codepoints:` 统一过的对，pred 与整理本金标字面不同，
    但按书级码位算是同一个字——不该被 quality() 记成「与整理本不一致」。"""
    from open_guji_cv.core.book import BookSpec
    from open_guji_cv.core import book as book_mod
    from open_guji_cv.core.spec import page_key
    from guji_manager.eval import quality as quality_mod
    from guji_manager.gold import v2_align as v2_align_mod
    from guji_manager.gold.v2_align import GoldChar, PageGold
    from open_guji_cv.products.kinds.recog import AdmitRec, ColumnAdmit, PageAdmit
    from open_guji_cv.products.store import ProductStore

    book_id = "k11book"
    fake_book = BookSpec(id=book_id, title="t", raw_dir=tmp_path,
                         codepoints={"内": "內"})   # 本书统一到「內」
    monkeypatch.setattr(book_mod, "load_book", lambda *_a, **_k: fake_book)

    cid = f"{book_id}:1:1:1"
    monkeypatch.setattr(v2_align_mod, "align_book", lambda *_a, **_k: [
        PageGold(book=book_id, page=1, anchored=True, n_chars=1,
                chars=[GoldChar(id=cid, page=1, col=1, slot=1, shape="内", ref="內",
                                align_op="equal")])])

    store = ProductStore(tmp_path / "products")
    store.write(book_id, "seed_admit", page_key(1), {
        "seed_admit": PageAdmit(page=1, columns=[ColumnAdmit(col=1, chars=[
            AdmitRec(id=cid, slot=1, admit=True, char="内", channel="match_solo")])])})

    out = quality_mod.quality(book_id, [1], store)
    assert out["accuracy"]["n_gold"] == 1
    assert out["accuracy"]["overall"] == 1.0, out["accuracy"]["errors"]


