"""步骤开跑前查租约：租约已被收回（整机暂停后醒来）就不再开跑，更不能存包。"""
import io
import threading

import pytest

from guji_manager.jobs import runner as R


def _job(why):
    j = object.__new__(R.Job)
    j.stage = "x"
    j.aid = 1
    j.id = 5
    j.log = io.StringIO()
    j.cancel = threading.Event()
    j.lease_lost = False
    j.db = lambda fn, *a, **kw: why
    return j


def test_step_stops_when_lease_lost():
    ran = []
    j = _job("lost")
    with pytest.raises(R.Cancelled):
        j.step("push", lambda: ran.append(1))
    assert not ran and j.lease_lost and j.cancel.is_set()


def test_step_stops_on_cancel_request():
    j = _job("cancel")
    with pytest.raises(R.Cancelled):
        j.step("run", lambda: None)
    assert not j.lease_lost


def test_step_runs_when_lease_ok():
    ran = []
    j = _job("")
    j.step("run", lambda: ran.append(1))
    assert ran == [1] and not j.cancel.is_set()
