"""jobsdb.connect：角色连接数满时退避重试，别的连接错误仍短重试后抛出。"""
import sys
import types

import pytest

from guji_manager.jobs import jobsdb

# CI 没装 psycopg：换一个只带 OperationalError 和 connect 的假模块，connect 里的 `import psycopg` 取到它
psycopg = types.ModuleType("psycopg")


class _OpErr(Exception):
    pass


psycopg.OperationalError = _OpErr
psycopg.connect = None


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", psycopg)
    monkeypatch.setenv("JOBSDB_TOKEN", "t")
    monkeypatch.setenv("JOBSDB_PASSWORD", "p")
    monkeypatch.setattr(jobsdb, "_tunnel_port", lambda tok: 1)
    monkeypatch.setattr("time.sleep", lambda s: None)


def test_retries_when_role_is_full(monkeypatch):
    calls = []

    def fake(**kw):
        calls.append(1)
        if len(calls) < 4:
            raise psycopg.OperationalError('FATAL:  too many connections for role "jobs_rw"')
        return "conn"
    monkeypatch.setattr(psycopg, "connect", fake)
    assert jobsdb.connect() == "conn"
    assert len(calls) == 4


def test_gives_up_after_full_retries(monkeypatch):
    monkeypatch.setattr(jobsdb, "FULL_RETRIES", 3)
    calls = []

    def fake(**kw):
        calls.append(1)
        raise psycopg.OperationalError("too many connections for role")
    monkeypatch.setattr(psycopg, "connect", fake)
    with pytest.raises(psycopg.OperationalError):
        jobsdb.connect()
    assert len(calls) == 4


def test_other_errors_use_short_retry(monkeypatch):
    calls = []

    def fake(**kw):
        calls.append(1)
        raise psycopg.OperationalError("connection refused")
    monkeypatch.setattr(psycopg, "connect", fake)
    with pytest.raises(psycopg.OperationalError):
        jobsdb.connect()
    assert len(calls) == 10
