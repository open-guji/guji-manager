"""落票策略：一格上的网站人审票，够不够自动落成人裁事件、写进 book-text（GM4，2026-11-23，用户定）。

现在只有用户本人在审，缺省策略 ``auto``＝有票就落。将来按审阅人的会员身份分流：高等级审阅人一票即定，
普通会员要多人投一致才落；没到门槛的格不落、不结案（条目仍开着，票留在收件箱），报告里记为「等多人投票」。

接口只有一个：``policy.decide(cell, votes) -> Decision``。``votes`` 是这一格上经 ``latest_votes`` 去重后的票
（每人一票，带 ``voter``、``choice``、``char``）；``Decision.land`` 为真才进 ``cellvotes draft`` 的分流。
策略不管票内容是否冲突、格位对不对——那是 ``triage`` 的闸（意见不一致、推翻旧裁、格位变了照旧挂起，
属于「特殊需要分析／待定」，不自动落）。

选策略：``--policy auto``（缺省，或环境变量 ``GUJI_LANDING_POLICY``）、``--policy quorum:2``（要 2 个人投同一结论）。
会员身份：``GUJI_REVIEWER_TIERS`` 指向 JSON ``{"<voter>": "<等级>"}``，没列的人是 ``member``；
``quorum`` 里等级在 ``solo`` 集合（缺省 ``owner``、``editor``）的人一票即定。网站接会员体系后，换成读会员接口即可，
只改 ``reviewer_tier``。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TIER = "member"
SOLO_TIERS = ("owner", "editor")


@dataclass(frozen=True)
class Decision:
    land: bool
    why: str = ""


def reviewer_tier(voter: str) -> str:
    """审阅人的会员等级。现在从 ``GUJI_REVIEWER_TIERS`` 指的 JSON 读；将来换成网站会员接口。"""
    p = os.environ.get("GUJI_REVIEWER_TIERS")
    if p and Path(p).is_file():
        try:
            return str(json.loads(Path(p).read_text(encoding="utf-8")).get(voter) or DEFAULT_TIER)
        except (OSError, ValueError):
            pass
    return DEFAULT_TIER


class AutoPolicy:
    """缺省：有票就落（单人审阅期）。"""
    name = "auto"

    def decide(self, cell: str, votes: list[dict]) -> Decision:
        return Decision(True) if votes else Decision(False, "无票")


class QuorumPolicy:
    """高等级（``solo``）一票即定；否则要至少 ``need`` 个人投了同一结论（选项＋字）才落。"""

    def __init__(self, need: int = 2, solo: tuple[str, ...] = SOLO_TIERS, tier=reviewer_tier):
        self.need, self.solo, self.tier = need, tuple(solo), tier
        self.name = f"quorum:{need}"

    def decide(self, cell: str, votes: list[dict]) -> Decision:
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


def get_policy(spec: str | None = None):
    spec = (spec or os.environ.get("GUJI_LANDING_POLICY") or "auto").strip()
    if spec == "auto":
        return AutoPolicy()
    if spec.startswith("quorum"):
        _, _, n = spec.partition(":")
        return QuorumPolicy(int(n) if n else 2)
    raise SystemExit(f"--policy 只认 auto 或 quorum[:N]：{spec}")


def apply_policy(policy, votes: list[dict]) -> tuple[list[dict], list[tuple[str, str, list[dict]]]]:
    """按格分组过策略。返回 (放行的票, [(格, 原因, 票)…] 等多人的)。"""
    by: dict[str, list[dict]] = {}
    for v in votes:
        by.setdefault(v["a"], []).append(v)
    wait = []
    for a, vs in by.items():
        d = policy.decide(a, vs)
        if not d.land:
            wait.append((a, d.why, vs))
    held = {a for a, _, _ in wait}
    return [v for v in votes if v["a"] not in held], wait
