"""AI 文意裁定命中核对（11-20 痛点 K1）。"""
import json
from types import SimpleNamespace as NS

from guji_manager import ruling_hits as RH
from guji_manager._cv import RulingStore
from open_guji_cv.feedback.llm_queue import PENDING


def _page(root, cells):
    d = root / "001" / "seed_admit"
    d.mkdir(parents=True, exist_ok=True)
    (d / "p0001.json").write_text(json.dumps({"seed_admit": {"columns": [{"chars": cells}]}}, ensure_ascii=False), encoding="utf-8")


def test_miss_detected_and_rekeyed(tmp_path):
    store = RulingStore(tmp_path / "fb")
    store._batch = "llm-session-x"
    store.put("ry", "v1", "甲乙丙", "丁戊", char="曰", conf="high", why="文意", model="session", cell="001:1:1:3")
    store.put("ry", "v1", "子丑", "寅卯", char="日", conf="high", why="", model="session", cell="001:1:1:4")
    ask = lambda l, r: {"evidence": {"group": {"id": "ry", "solvers": [{"why": PENDING, "ask": {"ver": "v1", "l": l, "r": r}}]}}}
    _page(tmp_path / "p", [{"id": "001:1:1:3", "char": "日", **ask("甲乙□", "丁戊")},    # 窗口变了 → 未命中
                           {"id": "001:1:1:4", "char": "日", **ask("子丑", "寅卯")},      # 命中（没人会再问，但即使挂着也不算）
                           {"id": "001:1:1:5", "char": "日", **ask("辰", "巳")}])          # 没裁定 → 不列
    rows = RH.check(tmp_path / "p", "001", store)
    assert [r["cell"] for r in rows] == ["001:1:1:3"] and rows[0]["原因"] == "窗口变了" and rows[0]["裁定字"] == "曰"
    store2 = RulingStore(tmp_path / "fb")
    store2._batch = "llm-rekey"
    assert RH.rekey(rows, store2) == 1
    assert RH.check(tmp_path / "p", "001", RulingStore(tmp_path / "fb")) == []


def test_prompt_version_change_not_rekeyed(tmp_path):
    store = RulingStore(tmp_path / "fb")
    store.put("ry", "v1", "甲", "乙", char="曰", conf="high", why="", model="m", cell="001:1:1:1")
    _page(tmp_path / "p", [{"id": "001:1:1:1", "char": "日",
                            "evidence": {"group": {"id": "ry", "solvers": [{"why": PENDING, "ask": {"ver": "v2", "l": "甲", "r": "乙"}}]}}}])
    rows = RH.check(tmp_path / "p", "001", store)
    assert len(rows) == 1 and "提示词版本" in rows[0]["原因"]
    assert RH.rekey(rows, store) == 0


def test_command_registered():
    from guji_manager.commands import COMMANDS
    assert "rulings-hits" in COMMANDS
