"""原图破损档（`v="damaged"`，2026-09-19 用户定）。

审阅台此前只有四档：定字 / 切分缺陷（truncated·contaminated）/ 非字 / 跳过。
bxgb:27:8:6 那种「原刻就残、认不出，但最像塊」无处可落——按 skip 记就永远挂在
待办里（实测全书唯一一条 skip 就是它），按 contaminated 记归因错了（切分没毛病）。
新档：文本层出 `□`，`guess` 记「最像哪个字」只作括注，不进字形库。
"""
from __future__ import annotations

from open_guji_cv.feedback.consumers import _expected_of, crop_exclude, gold_add
from open_guji_cv.feedback.events import Event, EventTarget, make_event
from open_guji_cv.feedback.routes import Destination, RouteTable
from guji_manager.review.verdict_view import review_verdicts

SHARD = "char-segmentation/instances"


def _ev(payload: dict, key: str = "bxgb:27:8:6", seq: int = 1) -> Event:
    return make_event("b", seq, "confirm",
                      EventTarget(step="seed_admit", unit="cell", key=key,
                                  book="bxgb", page=27, col=8, slot=6),
                      payload)


def test_verdict_readback_restores_guess(tmp_path):
    """刷新页面要能把 `guess` 读回来，否则人以为没填过、又填一遍。"""
    from open_guji_cv.feedback import EventLog
    log = EventLog(tmp_path)
    log.append([_ev({"v": "damaged", "guess": "塊"})])
    out = review_verdicts("b", log)["verdicts"]["bxgb:27:8:6"]
    assert out["done"] == "damaged" and out["guess"] == "塊"


