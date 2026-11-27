"""标 main 后自动入字格身份账（入口点组 ``guji.post_promote``，签名 ``(book, label, ws)``）。

为什么挂在标 main 上：执行机跑完的包不推数据回中心库，``hooks.finished`` 在执行机上入的账会丢；而 cv ``seed_admit``
按 ``(page, cells_sha)`` 认的是 **main 包** 的切分。所以由「哪份切分成了 main」来定入账，在标 main 的那台机器上：

1. 中心库先拉这一册的账（``guji db pull --only feedback/uid/<册>.jsonl``），免得拿旧账追加、推回去盖掉别人的行；
2. 取回刚标 main 的包到临时目录，``advance``（同一份切分的页跳过）；
3. 有新行就推回中心库（``guji db push --only``）。

没账的册：这部书已启用 u（账目录里已有别册的账，见 ``uid.book_enabled``）就按 main 包**首次入账**（读序发号，
book-text 有这册时照样参考它已发的号）；整部书都没账（没启用 u）什么都不做。永远不抛：失败只打一行提示和手跑命令，不挡标 main。
同一套入账（``sync``）另有两处兜底（11-25，标 main 的人用的 manager 版本管不住，钩子会漏）：执行机开跑前铺 main 底后
（``jobs/runner.py`` 的 ``uid`` 步）、定时自检（``uid/audit.py``，空闲执行方几小时一次，缺的交 ``uidsync`` 单）。
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


def sync(book: str, label: str | None = None, ws: str | None = None, *, products: str | Path | None = None,
         src: str = "sync", push: bool = True, reconfirm: bool = False) -> dict:
    """把这册 main 包（``label``，缺省现行 main）的切分入账并推中心库；标 main 钩子、执行机开跑前、定时自检共用。

    ``products`` 给了就用那份产物（执行机刚铺的底），否则取回 ``label`` 包到临时目录。返回
    ``{"status": disabled|pull_failed|entered|synced|unchanged|push_failed, "entered": 页数, "label": …}``；出错照抛。
    ``reconfirm``：包已对过账也再记一笔带时间的「已对过」（见 ``mark_synced``）。"""
    if ws:
        os.environ["GUJI_WORKSPACE"] = str(Path(ws).resolve())
    from . import advance, book_enabled, enabled, mark_synced
    env = _env()
    push = push and bool(ws) and os.environ.get("GUJI_UID_AUTO_PUSH", "1") != "0"
    if not (enabled(book) or book_enabled()):
        return {"status": "disabled", "entered": 0, "label": label}
    if push:
        ok, msg = _db("pull", book, ws, env)
        if not ok:
            return {"status": "pull_failed", "entered": 0, "label": label, "msg": msg}
    from .._cv import ProductStore
    from ..datastore.packs import fetch_products, main_label
    label = label or main_label(book)
    if not label:
        return {"status": "disabled", "entered": 0, "label": None, "msg": "这册没有 main 包"}
    if products:                        # "local"：本机现行产物根（执行机刚铺的底）
        st = ProductStore() if str(products) == "local" else ProductStore(Path(products))
        r = advance(book, st, src=src, label=label)
    else:
        with tempfile.TemporaryDirectory(prefix="uid-sync-") as tmp:
            fetch_products(book, Path(tmp), label=label)
            r = advance(book, ProductStore(Path(tmp)), src=src, label=label)
    # reconfirm（标 main 钩子、自检交的 uidsync 单）：同一个包重标 main 也记一笔，自检才不会一直报缺
    status = "entered" if r["entered"] else ("synced" if mark_synced(book, label, src=src, reconfirm=reconfirm)
                                             else "unchanged")
    from .ledger import fix_dup_ids
    renamed = fix_dup_ids(book)         # 旧版本入账写出的重复 id（切回旧切分的页）先改名，不然推库闸拦（QTW 11-26）
    out = {"status": status, "entered": r["entered"], "label": label, "u_max": r["u_max"], "via": r["via"]}
    if renamed:
        out["renamed_ids"] = len(renamed)
    if push and (status != "unchanged" or renamed):
        ok, msg = _db("push", book, ws, env)
        if not ok:
            out.update(status="push_failed", msg=msg)
    return out


def on_promote(book: str, label: str, ws: str | None = None) -> None:
    manual = f"guji uid sync {book} -w <工作区> --label {label}"
    try:
        if os.environ.get("GUJI_UID_ON_PROMOTE", "1") == "0":
            return
        r = sync(book, label, ws, src="promote", reconfirm=True)
        if r["status"] == "pull_failed":
            print(f"⚠ 字格身份账：拉中心库 {book} 的账失败，没入账（{r.get('msg')}）；手跑：{manual}", file=sys.stderr)
        elif r["status"] == "push_failed":
            print(f"⚠ 字格身份账：{book} 入账 {r['entered']} 页，推中心库失败（{r.get('msg')}）；"
                  f"手跑 guji db push -w <工作区> --only {_rel(book)}", file=sys.stderr)
        elif r["entered"]:
            print(f"字格身份账：{book} 按新 main 包入账 {r['entered']} 页（u_max={r['u_max']}，{r['via']}）", file=sys.stderr)
    except (Exception, SystemExit) as e:  # noqa: BLE001 —— 不挡标 main
        print(f"⚠ 字格身份账：标 main 后入账失败（{book} {label}）：{e}；手跑：{manual}", file=sys.stderr)
