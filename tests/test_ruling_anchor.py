"""裁定格锚点回填：只回填能证明现产物就是当时问的那份的（11-24）。"""
import json

from guji_manager import ruling_anchor as RA
from guji_manager._cv import RulingStore
from open_guji_cv.feedback.llm_queue import PENDING


def _page(root, cells):
    d = root / "001" / "seed_admit"
    d.mkdir(parents=True, exist_ok=True)
    (d / "p0001.json").write_text(json.dumps({"seed_admit": {"columns": [{"chars": cells}]}}, ensure_ascii=False), encoding="utf-8")


def test_backfill_only_provable(tmp_path, monkeypatch):
    monkeypatch.setattr(RA, "page_sha", lambda products, book, page: "SHA1+P1")
    store = RulingStore(tmp_path / "fb")
    store._batch = "llm-a"
    store.put("ry", "ry-l2-2", "甲乙", "丙丁", char="曰", conf="high", why="", model="m", cell="001:1:1:1")   # 窗口一致 → 回填
    store.put("ry", "ry-l2-2", "子丑", "寅卯", char="日", conf="high", why="", model="m", cell="001:1:1:2")   # 产物窗口变了 → 不回填
    ask = lambda l, r: {"evidence": {"group": {"id": "ry", "solvers": [{"why": PENDING, "ask": {"ver": "ry-l2-2", "l": l, "r": r}}]}}}
    _page(tmp_path / "p", [{"id": "001:1:1:1", "char": "日", **ask("甲乙", "丙丁")},
                           {"id": "001:1:1:2", "char": "日", **ask("子丑x", "寅卯")}])
    rows = {r["cell"]: r for r in RA.backfill(tmp_path / "p", "001", store, "llm-anchor", write=False)}
    assert rows["001:1:1:1"]["结果"] == "可回填" and rows["001:1:1:2"]["结果"] == "不回填"
    assert not store.log.events_dir.exists() or not any("anchor" in e.batch for e in store.log.iter_all(raw=True))
    RA.backfill(tmp_path / "p", "001", store, "llm-anchor", write=True)
    s2 = RulingStore(tmp_path / "fb")
    got = s2.get("ry", "ry-l2-2", "甲乙", "丙丁")
    assert got["cells_sha"] == "SHA1+P1" and got["char"] == "曰" and got["conf"] == "high"
    assert "cells_sha" not in s2.get("ry", "ry-l2-2", "子丑", "寅卯")
    # 再跑一遍：已有 cells_sha 的不重复回填
    assert [r for r in RA.backfill(tmp_path / "p", "001", s2, "llm-anchor2", write=False) if r["cell"] == "001:1:1:1"] == []


def test_backfill_no_cells_sha(tmp_path, monkeypatch):
    monkeypatch.setattr(RA, "page_sha", lambda *a: None)
    store = RulingStore(tmp_path / "fb")
    store.put("ry", "ry-l2-2", "甲", "乙", char="曰", conf="high", why="", model="m", cell="001:1:1:1")
    _page(tmp_path / "p", [{"id": "001:1:1:1", "char": "日"}])
    rows = RA.backfill(tmp_path / "p", "001", store, "b")
    assert rows[0]["结果"] == "不回填" and "切分戳" in rows[0]["原因"]


def test_backfill_screens_cross_group_versions(tmp_path, monkeypatch):
    """串组版本（cv 写前校验过不了）标「不回填」，不拖垮同批别的格。"""
    monkeypatch.setattr(RA, "page_sha", lambda products, book, page: "SHA1+P1")
    store = RulingStore(tmp_path / "fb")
    store._batch = "llm-a"
    store.put("ry", "ry-l2-2", "甲乙", "丙丁", char="曰", conf="high", why="", model="m", cell="001:1:1:1")
    store.put("ry", "rm-l2-1", "子丑", "寅卯", char="日", conf="high", why="", model="m", cell="001:1:1:2")   # ry 写 rm 版本
    ask = lambda v, l, r: {"evidence": {"group": {"id": "ry", "solvers": [{"why": PENDING, "ask": {"ver": v, "l": l, "r": r}}]}}}
    _page(tmp_path / "p", [{"id": "001:1:1:1", "char": "日", **ask("ry-l2-2", "甲乙", "丙丁")},
                           {"id": "001:1:1:2", "char": "日", **ask("rm-l2-1", "子丑", "寅卯")}])
    rows = {r["cell"]: r for r in RA.backfill(tmp_path / "p", "001", store, "llm-anchor", write=True)}
    assert rows["001:1:1:1"]["结果"] == "回填"
    assert rows["001:1:1:2"]["结果"] == "不回填" and "校验不过" in rows["001:1:1:2"]["原因"]
    s2 = RulingStore(tmp_path / "fb")
    assert s2.get("ry", "ry-l2-2", "甲乙", "丙丁")["cells_sha"] == "SHA1+P1"
