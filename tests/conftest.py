"""测试一律不连正式中心库（2026-11-18 迁 D1 后发现：本机有 GUJI_DATA_TOKEN_PROD 时个别测试会真写看板）。"""
import pytest

_LIVE = ("GUJI_DATA_TOKEN", "GUJI_DATA_TOKEN_PROD", "GUJI_DATA_TOKEN_READ", "GUJI_DATA_TOKEN_EXP",
         "GUJI_DATA_URL", "NEON_DATABASE_URL", "GUJI_DATA_PG_DSN")


@pytest.fixture(autouse=True)
def _no_live_central_db(monkeypatch):
    for k in _LIVE:
        monkeypatch.delenv(k, raising=False)
