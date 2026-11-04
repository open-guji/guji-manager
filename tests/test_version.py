"""版本号写在 pyproject.toml 与 guji_manager/__init__.py 两处，必须一致（doc/版本号规矩.md 第一节）。"""
from __future__ import annotations

import re
from pathlib import Path

import guji_manager


def test_pyproject_matches_package_version():
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    assert m and m.group(1) == guji_manager.__version__
