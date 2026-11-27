"""网站旧票回填字格永久编号 u（T5 收尾，A20 CV0 11-25）：中心库 ``web_inbox`` 里没带 u 的精校票、改字意见，
按字格身份账把票上的格号换成 u **补进 value**（只补字段，别的不动）。

网站 T5（kaiyuanguji-web #887）上线后新票自带 u；之前的票只有格号。格号是出单那一版切分的位置，
账上同一页可能有几份切分（``init`` 从 book-text 建、``advance`` 按现行产物接），所以**不能只看格号**：

- 候选：账上这一页**每一行**（每份切分）里这个格号的 u，连同那一行记的字（``chars``）。
- 核字：票上有当时看到的字就拿来比（同字判定走本书归一表 ``charnorm``）——
  精校票 ``shown``（单上显示的字；早期票没有 shown 时退用投票人给的字，选字、切分错带字那几档，计「票字同」）、改字 ``old_char``、一段 ``old_text`` 首／末字、专名 ``text`` 首／末字。
  候选里**恰有一个 u 的字对得上**才配；对上两个以上不同 u → 清单（多份切分同字异号，分不清）。
- 票上没字可比，或账行没记字：只在该页账**只入过一次**（切分没变过、格号只对一个 u）时按格号配。
- 其余进清单（理由：账上没这一页／格号不在账里／字对不上／…），**不动**。

配上的 u 已作废（并掉、删掉）也照写：u 记的是投票时那一格的身份，作废由下游（``web_votes.resolve_u``）挂起交人看；
结果里单独计数。

写法：``UPDATE web_inbox SET value = json_set(value, '$.u', …)``（一段、专名写 ``u_start``／``u_end``），
**同时换新 seq**（同 Worker 覆盖规矩：读的人按 ``after=<seq>`` 增量拉，不换 seq 就拉不到补过 u 的票）；
``WHERE value = <读到的原值>``，读后网站又改了这张票的就不写（计「写时已变」）。ts、received_at、actor、键都不动。
守恒：``票 = 已有 u + 配上 + 清单``，对不上抛错。
"""
from __future__ import annotations

import json
import re
from collections import Counter

from .uid.ledger import KIND, Ledger
from .voter import voter_tag

#: 这些档带的字是「这格就是 X」（cut／jiazhu／main 给了字也是），可拿来当核字的字；none、unsure、figure、damaged 的字不算
VOTE_CHAR_CHOICES = ("char", "cut", "jiazhu", "main")
A_RE = re.compile(r"^(\d+):(\d+):(-?\d+)([ab]?)$")


def ledger_from_raws(book: str, raws) -> Ledger:
    """中心库 events（stream=uid）的 raw 列（按 src_line 排好）→ Ledger（不落盘）。"""
    lines = []
    for r in raws:
        d = json.loads(r) if isinstance(r, str) else r
        if d.get("kind") == KIND:
            lines.append(d)
    from pathlib import Path
    return Ledger(book, Path("/dev/null"), lines)


def _page(a: str) -> int | None:
    m = A_RE.match(a or "")
    return int(m[1]) if m else None


class Resolver:
    """册内 格号（book-text 的 a，不带册前缀）＋当时的字 → u。"""

    def __init__(self, led: Ledger, same=None):
        self.led = led
        self.same = same or (lambda x, y: x == y)
        self.pre = f"{led.book}:"
        self.rows: dict[int, list[dict]] = {}
        for d in led.lines:
            self.rows.setdefault(int(d["page"]), []).append(d)
        self.retired = set(led.retired())

    def resolve(self, a: str, hint: str | None) -> tuple[int | None, str]:
        """→ (u, 怎么配的) 或 (None, 理由)。"""
        pg = _page(a)
        if pg is None:
            return None, f"格号不合法：{a}"
        rows = self.rows.get(pg)
        if not rows:
            return None, "账上没有这一页"
        k = self.pre + a
        cands = [(int(d["map"][k]), (d.get("chars") or {}).get(k)) for d in rows if k in d["map"]]
        if not cands:
            return None, "格号不在账里（任何一份切分都没有）"
        us = list(dict.fromkeys(u for u, _ in cands))
        hint = (hint or "").strip()
        if hint:
            hit = list(dict.fromkeys(u for u, ch in cands if ch and self.same(ch, hint)))
            if len(hit) == 1:
                return hit[0], "字同"
            if len(hit) > 1:
                return None, f"几份切分同字异号（u{'、u'.join(map(str, hit))}）"
            seen = sorted({ch for _, ch in cands if ch})
            if seen:
                return None, f"字对不上（票「{hint}」，账「{'、'.join(seen)}」）"
        if len(rows) == 1 and len(us) == 1:
            return us[0], "该页只切过一次"
        return None, ("账行没记字，且该页切过不止一次" if hint else "票上没字可核，且该页切过不止一次")


