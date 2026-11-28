# -*- coding: utf-8 -*-
"""交单前核册名：中心库里这部书有没有这一册（2026-11-28，GM2）。

## 为什么要有

册名错的单到执行机 prep 才暴露（`rerun_prep.sh` 拉完库 `ls books/<册>.yaml` 找不到），而且被当成环境问题连领三次：

* 北行 #18319（CV2 11-28）：交 `bxgb`，北行已按《册号位数统一》改名为 `1`（`books/1.yaml`，`aliases: [bxgb]`）；
* 殿本 #18292（CV4 11-27）：交 `01`，殿本还没改名，中心库仍是 `vol01`。

这里交单时查中心库 `books` 表（按 ws_glob 找到这部书的工作区）：

1. 册名就是现名 → 放过；
2. 是某册 yaml 的 `aliases` 里的旧名，或与某册按数值相等（`1`／`01`／`001`，用户 11-27 定册号按数值认）→ 换成现名，提示一句；
3. 都不是 → 拒，列出这部书的册名（同数字的优先）。

连不上中心库、找不到工作区就只提示、放过（不挡交单）。`--no-book-check` 整个跳过。
"""
from __future__ import annotations

import fnmatch
import json
import re
import sys


def resolve_name(book: str, books: list[tuple[str, list[str]]]) -> tuple[str | None, str]:
    """book 在 books（[(现名, 旧名们)]）里对应哪一册。返回 (现名或 None, 说明)。"""
    names = [n for n, _ in books]
    if book in names:
        return book, ""
    for n, al in books:
        if book in (al or []):
            return n, f"册 {book} 已改名为 {n}（册 yaml aliases），按新名交"
    if book.isdigit():
        same = [n for n in names if n.isdigit() and int(n) == int(book)]
        if len(same) == 1:
            return same[0], f"册 {book} 按数值即 {same[0]}，按 {same[0]} 交"
    return None, "册 %s 在中心库这部书里没有；%s" % (book, _hint(book, names))


def _hint(book: str, names: list[str]) -> str:
    digits = re.sub(r"\D", "", book)
    near = [n for n in names if digits and re.sub(r"\D", "", n).lstrip("0") == digits.lstrip("0")]
    if near:
        return "是不是 " + "／".join(near) + "？"
    show = sorted(names)
    return "现有册名：" + " ".join(show[:8]) + (f" …共 {len(show)} 册" if len(show) > 8 else "")


def find_ws(rows: list[tuple[str, str]], ws_glob: str) -> str | None:
    """workspaces 表的 (ws, dir) 里，哪个是 ws_glob 指的那部书：ws 等于书 ID，或目录名匹配 ws_glob。"""
    bid = ws_glob.split("-", 1)[0]
    for ws, d in rows:
        if ws == bid:
            return ws
    for ws, d in rows:
        if fnmatch.fnmatchcase(d or "", ws_glob):
            return ws
    return None


def fetch_books(cur, ws_glob: str) -> tuple[str, list[tuple[str, list[str]]]] | None:
    """(工作区 id, [(册名, aliases)])；认不出工作区返回 None。"""
    cur.execute("SELECT ws, dir FROM workspaces")
    ws = find_ws([(r[0], r[1]) for r in cur.fetchall()], ws_glob)
    if ws is None:
        return None
    cur.execute("SELECT book, doc FROM books WHERE ws = ?", [ws])
    out = []
    for name, doc in cur.fetchall():
        try:
            al = (json.loads(doc) if isinstance(doc, str) else (doc or {})).get("aliases") or []
        except (ValueError, AttributeError):
            al = []
        out.append((str(name), [str(a) for a in al] if isinstance(al, list) else [str(al)]))
    return ws, out


def check(raw: dict, *, default_glob: str, connect=None) -> str | None:
    """就地把 raw["book"] 换成现名；册名不对返回拒单理由，其余返回 None。"""
    book = raw.get("book")
    if not book:
        return None
    glob = raw.get("ws_glob") or default_glob
    try:
        if connect is None:
            from ..datastore.connect import connect
        with connect() as conn, conn.cursor() as cur:
            got = fetch_books(cur, glob)
    except BaseException as e:  # noqa: BLE001 —— 没配连库（SystemExit）也接住
        print(f"提示：没核册名 {book}（连不上中心库：{type(e).__name__}）", file=sys.stderr)
        return None
    if got is None or not got[1]:
        print(f"提示：没核册名 {book}（中心库认不出 {glob} 的工作区）", file=sys.stderr)
        return None
    ws, books = got
    name, msg = resolve_name(str(book), books)
    if name is None:
        return f"{msg}（工作区 {ws}）"
    if name != book:
        print(f"⚠ {msg}（工作区 {ws}）", file=sys.stderr)
        raw["book"] = name
    return None
