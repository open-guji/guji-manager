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


# ── K20：`guji product raw` 曾经 NameError（缺 import cv_imread）──────────


# ── K9：`guji product patch` 缺缓存时应现场 materialize，不该直接报错退出 ──


# ── K6：`Ruler.to_dict()` 加 `full=True`，做全量错例不再需要 monkeypatch ──


# ── K3：两处裸相对路径改按工作区/GUJI_CACHE_DIR 解析 ──────────────────────


# ── K21：`context_decide`(step_id) 与 `context_decision`(kind_id) 不同名，
#     按 kind_id 误当 step_id 查会静默 0 条 ─────────────────────────────


# ── K2：`round_check.load_verdicts()` 缺省先认工作区，不再直落 DATASET ────
def test_load_verdicts_prefers_workspace_events(tmp_path, monkeypatch, capsys):
    from guji_manager.eval import round_check as rc

    ws_events = tmp_path / "ws" / "feedback" / "events"
    ws_events.mkdir(parents=True)
    dataset_events = tmp_path / "dataset" / "feedback" / "events"
    dataset_events.mkdir(parents=True)
    monkeypatch.setattr(rc, "DATASET", tmp_path / "dataset")

    import json as _json
    ev = {"actor": "user", "kind": "confirm", "target": {"key": "vol01:1:1:1"},
         "payload": {"v": "confirm", "shape": "從工作区"}, "ts": "2026-09-27T00:00:00"}
    (ws_events / "vol01-dev_set-decide.jsonl").write_text(_json.dumps(ev, ensure_ascii=False) + "\n",
                                                          encoding="utf-8")
    # DATASET 里放一份不同的裁决——用来证明真读到的是工作区那份，不是 DATASET
    ev_dataset = dict(ev, payload={"v": "confirm", "shape": "從dataset"})
    (dataset_events / "vol01-dev_set-decide.jsonl").write_text(
        _json.dumps(ev_dataset, ensure_ascii=False) + "\n", encoding="utf-8")

    monkeypatch.setenv("GUJI_WORKSPACE", str(tmp_path / "ws"))
    out = rc.load_verdicts("vol01")
    assert out == {"vol01:1:1:1": "從工作区"}
    capsys.readouterr()


