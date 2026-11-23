"""databases.toml 连库配置（2026-11-22）：覆盖顺序、inherit、环境变量老用法、令牌只报名字。"""
from __future__ import annotations

import pytest

from guji_manager import dbconfig


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    monkeypatch.setattr(dbconfig, "USER_FILE", tmp_path / "none.toml")
    for v in ("GUJI_DB_CONFIG", "GUJI_DATA_URL", "GUJI_DATA_BRANCH", "GUJI_DATA_SQLITE", "JOBSDB_URL", "JOBSDB_USER",
              "GUJI_DATA_TOKEN", "GUJI_DATA_TOKEN_EXP", "GUJI_DATA_TOKEN_PROD", "GUJI_DATA_TOKEN_READ", "JOBSDB_TOKEN"):
        monkeypatch.delenv(v, raising=False)


def test_defaults():
    c = dbconfig.get("central")
    assert c["driver"] == "d1-worker" and c["url"] == "https://data.open-guji.com" and c["db"] == "main"
    w = dbconfig.get("webinbox")
    assert w["driver"] == "d1-worker" and w["url"] == c["url"]          # inherit central
    assert dbconfig.get("jobs")["driver"] == "pg-tunnel"


def test_user_file_and_env_override(monkeypatch, tmp_path):
    f = tmp_path / "db.toml"
    f.write_text('[jobs]\ndriver = "d1-worker"\nurl = "https://x.example"\ndb = "jobs"  # 注释\n', encoding="utf-8")
    monkeypatch.setenv("GUJI_DB_CONFIG", str(f))
    j = dbconfig.get("jobs")
    assert (j["driver"], j["url"], j["db"]) == ("d1-worker", "https://x.example", "jobs")
    assert j["token"] == ["JOBSDB_TOKEN"]                               # 未改的键沿用包内缺省
    monkeypatch.setenv("GUJI_DATA_URL", "https://other.example/")
    assert dbconfig.url("central") == "https://other.example"
    assert dbconfig.url("webinbox") == "https://other.example"          # inherit 后再套环境变量


def test_sqlite_env_switches_driver(monkeypatch, tmp_path):
    monkeypatch.setenv("GUJI_DATA_SQLITE", str(tmp_path / "c.db"))
    c = dbconfig.get("central")
    assert c["driver"] == "sqlite" and c["path"].endswith("c.db")


def test_tokens_order_and_exp(monkeypatch):
    monkeypatch.setenv("GUJI_DATA_TOKEN", "a")
    monkeypatch.setenv("GUJI_DATA_TOKEN_EXP", "e")
    monkeypatch.setenv("GUJI_DATA_TOKEN_READ", "a")                     # 重复的去掉
    assert dbconfig.tokens("central") == ["a"]
    assert dbconfig.tokens("central", branch="exp/GUJI-1-x") == ["a", "e"]


def test_describe_hides_values(monkeypatch):
    monkeypatch.setenv("GUJI_DATA_TOKEN", "secret-value")
    out = repr(dbconfig.describe())
    assert "secret-value" not in out and "GUJI_DATA_TOKEN（已设）" in out


def test_min_parser_matches_tomllib():
    from importlib import resources
    text = resources.files("guji_manager").joinpath("config/databases.toml").read_text(encoding="utf-8")
    if dbconfig._toml is None:
        pytest.skip("3.10 没有 tomllib")
    assert dbconfig._parse_min(text) == dbconfig._toml.loads(text)


def test_bad_driver(monkeypatch, tmp_path):
    f = tmp_path / "db.toml"
    f.write_text('[central]\ndriver = "mysql"\n', encoding="utf-8")
    monkeypatch.setenv("GUJI_DB_CONFIG", str(f))
    with pytest.raises(SystemExit):
        dbconfig.get("central")
