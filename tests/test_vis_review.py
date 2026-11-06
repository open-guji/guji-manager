"""看图裁定导出／写入（review/vis_review）：筛格与答案转事件。"""
import pytest

from guji_manager.review.vis_review import pick


ROWS = [
    {"vol": "001", "cell": "21:9:21", "pending_reason": "lib_unrecognized", "kind": "body", "ref": "全", "top": "今", "detail": "lib_other:全"},
    {"vol": "015", "cell": "151:1:4", "pending_reason": "lib_unrecognized", "kind": "body", "ref": "姑", "top": "姑", "detail": "clear:姑"},
    {"vol": "015", "cell": "1:1:1", "pending_reason": "lib_unrecognized", "kind": "roster", "ref": "甲", "top": "甲", "detail": "clear:甲"},
    {"vol": "002", "cell": "7:9:21", "pending_reason": "hard_pair", "kind": "body", "ref": "日", "top": "曰", "detail": ""},
]


def test_pick_reason_detail_body_only():
    got = pick(ROWS, "lib_unrecognized", "lib_other")
    assert [t["id"] for t in got] == ["vol01:21:9:21"] and got[0]["lib_top"] == "今"
    assert [t["id"] for t in pick(ROWS, "lib_unrecognized", vol_fmt="{n:03d}")] == ["001:21:9:21", "015:151:1:4"]


def test_answers_to_events_admit_only_high_ref():
    pytest.importorskip("open_guji_cv")
    from guji_manager.review.vis_review import answers_to_events
    base = {"left": "甲", "right": "乙", "ref_align": "", "reason": "lib_unrecognized"}
    rows = [{**pick(ROWS, "lib_unrecognized", "lib_other")[0], **base, "char": "全", "conf": "high", "why": "x"},
            {**pick(ROWS, "lib_unrecognized", "clear")[0], **base, "char": "姑", "conf": "mid", "why": "y"},
            {**pick(ROWS, "lib_unrecognized", "lib_other")[0], **base, "char": "今", "conf": "high", "why": "z"}]
    evs = answers_to_events(rows, batch="t", subclass="L04", model="m", ts="2026-11-06T00:00:00Z")
    p = [e.payload for e in evs]
    assert [x["admit_ok"] for x in p] == [True, False, False]          # 中把握、字≠参校字 都不放
    assert {x["prompt_ver"] for x in p} == {"vis-o1"} and {x["group"] for x in p} == {"O"} and p[0]["subclass"] == "L04"
    assert p[0]["ref"] == "" and p[0]["coord_ref"] == "全"
