"""连中心库。2026-11-18 起中心库是 Cloudflare D1，只能经 guji-data Worker（``GUJI_DATA_URL``、``GUJI_DATA_TOKEN``）；
返回的连接模仿 psycopg（见 ``d1conn``）。``GUJI_DATA_SQLITE=<文件>`` 改连本机 SQLite（测试、核对）。

旧的 ``endpoint=``（Neon 端点 id）现在就是分支名：``connect(endpoint="exp/GUJI-9-x")`` 连那个实验分支。
"""
from __future__ import annotations


def main_endpoint() -> str | None:
    """正式库在 D1 上就叫 main（旧代码拿它和 ``--endpoint`` 比，防止恢复演练打到正式库）。"""
    return "main"


def connect(endpoint: str | None = None, *, branch: str | None = None):
    from .d1conn import connect as d1_connect
    return d1_connect(branch or endpoint or "main")
