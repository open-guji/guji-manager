"""整机暂停后醒来的旧会话：领单已被 reap 收回，收尾不许把（已退回排队／在别处重跑的）任务写成 cancelled。"""
from __future__ import annotations

import contextlib
import datetime as dt

from guji_manager.jobs import store as S


class _Cur:
    def __init__(self, rows, cols):
        self.description = [type("C", (), {"name": c})() for c in cols]
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self, attempt_finished):
        self.sql: list[str] = []
        self.attempt_finished = attempt_finished

    @contextlib.contextmanager
    def transaction(self):
        yield

    def execute(self, q, args=()):
        self.sql.append(q)
        if q.startswith("SELECT finished_at, outcome FROM jobs.attempt"):
            fin = dt.datetime(2026, 11, 17, 11, 40) if self.attempt_finished else None
            return _Cur([(fin, "lost" if fin else None)], ["finished_at", "outcome"])
        if q.startswith("SELECT attempts, max_attempts"):
            return _Cur([(1, 3)], ["attempts", "max_attempts"])
        return _Cur([], [])


def test_reaped_attempt_does_not_touch_job():
    c = FakeConn(attempt_finished=True)
    S.finish(c, 4991, 7, "cancelled", error="有人要求停下")
    assert not any(q.startswith("UPDATE jobs.job") or q.startswith("UPDATE jobs.attempt") for q in c.sql)
    assert any("INSERT INTO jobs.event" in q for q in c.sql)


def test_live_attempt_finishes_as_before():
    c = FakeConn(attempt_finished=False)
    S.finish(c, 4991, 7, "succeeded")
    assert any(q.startswith("UPDATE jobs.attempt SET finished_at") for q in c.sql)
    assert any(q.startswith("UPDATE jobs.job SET status") for q in c.sql)


class HBConn(FakeConn):
    def __init__(self, attempt_live, cancel=False):
        super().__init__(False)
        self.live, self.cancel = attempt_live, cancel

    def execute(self, q, args=()):
        self.sql.append(q)
        if q.startswith("UPDATE jobs.attempt SET heartbeat_at"):
            return _Cur([(42,)] if self.live else [], ["job_id"])
        if q.startswith("UPDATE jobs.job SET stage"):
            return _Cur([(self.cancel,)], ["cancel_requested"])
        return _Cur([], [])


def test_heartbeat_tells_lost_from_cancel():
    assert S.heartbeat(HBConn(False), 7) == "lost"
    assert S.heartbeat(HBConn(True, cancel=True), 7) == "cancel"
    assert S.heartbeat(HBConn(True), 7) == ""
