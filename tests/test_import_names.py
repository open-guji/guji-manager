"""导入级冒烟：本包里每一条 `from .xxx import 名字`（模块级与函数里的都算）都要取得到。

11-23 #818 用 ruff 删「未用 import」时删掉了 `ops/pack_purity.py` 的再导出 `describe`，
`cli_products` 在函数里 `from .ops.pack_purity import describe`，标 main（`products pack promote`）当场 ImportError；
全套测试没有走到那条路径。这里静态列出所有相对导入，逐条核对目标模块真有这个名字，不靠测试碰巧走到。
`_cv` 是惰性门面（`__getattr__`），核对登记表；`_cv` 指向 cv 的名字由 `test_cv_surface.py` 管。
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1] / "guji_manager"


def _relative_imports():
    for f in sorted(PKG.rglob("*.py")):
        mod = "guji_manager." + ".".join(f.relative_to(PKG).with_suffix("").parts)
        is_pkg = f.name == "__init__.py"
        if is_pkg:
            mod = mod[: -len(".__init__")]
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level > 0:
                base = mod.split(".") if is_pkg else mod.split(".")[:-1]
                base = base[: len(base) - (node.level - 1)]
                target = ".".join(base + ([node.module] if node.module else []))
                for a in node.names:
                    if a.name != "*":
                        yield f"{f.relative_to(PKG.parent)}:{node.lineno}", target, a.name


CASES = list(_relative_imports())


def test_found_some():
    assert len(CASES) > 500


def test_relative_import_names_resolve():
    from guji_manager import _cv
    registered = set(_cv._FALLBACK) | set(_cv._LOCAL) | set(vars(_cv))
    bad = []
    for where, target, name in CASES:
        if target == "guji_manager._cv":
            if name not in registered:
                bad.append(f"{where}: _cv 没有登记 {name}")
            continue
        try:
            m = importlib.import_module(target)
        except ModuleNotFoundError as e:
            if e.name and e.name.startswith("guji_manager"):
                # 可能是子模块名：from .pkg import submodule
                try:
                    importlib.import_module(f"{target}.{name}")
                    continue
                except ModuleNotFoundError:
                    pass
                bad.append(f"{where}: 没有模块 {target}")
            continue       # 缺第三方依赖（torch 等）的不在这里管
        except ImportError:
            continue
        if hasattr(m, name):
            continue
        try:
            importlib.import_module(f"{target}.{name}")
        except ModuleNotFoundError:
            bad.append(f"{where}: {target} 没有 {name}")
    assert not bad, "\n".join(bad)


def test_promote_purity_paths_run(monkeypatch, capsys, tmp_path):
    """标 main（_warn_impure）与存包（_purity）两条路径真跑一遍：#818 后这两处都因 pack_purity.describe 缺失而挂。"""
    import json
    from guji_manager import cli_products
    from guji_manager import _cv
    from guji_manager.ops import pack_purity as PP

    class PK:
        _client = staticmethod(lambda: None)
        _ws_name = staticmethod(lambda: "ws")
        _prefix = staticmethod(lambda ws, book: f"{ws}/{book}")
        _call = staticmethod(lambda c, m, u, raw=False: json.dumps({"purity": {"pure": False, "code_mixed": {"x": 1}}}))
    monkeypatch.setattr(_cv, "packs", PK, raising=False)
    cli_products._warn_impure("b", "lab")
    assert "这份 main 包" in capsys.readouterr().err

    monkeypatch.setattr(_cv, "default_products_root", lambda: tmp_path, raising=False)
    monkeypatch.setattr(PP, "check", lambda book, root: {"pure": True})
    assert cli_products._purity("b", tmp_path) == {"pure": True}
    assert "纯净性" in capsys.readouterr().out
