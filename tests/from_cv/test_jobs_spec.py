# -*- coding: utf-8 -*-
"""任务库的任务定义：规整、校验、指纹（纯函数，不连库、不联网）。"""
from __future__ import annotations

import pytest

from guji_manager.jobs import spec as SP

C1 = "a" * 40
C2 = "b" * 40


def _resolve(ref: str) -> str:
    return {"v0.5.16": C1, "dev": C2}[ref]


def norm(**kw):
    return SP.normalize(kw, resolve=_resolve)


def test_redact_hides_tokens():
    from guji_manager.jobs.runner import redact
    s = redact("GUJI_DATA_TOKEN=abc123 ok postgresql://u:p@h/db Bearer xyz")
    assert "abc123" not in s and "u:p" not in s and "xyz" not in s and "ok" in s




def test_db_rev_in_hash_and_optional():
    """db_rev 进指纹（册配置改了、spec 没变的单不再判重复）；不给就不出这个键，老指纹不变。"""
    a = norm(book="vol10", cv="v0.5.16")
    assert "db_rev" not in a
    b = norm(book="vol10", cv="v0.5.16", db_rev=879402)
    c = norm(book="vol10", cv="v0.5.16", db_rev=879306)
    assert b["db_rev"] == 879402
    assert len({SP.spec_hash(a), SP.spec_hash(b), SP.spec_hash(c)}) == 3
    for bad in (-1, "1", True, 1.5):
        with pytest.raises(SP.SpecError):
            norm(book="vol10", cv="v0.5.16", db_rev=bad)
