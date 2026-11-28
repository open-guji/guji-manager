"""落票策略：一格上的网站人审票，够不够自动落成人裁事件、写进 book-text（GM4，2026-11-23 起；11-28 加规则策略）。

**这是「谁的票能直接落地」的唯一定义处**（落定口径本身在 ``levels.py``，这里只管「票够不够格落成事件」）。
以后调策略只改本文件（或它读的两份数据：名册、规则），别处不判。

接口只有一个：``policy.decide(cell, votes, book=None) -> Decision``。``votes`` 是这一格上经 ``latest_votes`` 去重后的票
（每人一票，带 ``voter``、``choice``、``char``）；``book`` 是网站书 id（``--site-book``）；``Decision.land`` 为真才进
``cellvotes draft`` 的分流。策略不管票内容是否冲突、格位对不对——那是 ``triage`` 的闸（意见不一致、推翻旧裁、格位变了照旧
挂起）。没到门槛的格不落、不结案（条目仍开着，票留在收件箱），报告里记为「等多人投票」。

三步，各自独立可换：
1. **身份**：``Standing(tier, books)``。``roster(voter)`` 回答「这位投票人是谁」——匿名（16 位 hex）＝``anon``；会员号查名册，
   没列的会员＝``member``；名册里有等级和负责的书。名册现在读 JSON（``GUJI_MEMBER_ROSTER``，旧名 ``GUJI_REVIEWER_TIERS``
   也认）：``{"<会员号>": {"tier": "editor", "books": [<范围>, …]}}``，值写成字符串＝只有等级。将来换成读网站会员接口，
   只换 ``load_roster``。等级阶梯 ``TIERS``：anon < member < reviewer < editor < admin < owner（网站角色 reader／reviewer／
   editor／admin 对应 member／reviewer／editor／admin；owner 是站方本人）。
   **负责的范围** ``books`` 是个列表，每项可以是：版本（Book id，即网站书 id，直接写）、``work:<作品id>``、``collection:<丛书id>``
   （11-28 用户定）。写了作品或丛书，就管它名下**所有版本**。版本怎么归到作品／丛书，由 ``Lineage`` 回答（``load_lineage``，
   现读 JSON ``GUJI_BOOK_LINEAGE``：``{"<书id>": {"work": "<作品id>", "collections": ["<丛书id>", …]}}``；将来换成读 book-index，
   只换这一个函数）；查不到的书只认版本这一项。
2. **规则**：``Rules`` 一个数据类，可由 JSON（``GUJI_LANDING_RULES`` 或 ``rules:<路径>``）整份盖掉：
   ``solo_tiers``（缺省 editor、admin、owner：一票即落）、``book_owner_solo``（缺省真：名册里 ``books`` 覆盖这本书（版本／作品／丛书）的人，一票即落）、
   ``quorum``（缺省 0＝不开：其余人无论几票都不直接落；设 N＝至少 N 个 ``quorum_min_tier`` 以上的人同一结论才落）、
   ``quorum_min_tier``（缺省 member：匿名永远不计入）。
3. **策略**：``auto``（有票就落）、``quorum:N``（旧，保留）、``rules``（按上面两步判）。选策略 ``--policy`` 或 ``GUJI_LANDING_POLICY``。

缺省仍是 ``auto``（现在只有用户本人在审）；名册接好后改成 ``rules`` 即切换，不用动代码。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..voter import is_member

DEFAULT_TIER = "member"
SOLO_TIERS = ("owner", "editor")          # 旧 quorum 策略的缺省；rules 策略的缺省见 Rules
#: 等级阶梯，低→高。
TIERS = ("anon", "member", "reviewer", "editor", "admin", "owner")


@dataclass(frozen=True)
class Decision:
    land: bool
    why: str = ""


@dataclass(frozen=True)
class Standing:
    """一位投票人的身份：等级＋他直接负责的书（网站书 id）。"""
    tier: str = DEFAULT_TIER
    books: frozenset = frozenset()

    def at_least(self, tier: str) -> bool:
        return TIERS.index(self.tier if self.tier in TIERS else DEFAULT_TIER) >= TIERS.index(tier)


# ───────────── 1. 身份：名册 ─────────────

def load_roster(path: str | os.PathLike | None = None) -> dict[str, Standing]:
    """读名册 JSON：``{会员号: {"tier":…, "books":[…]}}`` 或 ``{会员号: "等级"}``。读不到＝空名册（人人是 member）。
    将来换成网站会员接口，只改这个函数（返回同形的 dict）。"""
    p = path or os.environ.get("GUJI_MEMBER_ROSTER") or os.environ.get("GUJI_REVIEWER_TIERS")
    if not p or not Path(p).is_file():
        return {}
    try:
        raw = json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for voter, v in raw.items():
        if isinstance(v, str):
            v = {"tier": v}
        if isinstance(v, dict):
            out[str(voter)] = Standing(str(v.get("tier") or DEFAULT_TIER), frozenset(map(str, v.get("books") or ())))
    return out


# ───────────── 1b. 负责范围：版本／作品／丛书 ─────────────

def load_lineage(path: str | os.PathLike | None = None) -> dict[str, dict]:
    """版本归属：``{书id: {"work": 作品id, "collections": [丛书id…]}}``。读不到＝空（每本书只属于它自己）。
    将来换成读 book-index 的 Book（work_id、丛书 Collection），返回同形的 dict 即可。"""
    p = path or os.environ.get("GUJI_BOOK_LINEAGE")
    if not p or not Path(p).is_file():
        return {}
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def scope_keys(book: str | None, lineage: dict[str, dict] | None = None) -> set[str]:
    """一本书（版本）算在哪些范围里：自己、所属作品、所属各丛书。范围项的写法：``<书id>``｜``work:<id>``｜``collection:<id>``。"""
    if not book:
        return set()
    ln = (load_lineage() if lineage is None else lineage).get(book) or {}
    keys = {book}
    if ln.get("work"):
        keys.add(f"work:{ln['work']}")
    keys.update(f"collection:{c}" for c in ln.get("collections") or ())
    return keys


def standing_of(voter: str, roster: dict[str, Standing] | None = None) -> Standing:
    """这位投票人的身份：匿名＝anon；会员查名册，没列的＝member。"""
    if not is_member(voter):
        return Standing("anon")
    r = load_roster() if roster is None else roster
    return r.get(voter) or Standing(DEFAULT_TIER)


def reviewer_tier(voter: str) -> str:
    """审阅人的等级（旧接口，quorum 策略用；不区分匿名，名册里没有的都是 member）。"""
    return (load_roster().get(voter) or Standing(DEFAULT_TIER)).tier


# ───────────── 2. 规则（数据）─────────────

@dataclass(frozen=True)
class Rules:
    solo_tiers: tuple = ("editor", "admin", "owner")   # 这些等级一票即落
    book_owner_solo: bool = True                        # 名册里负责这本书的人一票即落
    quorum: int = 0                                     # 0＝不开；N＝至少 N 个够格的人同一结论才落
    quorum_min_tier: str = "member"                     # 计入 quorum 的最低等级（anon 永远不计）

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "Rules":
        p = path or os.environ.get("GUJI_LANDING_RULES")
        if not p:
            return cls()
        try:
            raw = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise SystemExit(f"落票规则读不了：{p}（{e}）")
        bad = set(raw) - set(cls.__dataclass_fields__)
        if bad:
            raise SystemExit(f"落票规则有不认识的项：{sorted(bad)}")
        r = replace(cls(), **{k: (tuple(v) if k == "solo_tiers" else v) for k, v in raw.items()})
        if r.quorum_min_tier not in TIERS[1:] or any(t not in TIERS for t in r.solo_tiers):
            raise SystemExit(f"落票规则的等级须在 {TIERS}（quorum_min_tier 不含 anon）")
        return r


# ───────────── 3. 策略 ─────────────

class AutoPolicy:
    """缺省：有票就落（单人审阅期）。"""
    name = "auto"

    def decide(self, cell: str, votes: list[dict], book: str | None = None) -> Decision:
        return Decision(True) if votes else Decision(False, "无票")


class QuorumPolicy:
    """（旧）高等级（``solo``）一票即定；否则要至少 ``need`` 个人投了同一结论（选项＋字）才落。"""

    def __init__(self, need: int = 2, solo: tuple[str, ...] = SOLO_TIERS, tier=reviewer_tier):
        self.need, self.solo, self.tier = need, tuple(solo), tier
        self.name = f"quorum:{need}"

    def decide(self, cell: str, votes: list[dict], book: str | None = None) -> Decision:
        if any(self.tier(v.get("voter") or "") in self.solo for v in votes):
            return Decision(True)
        tally: dict[tuple, int] = {}
        for v in votes:
            k = (v.get("choice"), v.get("char") or "")
            tally[k] = tally.get(k, 0) + 1
        top = max(tally.values(), default=0)
        if top >= self.need:
            return Decision(True)
        return Decision(False, f"等多人投票（同一结论最多 {top} 人，要 {self.need} 人）")


class RulesPolicy:
    """按身份与规则判：solo 等级的人、负责这本书的人，一票即落；其余按 ``rules.quorum``（缺省不开）；匿名票从不单独落地。
    「一票即落」只认这个人**自己**那一票：一格上别人的票不一致由 ``triage`` 的闸挂起，不在这里管。"""
    name = "rules"

    def __init__(self, rules: Rules | None = None, roster: dict[str, Standing] | None = None,
                 lineage: dict[str, dict] | None = None):
        self.rules = rules or Rules.load()
        self.roster = load_roster() if roster is None else roster
        self.lineage = load_lineage() if lineage is None else lineage

    def decide(self, cell: str, votes: list[dict], book: str | None = None) -> Decision:
        r = self.rules
        sts = [(v, standing_of(v.get("voter") or "", self.roster)) for v in votes]
        scope = scope_keys(book, self.lineage)
        for v, st in sts:
            if st.tier in r.solo_tiers:
                return Decision(True, f"{st.tier} 一票即落")
            if r.book_owner_solo and scope & st.books:
                return Decision(True, "负责本书（%s）" % "、".join(sorted(scope & st.books)))
        if r.quorum:
            tally: dict[tuple, int] = {}
            for v, st in sts:
                if st.at_least(r.quorum_min_tier):
                    k = (v.get("choice"), v.get("char") or "")
                    tally[k] = tally.get(k, 0) + 1
            top = max(tally.values(), default=0)
            if top >= r.quorum:
                return Decision(True, f"{top} 位{r.quorum_min_tier}以上会员同一结论")
        n_anon = sum(1 for _, st in sts if st.tier == "anon")
        why = "等有权限的人确认（会员 %d 票、匿名 %d 票，都不能直接落地）" % (len(sts) - n_anon, n_anon)
        return Decision(False, why)


def get_policy(spec: str | None = None):
    spec = (spec or os.environ.get("GUJI_LANDING_POLICY") or "auto").strip()
    if spec == "auto":
        return AutoPolicy()
    if spec.startswith("quorum"):
        _, _, n = spec.partition(":")
        return QuorumPolicy(int(n) if n else 2)
    if spec == "rules" or spec.startswith("rules:"):
        return RulesPolicy(Rules.load(spec.partition(":")[2] or None))
    raise SystemExit(f"--policy 只认 auto、quorum[:N]、rules[:规则文件]：{spec}")


def apply_policy(policy, votes: list[dict], book: str | None = None) -> tuple[list[dict], list[tuple[str, str, list[dict]]]]:
    """按格分组过策略。返回 (放行的票, [(格, 原因, 票)…] 等多人的)。``book`` 是网站书 id（负责人规则要用）。"""
    by: dict[str, list[dict]] = {}
    for v in votes:
        by.setdefault(v["a"], []).append(v)
    wait = []
    for a, vs in by.items():
        d = policy.decide(a, vs, book)
        if not d.land:
            wait.append((a, d.why, vs))
    held = {a for a, _, _ in wait}
    return [v for v in votes if v["a"] not in held], wait