def _ends(text) -> tuple[str, str]:
    s = str(text or "")
    return (s[0], s[-1]) if s else ("", "")


SRC_RE = re.compile(r"^网站精校意见（([^）]+)）；意见来源 (.+)$")


def vote_events(rows) -> dict[tuple[str, str, str], dict]:
    """网站票导成的人裁事件（payload.source＝「网站精校意见（<rev>）；意见来源 <voter 前 16 位>、…」）
    → {(rev, 格号 a, voter16): {root, u?}}。

    一张票导入后可能又被抄过：``~r``（第 7 轮换图源 rebase，格号换成新 rev 的）、``~u``（T2 补 u）、``~q`` 等；
    同一个 root（id 第一个 ``~`` 之前）是一条链。格号取 root 那条（就是票上的格号），u 取链上最后一条带 ``anchor.u`` 的。
    ``rows``：(id, payload, target)，payload／target 为 dict 或 JSON 串。"""
    chain: dict[str, dict] = {}
    for eid, pl, tg in rows:
        pl = json.loads(pl) if isinstance(pl, str) else (pl or {})
        tg = json.loads(tg) if isinstance(tg, str) else (tg or {})
        m = SRC_RE.match(str(pl.get("source") or ""))
        if not m:
            continue
        root = eid.split("~", 1)[0]
        c = chain.setdefault(root, {"root": root})
        if eid == root:
            c["key"] = tg.get("key")
            c["rev"], c["voters"] = m[1], [x.strip() for x in m[2].split("、") if x.strip()]
        u = (tg.get("anchor") or {}).get("u")
        if isinstance(u, int) and u > 0:
            c["u"] = u
    out: dict[tuple[str, str, str], dict] = {}
    for c in chain.values():
        if not c.get("key") or ":" not in c["key"]:
            continue
        a = c["key"].split(":", 1)[1]
        for v in c["voters"]:
            out[(c["rev"], a, v[:16])] = c
    return out


def plan_rows(res: Resolver, rows: list[dict], events: dict | None = None) -> dict:
    """rows：web_inbox 行 {kind, key, value(str)}；``events``＝``vote_events`` 的结果（给了就用来配账上配不上的精校票）。
    → {fills, 清单, 已有u, 守恒, 方式, 作废}。

    精校票若已导成人裁事件（``events``）且那条事件链已补 u（T2），**以事件的 u 为准**（计「人裁事件」）；
    导过但事件链没 u、账上也配不上的进清单，理由写「已导成人裁…」，与真正没处理过的票分开。"""
    events = events or {}
    fills, left, had = [], [], 0
    how = Counter()
    retired = 0
    for r in rows:
        v = json.loads(r["value"])
        base = {"kind": r["kind"], "key": r["key"], "old": r["value"]}
        if r["kind"] == "cellreview":
            if "u" in v:
                had += 1
                continue
            a = str(v.get("a") or "")
            hint = v.get("shown")
            if not hint and v.get("choice") in VOTE_CHAR_CHOICES and v.get("char"):
                hint = v["char"]               # 早期票没记 shown：拿投票人给的字核（单独计「票字同」）
            u, why = res.resolve(a, hint)
            if u is not None and why == "字同" and not v.get("shown"):
                why = "票字同"
            ev = events.get((str(v.get("rev") or ""), a, voter_tag(str(v.get("voter") or ""))[:16]))
            if ev is not None and ev.get("u"):
                # 已导成人裁、事件链有 u：以它为准（换图源的票走过几何 rebase，比按格号＋字核更可靠；11-25 实测 473 条里 2 条不一致）
                why = "人裁事件" if u in (None, ev["u"]) else "人裁事件（账上按字配的是另一个 u）"
                u = ev["u"]
            elif u is None and ev is not None:
                left.append({**base, "格": a, "理由": f"已导成人裁 {ev['root']}（事件链还没 u）；账上：{why}"})
                continue
            if u is None:
                left.append({**base, "格": a, "理由": why})
                continue
            fills.append({**base, "格": a, "set": {"u": u}, "how": why})
            how[why] += 1
            retired += u in res.retired
            continue
        kind = v.get("kind")
        if kind == "char":
            if "u" in v:
                had += 1
                continue
            a = str(v.get("cell_id") or "")
            u, why = res.resolve(a, v.get("old_char"))
            if u is None:
                left.append({**base, "格": a, "理由": why})
                continue
            fills.append({**base, "格": a, "set": {"u": u}, "how": why})
            how[why] += 1
            retired += u in res.retired
            continue
        if kind in ("span", "entity"):
            if "u_start" in v or "u_end" in v:
                had += 1
                continue
            if kind == "span":
                s, e, txt = v.get("start"), v.get("end"), v.get("old_text")
            else:
                an = v.get("anchor") or {}
                s, e, txt = an.get("start"), an.get("end"), v.get("text")
            h0, h1 = _ends(txt)
            us, why_s = res.resolve(str(s or ""), h0)
            ue, why_e = res.resolve(str(e or ""), h1)
            if us is None or ue is None:
                left.append({**base, "格": f"{s}~{e}", "理由": f"起：{why_s}；止：{why_e}"})
                continue
            fills.append({**base, "格": f"{s}~{e}", "set": {"u_start": us, "u_end": ue}, "how": why_s})
            how[why_s] += 1
            retired += (us in res.retired) or (ue in res.retired)
            continue
        left.append({**base, "格": "", "理由": f"不认得的意见类别 {kind!r}"})
    cons = {"票": len(rows), "已有u": had, "配上": len(fills), "清单": len(left)}
    if cons["票"] != had + len(fills) + len(left):
        raise AssertionError(f"不守恒：{cons}")
    return {"fills": fills, "清单": left, "守恒": cons, "方式": dict(how), "配上的u已作废": retired}


