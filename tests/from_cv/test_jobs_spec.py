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