def test_load_verdicts_reads_cross_book_batch_files(tmp_path, monkeypatch, capsys):
    """全唐文人裁在跨册批次文件 `qtw-human-batch*.jsonl` 里（C #166 查出）：
    文件名不以书 id 开头也要读到，按 target.key 的书前缀过滤，别册的不混进来。"""
    from guji_manager.eval import round_check as rc
    import json as _json

    ws_events = tmp_path / "ws" / "feedback" / "events"
    ws_events.mkdir(parents=True)
    monkeypatch.setattr(rc, "DATASET", tmp_path / "dataset")
    rows = [
        {"actor": "user", "kind": "confirm", "target": {"key": "v007:3:1:2"},
         "payload": {"v": "confirm", "shape": "聞"}, "ts": "2026-09-27T01:00:00"},
        {"actor": "user", "kind": "confirm", "target": {"key": "v2:v007:3:1:3"},
         "payload": {"v": "confirm", "shape": "爲"}, "ts": "2026-09-27T01:00:01"},
        {"actor": "user", "kind": "confirm", "target": {"key": "v0070:3:1:2"},
         "payload": {"v": "confirm", "shape": "別册"}, "ts": "2026-09-27T01:00:02"},
        {"actor": "user", "kind": "confirm", "target": {"key": "v008:3:1:2"},
         "payload": {"v": "confirm", "shape": "他册"}, "ts": "2026-09-27T01:00:03"},
    ]
    (ws_events / "qtw-human-batch1.jsonl").write_text(
        "".join(_json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.setenv("GUJI_WORKSPACE", str(tmp_path / "ws"))
    assert rc.load_verdicts("v007") == {"v007:3:1:2": "聞", "v2:v007:3:1:3": "爲"}
    capsys.readouterr()


def test_load_verdicts_falls_back_to_dataset_and_warns_when_both_empty(tmp_path, monkeypatch, capsys):
    from guji_manager.eval import round_check as rc

    monkeypatch.setattr(rc, "DATASET", tmp_path / "dataset")   # 不存在，天然空
    monkeypatch.setenv("GUJI_WORKSPACE", str(tmp_path / "empty_ws"))  # 也不存在
    out = rc.load_verdicts("vol99")
    assert out == {}
    err = capsys.readouterr().err
    assert "vol99" in err and "0 条" in err   # 不许悄悄回空字典不说话


def test_load_verdicts_explicit_root_still_works(tmp_path, monkeypatch):
    """显式传 `root`（老调用点如 `research/metric_loss/*.py` 传的是工作区根，
    不是 events 目录本身）行为不变：函数自己拼 `feedback/events`。"""
    from guji_manager.eval import round_check as rc
    import json as _json

    root = tmp_path / "explicit_ws"       # 一个「工作区根」，不是 events 目录
    (root / "feedback" / "events").mkdir(parents=True)
    ev = {"actor": "user", "kind": "confirm", "target": {"key": "vol01:1:1:1"},
         "payload": {"v": "confirm", "shape": "甲"}, "ts": "t"}
    (root / "feedback" / "events" / "vol01-x-decide.jsonl").write_text(
        _json.dumps(ev, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setenv("GUJI_WORKSPACE", str(tmp_path / "should_be_ignored"))
    assert rc.load_verdicts("vol01", root=root) == {"vol01:1:1:1": "甲"}


# ── K13：`glyph-db` 认 `-w`，没有工作区时报错退出（不再静默写进 cv 仓 output/） ──


# ── K15：`eval_frame_residue.py --pages all` 的 max_page 硬编码 300 改按书实际页数 ──


# ── K10：`status`／`collate` 缺 -w 时认 GUJI_WORKSPACE（其余命令仍必须显式 -w） ──


# ── K11：quality()／round_check.accuracy() 比对前按书级 codepoints 归一 ──


def test_round_check_accuracy_treats_book_codepoints_pair_as_match(tmp_path, monkeypatch):
    from open_guji_cv.core.book import BookSpec
    from open_guji_cv.core.spec import page_key
    from open_guji_cv.core import book as book_mod
    from guji_manager.eval import round_check as rc
    from guji_manager.gold import v2_align as v2_align_mod
    from guji_manager.gold.v2_align import GoldChar, PageGold
    from open_guji_cv.products.kinds.recog import AdmitRec, ColumnAdmit, PageAdmit
    from open_guji_cv.products.store import ProductStore

    book_id = "k11book2"
    fake_book = BookSpec(id=book_id, title="t", raw_dir=tmp_path,
                         codepoints={"内": "內"})
    monkeypatch.setattr(book_mod, "load_book", lambda *_a, **_k: fake_book)

    cid = f"{book_id}:1:1:1"
    monkeypatch.setattr(v2_align_mod, "align_book", lambda *_a, **_k: [
        PageGold(book=book_id, page=1, anchored=True, n_chars=1,
                chars=[GoldChar(id=cid, page=1, col=1, slot=1, shape="内", ref="內",
                                align_op="equal")])])
    monkeypatch.setattr(rc, "load_verdicts", lambda *_a, **_k: {})

    store = ProductStore(tmp_path / "products")
    store.write(book_id, "seed_admit", page_key(1), {
        "seed_admit": PageAdmit(page=1, columns=[ColumnAdmit(col=1, chars=[
            AdmitRec(id=cid, slot=1, admit=True, char="内", channel="match_solo")])])})

    out = rc.accuracy(book_id, [1], store)
    assert out["gold"] == [1, 1], out["errors"]