# ───────────── 中心库读写 ─────────────

def load_ledger(conn, ws: str, book: str) -> Ledger:
    rows = conn.execute(
        "SELECT raw FROM events WHERE ws = %s AND stream = 'uid' AND src_path = %s ORDER BY src_line",
        [ws, f"feedback/uid/{book}.jsonl"]).fetchall()
    return ledger_from_raws(book, [r[0] for r in rows])


def load_votes(conn, site_book: str, site_vol: str) -> list[dict]:
    """本书本册的精校票（value.vol）与改字意见（value.volume）。"""
    out = []
    for kind, field in (("cellreview", "vol"), ("charfix", "volume")):
        rows = conn.execute(
            f"SELECT kind, key, value FROM web_inbox WHERE kind = %s AND book = %s "
            f"AND json_valid(value) AND json_extract(value, '$.{field}') = %s ORDER BY key",
            [kind, site_book, site_vol]).fetchall()
        out += [{"kind": k, "key": key, "value": val} for k, key, val in rows]
    return out


def load_vote_events(conn, ws: str, book: str) -> dict:
    rows = conn.execute(
        "SELECT id, payload, target FROM events WHERE ws = %s AND stream = 'events' AND kind = 'confirm' "
        "AND book = %s AND json_extract(payload, '$.source') LIKE %s",
        [ws, book, "网站精校意见%"]).fetchall()
    return vote_events(rows)


def apply(conn, fills: list[dict]) -> dict:
    """逐条写，``RETURNING key`` 数实际写了几条（经 Worker 拿不到 rowcount）。→ {写入, 写时已变}。

    u 一律 ``CAST(? AS INTEGER)``：经 Worker 的 JSON 参数到 D1 会绑成 REAL，json_set 写出 ``16.0``，
    虚拟列 ``u``（只认 json_type=integer）就是 NULL、下游 ``vote_u`` 也不认（11-25 线上踩过，已修回）。"""
    n = stale = 0
    for f in fills:
        keys = list(f["set"])
        path_args = ", ".join("%s, CAST(%s AS INTEGER)" for _ in keys)
        params: list = []
        for k in keys:
            params += [f"$.{k}", int(f["set"][k])]
        got = conn.execute(
            f"UPDATE web_inbox SET value = json_set(value, {path_args}), "
            f"seq = (SELECT COALESCE(MAX(seq), 0) + 1 FROM web_inbox) "
            f"WHERE kind = %s AND key = %s AND value = %s RETURNING key",
            params + [f["kind"], f["key"], f["old"]]).fetchall()
        if len(got) == 1:
            n += 1
        else:
            stale += 1
    return {"写入": n, "写时已变": stale}
