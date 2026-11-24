"""`guji human-conflicts`：跨批次人裁冲突（SJ 11-21）。绑定与生效字用注入的假函数，口径由 cv human_chars 自己的测试管。"""
from types import SimpleNamespace as NS

from guji_manager import human_conflicts as HC


def _e(i, key, ch, batch, ts):
    return NS(id=f"e{i}", kind="confirm", target=NS(unit="cell", key=key), payload={"v": "confirm", "shape": ch}, batch=batch, ts=ts, seq=i)


def test_find_conflicts():
    evs = [_e(1, "01:3:1:2", "日", "r1", "2026-11-19T01:00:00Z"), _e(2, "01:3:1:2", "曰", "r3", "2026-11-20T01:00:00Z"),
           _e(3, "01:3:1:5", "甲", "r1", "2026-11-19T01:00:00Z"), _e(4, "01:3:1:5", "甲", "r2", "2026-11-19T02:00:00Z"),   # 同字不报
           _e(5, "01:4:1:1", "子", "r2", "2026-11-19T03:00:00Z"), _e(6, "01:4:1:2", "丑", "uncanon", "2026-11-21T00:00:00Z"),
           _e(7, "01:9:1:1", "卯", "r4", "2026-11-21T00:00:00Z")]
    bound = {"e6": {"status": "shifted", "bound": "01:4:1:1"}, "e7": {"status": "split"}}   # 6 顺移到 4:1:1；7 绑不上
    usable = lambda row, ts=None: row.get("bound") if row and row.get("status") != "split" else None  # noqa: E731
    eff = {"01:3:1:2": "曰", "01:3:1:5": "甲", "01:4:1:1": "丑"}
    rows, lost = HC.find_conflicts(evs, bound, eff, usable)
    assert [r["cell"] for r in rows] == ["01:3:1:2", "01:4:1:1"]
    assert rows[0]["生效字"] == "曰" and rows[0]["生效批次"] == "r3" and not rows[0]["注意"]
    assert "原 4:1:2" in rows[1]["历次"] and rows[1]["生效批次"] == "uncanon"
    assert lost and lost[0]["cell"] == "01:9:1:1"
    rows, _ = HC.find_conflicts(evs, bound, {**eff, "01:3:1:2": "日"}, usable, {"r3"})
    assert [r["cell"] for r in rows] == ["01:3:1:2"] and "不是最后一条" in rows[0]["注意"]


def test_command_registered():
    from guji_manager.commands import COMMANDS
    assert "human-conflicts" in COMMANDS
