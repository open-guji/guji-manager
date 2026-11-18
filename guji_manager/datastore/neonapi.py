"""旧：按分支名查 Neon 端点 id。2026-11-18 中心库迁到 D1 后分支直接按名字连（``connect(endpoint=分支名)``），
这里只留同名函数给老调用处：原样返回分支名。"""
from __future__ import annotations


def branch_endpoint(name: str, project: str | None = None) -> str:
    return name
