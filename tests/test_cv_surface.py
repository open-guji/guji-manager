"""守卫：本包只经 `open_guji_cv.api` 或 `guji_manager._cv`（转 cv 的 `manager_api`）用 cv。

拆分过渡期 manager 能用 cv 内部，但要登记在册：cv 改名时 cv 的测试当场红，而不是这里运行时才炸。
`tools/` 下的一次性脚本不在此列。"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1] / "guji_manager"
ALLOWED = {"open_guji_cv.api"}


def _cv_imports(path: Path) -> list[tuple[int, str]]:
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [(node.lineno, a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.append((node.lineno, node.module))
    return [(n, m) for n, m in out if m == "open_guji_cv" or m.startswith("open_guji_cv.")]


def test_package_uses_cv_only_through_facade():
    bad = [f"{p.relative_to(PKG)}:{n} {m}" for p in PKG.rglob("*.py") if p.name != "_cv.py"
           for n, m in _cv_imports(p) if m not in ALLOWED]
    assert not bad, "本包直接 import 了 cv 内部（改走 `from ._cv import X`，名字先登记进 cv 的 manager_api）：\n  " + "\n  ".join(bad)


def test_fallback_matches_cv_facade():
    try:
        api = importlib.import_module("open_guji_cv.manager_api")
    except ImportError:
        pytest.skip("装的 cv 没有 manager_api（旧版），只靠兜底表")
    from guji_manager import _cv
    assert set(_cv._FALLBACK) == set(api.__all__), "guji_manager._cv._FALLBACK 与 cv manager_api 的名字不一致"
    for name in _cv._FALLBACK:
        assert getattr(_cv, name) is getattr(api, name)
