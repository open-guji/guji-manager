"""`guji job stats`：按领单记录拆出排队、真运行、失联耗时（补三本书统计里 started_at 只记首领的偏差）。"""
from __future__ import annotations

from guji_manager.jobs import stats as T

T0 = "2026-11-17T10:00:00+00:00"


def at(h, m=0):
    return f"2026-11-17T{h:02d}:{m:02d}:00+00:00"


def job(i, why, status="succeeded", **kw):
    return {"id": i, "why": why, "status": status, "created_at": T0, "started_at": kw.pop("s", None),
            "finished_at": kw.pop("f", None), "attempts": kw.pop("n", 1), "error": kw.pop("error", None), "spec": kw.pop("spec", {})}


def test_lost_attempt_not_counted_as_run():
    jobs = [job(1, "SJ r76 整书", s=at(11), f=at(13, 20), n=2), job(2, "SJ r76 整书", s=at(10, 30), f=at(10, 50))]
    att = {1: [{"n": 1, "started_at": at(11), "finished_at": None, "lease_until": at(12), "outcome": "lost"},
               {"n": 2, "started_at": at(13), "finished_at": at(13, 20), "outcome": "succeeded"}],
           2: [{"n": 1, "started_at": at(10, 30), "finished_at": at(10, 50), "outcome": "succeeded"}]}
    (r,) = T.summarize(jobs, att)
    assert r["round"] == "r76" and r["n"] == 2
    assert r["wait_med"] == 45 and r["wait_max"] == 60            # 首次领单 − 交单：60、30
    assert r["run_max"] == 20 and r["run_med"] == 20              # 失联那次的 2 小时不算运行
    assert r["multi_claim"] == 1 and r["lost_attempts"] == 1 and r["lost_min"] == 60
    assert r["span_h"] == 3.3


def test_old_json_falls_back_to_job_times_and_kinds():
    jobs = [job(1, "qtw b1", s=at(11), f=at(12), n=2),
            job(2, "qtw b1", status="failed", error="执行会话失联 3 次（租约过期）"),
            job(3, "qtw b1", status="failed", error="BookCodeError: 书级代码没有 k5"),
            job(4, "qtw b1", status="cancelled"),
            job(5, "no round here")]
    (r,) = T.summarize(jobs, None)
    assert r["round"] == "b1" and r["n"] == 4 and r["run_med"] == 60 and r["lost_attempts"] is None
    assert r["fail"] == {"失联": 1, "配置": 1, "交单后改动（停）": 1}
    assert "| b1 |" in T.render([r])


def test_by_change():
    jobs = [job(1, "", spec={"output": {"change": "r12g24"}}, s=at(11), f=at(11, 14))]
    (r,) = T.summarize(jobs, {1: [{"n": 1, "started_at": at(11), "finished_at": at(11, 14), "outcome": "succeeded"}]}, by="change")
    assert r["round"] == "r12g24" and r["run_med"] == 14


def test_round_prefers_r_number():
    assert T.round_of({"why": "钉 g24 k3 出 r12"}, "why") == "r12"
    assert T.round_of({"why": "全唐文 b1 换库"}, "why") == "b1"
