"""标 main 后自动入字格身份账（入口点组 ``guji.post_promote``，签名 ``(book, label, ws)``）。

为什么挂在标 main 上：执行机跑完的包不推数据回中心库，``hooks.finished`` 在执行机上入的账会丢；而 cv ``seed_admit``
按 ``(page, cells_sha)`` 认的是 **main 包** 的切分。所以由「哪份切分成了 main」来定入账，在标 main 的那台机器上：

1. 中心库先拉这一册的账（``guji db pull --only feedback/uid/<册>.jsonl``），免得拿旧账追加、推回去盖掉别人的行；
2. 取回刚标 main 的包到临时目录，``advance``（同一份切分的页跳过）；
3. 有新行就推回中心库（``guji db push --only``）。

没账的册：这部书已启用 u（账目录里已有别册的账，见 ``uid.book_enabled``）就按 main 包**首次入账**（读序发号，
book-text 有这册时照样参考它已发的号）；整部书都没账（没启用 u）什么都不做。永远不抛：失败只打一行提示和手跑命令，不挡标 main。
``GUJI_UID_ON_PROMOTE=0`` 整个关掉；``GUJI_UID_AUTO_PUSH=0`` 只入本机账、不推。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _rel(book: str) -> str:
    return f"feedback/uid/{book}.jsonl"


def _env() -> dict:
    e = dict(os.environ)
    if e.get("GUJI_DATA_TOKEN_PROD"):            # 推中心库要写令牌（同 online_lists 口径）
        e["GUJI_DATA_TOKEN"] = e["GUJI_DATA_TOKEN_PROD"]
    e.setdefault("GUJI_ACTOR", e.get("GUJI_JOBS_WHO") or "uid-on-promote")
    return e


def _db(op: str, book: str, ws: str, env: dict) -> tuple[bool, str]:
    from ..online_lists import _guji_cmd
    r = subprocess.run([*_guji_cmd(), "db", op, "-w", ws, "--only", _rel(book), *(["--no-rebuild"] if op == "pull" else [])],
                       capture_output=True, text=True, env=env)
    return r.returncode == 0, (r.stderr or r.stdout).strip()[-300:]


def on_promote(book: str, label: str, ws: str | None = None) -> None:
    try:
        if os.environ.get("GUJI_UID_ON_PROMOTE", "1") == "0":
            return
        if ws:
            os.environ["GUJI_WORKSPACE"] = str(Path(ws).resolve())
        from . import advance, book_enabled, enabled
        first = not enabled(book)
        if first and not book_enabled():
            return
        manual = f"guji uid advance {book} -w <工作区> --products <取回的 main 包根> 后 guji db push --only {_rel(book)}"
        env = _env()
        push = bool(ws) and os.environ.get("GUJI_UID_AUTO_PUSH", "1") != "0"
        if push:
            ok, msg = _db("pull", book, ws, env)
            if not ok:
                print(f"⚠ 字格身份账：拉中心库 {book} 的账失败，没入账（{msg}）；手跑：{manual}", file=sys.stderr)
                return
        from .._cv import ProductStore
        from ..datastore.packs import fetch_products
        with tempfile.TemporaryDirectory(prefix="uid-promote-") as tmp:
            fetch_products(book, Path(tmp), label=label)
            r = advance(book, ProductStore(Path(tmp)), src="promote")
        if not r["entered"]:
            return
        print(f"字格身份账：{book} 按新 main 包{'首次' if first else ''}入账 {r['entered']} 页（u_max={r['u_max']}，{r['via']}）", file=sys.stderr)
        if push:
            ok, msg = _db("push", book, ws, env)
            print(f"字格身份账：已推中心库 {_rel(book)}" if ok else
                  f"⚠ 字格身份账：推中心库失败（{msg}）；手跑 guji db push -w <工作区> --only {_rel(book)}", file=sys.stderr)
    except (Exception, SystemExit) as e:  # noqa: BLE001 —— 不挡标 main
        print(f"⚠ 字格身份账：标 main 后入账失败（{book} {label}）：{e}", file=sys.stderr)
