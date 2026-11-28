"""`guji pending-parity`：对账「网站待审数＝中心库 open 数」（清理计划 v2，2026-11-28）。

    guji pending-parity [--site https://www.openguji.com] [--books a,b] [--json]

按（书, 册）比：中心库 ``pending_current`` 里 ``state='open'`` 的条目数，对网站 ``/api/pending-index?book=`` 给的各章待审数。
网站读时现算（落定的格不显示），``pending-settle`` 把落定的开着条目标 resolved——两边应该相等；
中心库比网站多＝落定了没标（跑 ``guji pending-settle --apply``）；网站比中心库多＝条目表里没有、网站却在显示（查 Worker）。
有任何一册不等就退出码 1，可挂 CI／定时。只读，用 GUJI_DATA_TOKEN_READ 之类的只读令牌即可，不打印令牌。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request


def vol_key(v: object) -> str:
    """册／章号归一：取其中的数字、去前导零（``01``／``001``／``vol01`` 同口径，同 Worker normVol）；没有数字原样。"""
    m = re.search(r"\d+", str(v))
    return str(int(m.group())) if m else str(v)


def compare(db_open: dict[tuple[str, str], int], site: dict[tuple[str, str], int]) -> list[dict]:
    """两边（书, 册）→ 数目；返回不等的行 ``{book, vol, db, site, diff}``（diff＝db−site），按书册排序。"""
    rows = []
    for k in sorted(set(db_open) | set(site)):
        d, s = db_open.get(k, 0), site.get(k, 0)
        if d != s:
            rows.append({"book": k[0], "vol": k[1], "db": d, "site": s, "diff": d - s})
    return rows


def db_open_counts(conn, books: list[str] | None = None) -> dict[tuple[str, str], int]:
    sql = "SELECT book, vol, count(*) FROM pending_current WHERE state = 'open'"
    params: list = []
    if books:
        sql += " AND book IN (" + ",".join("?" * len(books)) + ")"
        params = list(books)
    sql += " GROUP BY book, vol"
    out: dict[tuple[str, str], int] = {}
    for book, vol, n in conn.execute(sql, params).fetchall():
        k = (book, vol_key(vol))
        out[k] = out.get(k, 0) + int(n)
    return out


def site_counts(site: str, books: list[str], skipped: list[str] | None = None) -> dict[tuple[str, str], int]:
    """网站各书各册待审数。网站不认的书 id（HTTP 400，如不足 4 位的 ``mai``）不算不等，记进 ``skipped``。"""
    out: dict[tuple[str, str], int] = {}
    for b in books:
        req = urllib.request.Request(f"{site.rstrip('/')}/api/pending-index?book={b}", headers={"User-Agent": "guji-pending-parity"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                counts = json.load(r).get("counts") or {}
        except urllib.error.HTTPError as e:
            if e.code != 400:
                raise
            if skipped is not None:
                skipped.append(b)
            continue
        for vol, n in counts.items():
            if n:
                out[(b, vol_key(vol))] = out.get((b, vol_key(vol)), 0) + int(n)
    return out


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("pending-parity", help="对账：网站待审数＝中心库 open 条目数（不等退出码 1）")
    p.add_argument("--site", default="https://www.openguji.com")
    p.add_argument("--books", default=None, help="只比这些书 id（逗号分隔）；缺省比中心库里有 open 条目的全部书")
    p.add_argument("--json", action="store_true")


def cmd_pending_parity(a) -> int:
    from .datastore.connect import connect
    from . import dbconfig
    dbconfig.apply_env()
    conn = connect()
    books = [x.strip() for x in (a.books or "").split(",") if x.strip()] or None
    db = db_open_counts(conn, books)
    skipped: list[str] = []
    site = site_counts(a.site, books or sorted({b for b, _ in db}), skipped)
    db = {k: v for k, v in db.items() if k[0] not in skipped}
    bad = compare(db, site)
    tot_db, tot_site = sum(db.values()), sum(site.values())
    if a.json:
        print(json.dumps({"db_open": tot_db, "site": tot_site, "skipped_books": skipped, "mismatch": bad}, ensure_ascii=False, indent=1))
    else:
        print(f"中心库 open {tot_db}，网站待审 {tot_site}，不等的（书,册）{len(bad)} 个")
        if skipped:
            print(f"网站不认的书 id（没比）：{'、'.join(skipped)}")
        for r in bad[:40]:
            print(f"  {r['book']} 册{r['vol']}：中心库 {r['db']}／网站 {r['site']}（{r['diff']:+d}）")
        if any(r["diff"] > 0 for r in bad):
            print("中心库比网站多：落定了没标，跑 guji pending-settle --apply --sync")
        if any(r["diff"] < 0 for r in bad):
            print("网站比中心库多：条目表里没有、网站却在显示，查 Worker")
    return 1 if bad else 0


COMMANDS = {"pending-parity": (add_parser, cmd_pending_parity)}
