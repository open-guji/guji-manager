"""网站收件箱 ``web_inbox``（中心库 D1，Worker ``GET /v1/web/inbox``）读取：网站票、改字意见的新来源（A20，11-21）。

网站边缘函数在写 KV 的同时把同一份记录写进 D1 表 ``web_inbox``（过渡期双写，之后淘汰 KV）：

    GET /v1/web/inbox?kind=&book=&after=<seq>&limit=<≤500>
      → {items:[{seq, kind, key, book, ts, value}], next, hasMore}

``key`` 是网站 KV 的原键，``value`` 是写进 KV 的那份记录；同键再写覆盖（换新 seq）。所以这里取出来的 ``value``
与 ``--from-kv`` 管理读、中心库快照（``feedback/lists/web/<书>/…jsonl``）是同一份东西，下游照旧处理。

精校票两种键（A20 交接文档；M10 交接）：

- 按单版 ``cr:<rev>:<书>:<格>:<voter>`` ＝ ``/api/cellreview?rev=&book=`` 读到的；
- 按条目 ``cr:i:<书>:<条目>:<voter>`` ＝ ``/api/cellreview?items=1&book=`` 读到的。

改字／一段／专名（``kind=charfix``）的值是 ``fixes.jsonl`` 的一行（``cf:``／``cs:``／``ce:`` 键）。

**排序**：KV 列键按键名字典序回，这里也按 ``key`` 排，让产出与 ``--from-kv`` 逐字节一致（同格同来源取最新时，
时间相同才看先后）。读令牌：``GUJI_DATA_TOKEN``、``GUJI_DATA_TOKEN_PROD``、``GUJI_DATA_TOKEN_READ`` 依次试，401 换下一把
（同 ``datastore.d1conn``）；网站令牌 ``CELLREVIEW_TOKEN`` 读不了这里。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

KINDS = ("cellreview", "charfix", "thread", "feedback")
TOKEN_ENVS = ("GUJI_DATA_TOKEN", "GUJI_DATA_TOKEN_PROD", "GUJI_DATA_TOKEN_READ")
PAGE = 500
_UA = {"User-Agent": "open-guji-manager/web-inbox"}


def base_url() -> str:
    return os.environ.get("GUJI_DATA_URL", "https://data.open-guji.com").rstrip("/")


def _tokens(token_env: str | None = None) -> list[str]:
    names = [token_env] if token_env else list(TOKEN_ENVS)
    out = []
    for n in names:
        t = os.environ.get(n or "")
        if t and t not in out:
            out.append(t)
    if not out:
        raise SystemExit(f"读网站收件箱要中心库读令牌（{token_env or '、'.join(TOKEN_ENVS)}）")
    return out


def fetch(kind: str, book: str = "", after: int = 0, token_env: str | None = None, base: str | None = None,
          opener=urllib.request.urlopen, limit: int = PAGE) -> tuple[list[dict], int]:
    """按 seq 增量读全（翻页到 hasMore=false）。返回 (行, 读到的最大 seq；一行没有就是 after)。读失败直接抛。"""
    if kind not in KINDS:
        raise ValueError(f"kind 须是 {'、'.join(KINDS)}：{kind}")
    base = (base or base_url()).rstrip("/")
    toks = _tokens(token_env)
    rows: list[dict] = []
    cur = int(after)
    while True:
        q = {"kind": kind, "after": str(cur), "limit": str(limit), **({"book": book} if book else {})}
        url = f"{base}/v1/web/inbox?{urllib.parse.urlencode(q)}"
        d = None
        for i, t in enumerate(toks):
            req = urllib.request.Request(url, headers={**_UA, "Authorization": f"Bearer {t}"})
            try:
                with opener(req, timeout=60) as r:
                    d = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code == 401 and i + 1 < len(toks):
                    continue
                raise SystemExit(f"读网站收件箱失败：HTTP {e.code}（{url.split('?')[0]}）") from e
        items = (d or {}).get("items") or []
        rows += items
        if items:
            cur = max(cur, max(int(r["seq"]) for r in items))
        if not d.get("hasMore"):
            return rows, cur
        nxt = d.get("next")
        if nxt is None or int(nxt) <= int(q["after"]):
            raise SystemExit(f"读网站收件箱翻页游标不前进（after={q['after']}，next={nxt}）")
        cur = max(cur, int(nxt))


def is_tombstone(r: dict) -> bool:
    """墓碑（A20 11-21）：网站删了 KV 键（撤票、站方删除），收件箱同 kind＋key 写 ``value.deleted: true``。读到跳过，
    等同 KV 里这个键已不存在。"""
    return (r.get("value") or {}).get("deleted") is True


def live_rows(rows: list[dict]) -> list[dict]:
    """去掉探测条目（``probe:`` 键）与墓碑，按键排序（同 KV 列键顺序）。"""
    return sorted((r for r in rows if not r["key"].startswith("probe:") and not is_tombstone(r)), key=lambda r: r["key"])


def _sorted_values(rows: list[dict], pred) -> list[dict]:
    return [r["value"] for r in live_rows(rows) if pred(r["key"])]


def rev_votes(rows: list[dict], book: str, rev: str) -> list[dict]:
    """按单版记的票（``cr:<rev>:<书>:``），同 ``/api/cellreview?rev=&book=``。"""
    pre = f"cr:{rev}:{book}:"
    return _sorted_values(rows, lambda k: k.startswith(pre))


def item_votes(rows: list[dict], book: str) -> list[dict]:
    """按条目记的票（``cr:i:<书>:``），同 ``/api/cellreview?items=1&book=``。"""
    pre = f"cr:i:{book}:"
    return _sorted_values(rows, lambda k: k.startswith(pre))


def rev_files(rows: list[dict], book: str) -> dict[str, list[dict]]:
    """按单版的票按 rev 分组成 ``{"<rev>.jsonl": [票…]}``（同中心库快照的文件名），给 ``opinions ingest``。"""
    out: dict[str, list[dict]] = {}
    for r in live_rows(rows):
        parts = r["key"].split(":")
        if len(parts) < 4 or parts[0] != "cr" or parts[1] == "i" or parts[2] != book:
            continue
        out.setdefault(f"{parts[1]}.jsonl", []).append(r["value"])
    return out


def fix_values(rows: list[dict]) -> list[dict]:
    """改字／一段／专名的 KV 原值（``fixes.jsonl`` 的行）。"""
    return _sorted_values(rows, lambda k: True)


def by_prefix(kind: str, prefix: str, token_env: str | None = None, **kw) -> list[dict]:
    """不按书过滤、按键前缀取（A20 11-21：``thread`` 等值里没有 ``book``／``book_id`` 的，表里 book 为空，按书读不到）。
    返回值（已去墓碑、探测条目，按键排序）。"""
    rows, _ = fetch(kind, "", token_env=token_env, **kw)
    return _sorted_values(rows, lambda k: k.startswith(prefix))


# ---- 对账（双写期：KV 管理读 vs 收件箱）----

def vote_id(v: dict) -> str:
    """一票的身份（KV 键去掉前缀后的部分）：条目票 ``i:<条目>:<voter>``，单版票 ``<rev>:<格>:<voter>``。"""
    if v.get("item"):
        return f"i:{v['item']}:{v.get('voter')}"
    return f"{v.get('rev')}:{v.get('a')}:{v.get('voter')}"


def diff_votes(kv: list[dict], inbox: list[dict]) -> dict[str, list[str]]:
    """两边逐票比：只在 KV、只在收件箱、两边都有但值不同。``inbox`` 要先去墓碑（``item_votes``／``rev_votes`` 已去）：
    KV 键没了、收件箱是墓碑，两边都不出现，算一致。"""
    a = {vote_id(v): v for v in kv}
    b = {vote_id(v): v for v in inbox}
    same = lambda x, y: json.dumps(x, sort_keys=True, ensure_ascii=False) == json.dumps(y, sort_keys=True, ensure_ascii=False)
    return {"only_kv": sorted(set(a) - set(b)), "only_inbox": sorted(set(b) - set(a)),
            "differ": sorted(k for k in set(a) & set(b) if not same(a[k], b[k]))}
