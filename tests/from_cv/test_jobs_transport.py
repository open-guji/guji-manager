"""任务库连接选路：只走美国机隧道；没有 JOBSDB_TOKEN 一律报错（Neon 11-19 已删，没有退路）。"""
import pytest

from guji_manager.jobs import jobsdb, store


def test_disabled_without_token(monkeypatch):
    monkeypatch.delenv("JOBSDB_TOKEN", raising=False)
    assert jobsdb.enabled() is False


def test_enabled_with_token(monkeypatch):
    monkeypatch.setenv("JOBSDB_TOKEN", "  tok  ")
    assert jobsdb.enabled() is True


def test_no_neon_fallback_even_when_asked(monkeypatch):
    monkeypatch.delenv("JOBSDB_TOKEN", raising=False)
    monkeypatch.delenv("GUJI_JOBS_BRANCH", raising=False)
    monkeypatch.setenv("GUJI_REQUIRE_JOBSDB", "0")
    monkeypatch.setattr(store, "connect_central", lambda: pytest.fail("不该走中心库"))
    with pytest.raises(SystemExit):
        store.connect()


def test_connect_uses_jobsdb_when_token(monkeypatch):
    monkeypatch.setenv("JOBSDB_TOKEN", "tok")
    class C:
        autocommit = False
    monkeypatch.setattr(jobsdb, "connect", lambda: C())
    monkeypatch.setattr(store, "connect_central", lambda: pytest.fail("不该走中心库"))
    c = store.connect()
    assert c.autocommit is True


def test_pin_only_for_bare_ip(monkeypatch):
    monkeypatch.delenv("JOBSDB_CERT_SHA256", raising=False)
    monkeypatch.delenv("JOBSDB_URL", raising=False)
    assert jobsdb._pin() is None                     # 域名：系统 CA
    monkeypatch.setenv("JOBSDB_URL", "wss://170.106.66.156/jobsdb")
    p = jobsdb._pin()
    assert len(p) == 64 and all(ch in "0123456789abcdef" for ch in p)
    monkeypatch.setenv("JOBSDB_CERT_SHA256", "none")
    assert jobsdb._pin() is None


def test_require_jobsdb_fails_loudly_without_token(monkeypatch):
    monkeypatch.delenv("JOBSDB_TOKEN", raising=False)
    monkeypatch.setenv("GUJI_REQUIRE_JOBSDB", "1")
    monkeypatch.setattr(store, "connect_central", lambda: pytest.fail("不该退回中心库"))
    with pytest.raises(SystemExit):
        store.connect()


def test_default_refuses_neon_without_token(monkeypatch):
    monkeypatch.delenv("JOBSDB_TOKEN", raising=False)
    monkeypatch.delenv("GUJI_JOBS_BRANCH", raising=False)
    monkeypatch.delenv("GUJI_REQUIRE_JOBSDB", raising=False)
    monkeypatch.setattr(store, "connect_central", lambda: pytest.fail("不该退回中心库"))
    with pytest.raises(SystemExit):
        store.connect()


def test_ci_branch_has_no_neon_fallback(monkeypatch):
    monkeypatch.delenv("JOBSDB_TOKEN", raising=False)
    monkeypatch.delenv("GUJI_REQUIRE_JOBSDB", raising=False)
    monkeypatch.setenv("GUJI_JOBS_BRANCH", "ci")
    monkeypatch.setattr(store, "connect_central", lambda: pytest.fail("不该走中心库"))
    with pytest.raises(SystemExit):
        store.connect()
