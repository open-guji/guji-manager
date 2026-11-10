# -*- coding: utf-8 -*-
"""``guji code``：书级代码（书仓 `code/`，cv `core/book_code.py`，2026-11-09）。

    guji code status  -w <书仓>            # 有没有 code/、name/base/覆盖表、已有版本、工作副本与最新版差在哪
    guji code release -w <书仓> [--note …] [--samples <链接>]   # 写 code/releases/k<N+1>.json（内容没变不出）
    guji code verify  -w <书仓> [--version N]   # 工作副本 vs k<N>（缺省最新），退出码 1 = 有改动
    guji code check   -w <书仓>            # 护栏：书级模块只许 import open_guji_cv.seg / open_guji_cv.book_api / 本书模块

`release` 只写清单文件，不提交、不打 tag：出完在书仓里 `git add code/ && git commit && git push origin main`，
再打 tag `k<N>`。本地有权限就 `git tag k<N> && git push origin k<N>`；云端会话推不了 tag，走中转站（只认书仓 main 上的提交）：
`python3 process/tag.py guji-workspace/<书仓> <40 位提交号> k<N> "说明"`（ai-team 仓，2026-11-09 白名单加了 guji-workspace）。
再把书配置（book_defaults.yaml）改成 `code: N` 推中心库。版本号不进指纹，升号本身不让任何产物过期。
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

#: 书级代码能 import 的 cv 模块前缀（其余 open_guji_cv.* 都算越界）。
ALLOWED_CV = ("open_guji_cv.seg", "open_guji_cv.book_api")


def _ws(args) -> Path:
    ws = Path(args.workspace or ".").expanduser().resolve()
    if not ws.is_dir():
        print(f"✗ 书仓 {ws} 不存在", file=sys.stderr)
        sys.exit(2)
    return ws


def _out(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def import_problems(root: Path, name: str) -> list[str]:
    """`code/` 下 .py 里越界的 import（顶层与函数内都算）。"""
    bad = []
    for f in sorted(root.rglob("*.py")):
        rel = f.relative_to(root).as_posix()
        if rel.startswith(("releases/", "tests/")) or "/." in "/" + rel:
            continue                  # tests/ 是本书测试，要借 cv 的 helpers，不进指纹，不查
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.ImportFrom):
                if node.level >= 2:
                    mods.append("." * node.level + (node.module or ""))
                elif node.level == 0 and node.module:
                    mods.append(node.module)
            elif isinstance(node, ast.Import):
                mods += [a.name for a in node.names]
            for m in mods:
                if m.startswith("..") :
                    bad.append(f"{rel}:{node.lineno} 相对 import 越出 code/：{m}")
                elif m.startswith("open_guji_cv") and not m.startswith(ALLOWED_CV):
                    bad.append(f"{rel}:{node.lineno} 用了 cv 内部模块 {m}（只许 {', '.join(ALLOWED_CV)}）")
                elif m.startswith("guji_book.") and not m.startswith(f"guji_book.{name}"):
                    bad.append(f"{rel}:{node.lineno} 用了别的书的代码 {m}（书之间不互相 import，要用就复制）")
    return bad


def cmd_code(args) -> None:
    from ._cv import core_book_code as bc
    ws = _ws(args)
    root = bc.code_root(ws)
    if root is None:
        _out({"workspace": str(ws), "code": None, "note": "没有 code/code.yaml：全走 cv 的缺省实现"})
        sys.exit(0 if args.code_cmd == "status" else 1)
    try:
        code = bc.load(ws)
    except bc.BookCodeError as e:
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)
    have = bc.releases(root)
    if args.code_cmd == "status":
        latest = have[-1] if have else None
        _out({"workspace": str(ws), "name": code.name, "base": code.base, "pipeline": code.pipeline, "cv": code.cv,
              "overrides": code.overrides, "releases": [f"k{n}" for n in have],
              "drift_vs_latest": bc.drift(root, latest) if latest else None,
              "working_digest": bc.digest(bc.file_table(root))[:12]})
    elif args.code_cmd == "verify":
        n = args.version or (have[-1] if have else None)
        if n is None:
            print("✗ 还没有任何版本（先 guji code release）", file=sys.stderr)
            sys.exit(1)
        d = bc.drift(root, n)
        _out({"version": f"k{n}", "clean": not d, "drift": d})
        sys.exit(1 if d else 0)
    elif args.code_cmd == "check":
        bad = import_problems(root, code.name)
        _out({"ok": not bad, "problems": bad})
        sys.exit(1 if bad else 0)
    elif args.code_cmd == "release":
        bad = import_problems(root, code.name)
        if bad:
            print("✗ import 越界，先修：\n  " + "\n  ".join(bad), file=sys.stderr)
            sys.exit(1)
        from ._cv import core_cv_version as CV
        cvv = CV.describe()[0] or "unknown"
        why = bc.check_cv(code, cvv)
        if why:
            print(f"✗ {why}", file=sys.stderr)
            sys.exit(1)
        try:
            n, p = bc.make_release(root, cv_version=cvv, note=args.note or "", samples=args.samples or "")
        except bc.BookCodeError as e:
            print(f"✗ {e}", file=sys.stderr)
            sys.exit(1)
        _out({"version": f"k{n}", "manifest": str(p),
              "next": [f"git -C {ws} add code/ && git -C {ws} commit -m 'code k{n}'",
                       f"git -C {ws} push origin HEAD:main",
                       f"打 tag k{n}：本地 git -C {ws} tag k{n} && git -C {ws} push origin k{n}；云端走中转站 "
                       f"python3 <ai-team>/process/tag.py guji-workspace/<书仓> $(git -C {ws} rev-parse HEAD) k{n} '说明'",
                       f"书配置 book_defaults.yaml 写 code: {n}（或 pin: …-k{n}），guji db push"]})


def add_parser(sub) -> None:
    p = sub.add_parser("code", help="[v2] 书级代码（书仓 code/）：status／release 出 k<N>／verify／check")
    ps = p.add_subparsers(dest="code_cmd", required=True)
    st = ps.add_parser("status", help="name、覆盖表、已有版本、工作副本差在哪")
    rel = ps.add_parser("release", help="写下一版清单 code/releases/k<N+1>.json（内容没变不出；不提交不打 tag）")
    rel.add_argument("--note", default="")
    rel.add_argument("--samples", default="", help="这版在样页单上的比对结果链接")
    ve = ps.add_parser("verify", help="工作副本 vs k<N>（退出码 1 = 有改动）")
    ve.add_argument("--version", type=int, default=None, help="缺省最新")
    ch = ps.add_parser("check", help="书级模块的 import 有没有越界")
    for q in (st, rel, ve, ch):
        q.add_argument("-w", "--workspace", default=None, help="书仓根（缺省当前目录）")


COMMANDS = {"code": (add_parser, cmd_code)}
