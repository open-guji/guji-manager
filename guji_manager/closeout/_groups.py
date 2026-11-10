"""字组同组判断（取 cv 的字组登记，惰性）。"""
from __future__ import annotations


def same_group(a: str, b: str) -> bool:
    from .._cv import groups_of
    return any(b in g.members for g in groups_of(a))
