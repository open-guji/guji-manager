#!/usr/bin/env python3
"""把 open-guji-cv 里一个 manager 一侧的包（和它的 cli_*.py、测试）复制进本仓，并按"已搬走集合"改 import。

    python tools/move_from_cv.py --cv ../open-guji-cv --pkg exp --cli cli_exp [--tests tests/test_exp_framework.py ...]

规则：包内相对 import 不变；指向"本仓已有的包"（guji_manager 下已有目录／模块）的改成相对本仓的写法，
指向 cv 里其余模块的改成绝对 `open_guji_cv.…`。复制完打印需要人看的地方（`__file__`／`parents[`／`REPO_ROOT`：
路径可能指向 cv 仓里的数据文件）。**只复制，不删 cv 里的**（cv 自带的优先，删除是 cv 另一个 PR）。
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
PKG = HERE / "guji_manager"


def moved_names() -> set[str]:
    return {p.name.removesuffix(".py") for p in PKG.iterdir() if (p.is_dir() or p.suffix == ".py") and not p.name.startswith("__")}


def _fix_line(m: re.Match, depth: int, moved: set[str]) -> str:
    dots, rest = m.group(1), (m.group(2) or "")
    up = len(dots) - 1
    if up < depth:
        return m.group(0)
    top = rest.split(".")[0] if rest else ""
    if top in moved:
        return f"from {'.' * (depth + 1)}{rest} import"
    return f"from open_guji_cv.{rest} import" if rest else "from open_guji_cv import"


def convert(src: Path, dst: Path, depth: int, moved: set[str]) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    t = src.read_text(encoding="utf-8")
    t = re.sub(r"from (\.+)([A-Za-z_][\w.]*)? import", lambda m: _fix_line(m, depth, moved), t)
    dst.write_text(t, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cv", required=True)
    ap.add_argument("--pkg", action="append", default=[], help="open_guji_cv 下的包名，可重复")
    ap.add_argument("--cli", action="append", default=[], help="open_guji_cv 下的顶层模块名（如 cli_exp），可重复")
    ap.add_argument("--tests", nargs="*", default=[], help="cv 仓里的测试文件／目录（相对 cv 仓根）")
    a = ap.parse_args()
    cv = Path(a.cv)
    moved = moved_names() | set(a.pkg) | set(a.cli)
    flagged = []
    for pkg in a.pkg:
        for f in (cv / "open_guji_cv" / pkg).rglob("*.py"):
            rel = f.relative_to(cv / "open_guji_cv")
            convert(f, PKG / rel, len(rel.parts) - 1, moved)
            flagged.append(PKG / rel)
        for f in (cv / "open_guji_cv" / pkg).rglob("*"):
            if f.is_file() and f.suffix not in (".py", ".pyc"):
                d = PKG / f.relative_to(cv / "open_guji_cv")
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, d)
                print("数据文件（要加进 package-data）：", d.relative_to(HERE))
    for m in a.cli:
        convert(cv / "open_guji_cv" / f"{m}.py", PKG / f"{m}.py", 0, moved)
        flagged.append(PKG / f"{m}.py")
    for t in a.tests:
        src = cv / t
        files = list(src.rglob("*.py")) if src.is_dir() else [src]
        for f in files:
            dst = HERE / "tests" / f.relative_to(cv / "tests")
            dst.parent.mkdir(parents=True, exist_ok=True)
            txt = f.read_text(encoding="utf-8")
            for name in sorted(moved, key=len, reverse=True):
                txt = re.sub(rf"\bopen_guji_cv\.{name}\b", f"guji_manager.{name}", txt)
                txt = re.sub(rf"from open_guji_cv import {name}\b", f"from guji_manager import {name}", txt)
            dst.write_text(txt, encoding="utf-8")
    pat = re.compile(r"__file__|parents\[|REPO_ROOT")
    for f in flagged:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if pat.search(line):
                print(f"看一下 {f.relative_to(HERE)}:{i}: {line.strip()[:110]}")


if __name__ == "__main__":
    main()
