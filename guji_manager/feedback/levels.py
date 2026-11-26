"""事件级别：人裁（human）、已放行的 AI 钉（ai）、不算钉（None）。2026-11-26 统一口径（GM4 批量规则，CV0）。

与 cv `open_guji_cv.feedback.events.event_level`、中心库 `events.level` 虚拟列（guji-workspace-data#37）同一张表，
改要三处一起改。本模块不经 `_cv` 取 cv 的函数：钉 0.7.x patch 线的执行机也要按同一口径数。

- `counts_as_pin`（human 或 ai）：**会改产物、会把格藏出待审队列的读者都用它**（字形库入库、已裁、对勘状态、
  近似字、插图、冻结计数、人裁冲突）。与 11-26 前 cv 的 `counts_as_human` 同一集合，行为不变。
- `counts_as_human`（只认 human）：统计、评测（在线准确率真值、rough_bench 标签）用，AI 钉不混进「人裁」。
"""

from __future__ import annotations

#: 「模型的判断」类来源（同 cv `events.MODEL_JUDGMENT_SOURCES`）：不算钉。
MODEL_JUDGMENT_SOURCES = frozenset({"vision", "llm", "knn_infer", "auto"})

#: `actor="model"` 而没写 `payload.level` 的老事件里，人授意的重写／重绑（字是人定的）：按批次名 `~` 前的部分认。
#: 用户 11-25 定「尽量批量处理不问我」，GM4 归类见 ai-team domain/GM/GM4/待审与裁定-数据表与工作流整理方案-2026-11-25.md §七。
HUMAN_MODEL_BATCHES = frozenset({
    "H-mojibake-fix-20260927", "r74-v01", "r77-重绑", "r79-v01", "SJ-ry-rebind-1120", "SJ-sheldon-1123",
    "SJ-L1取消归一-human24", "SJ-v02-rebind-1124", "SJ-歲暫歸一-1125",
})
EVENT_LEVELS = ("human", "ai")


def event_level(e) -> str | None:
    """先认 `payload.level`；没有的：`actor` 不是 model 的算 human，是 model 的批次在 `HUMAN_MODEL_BATCHES` 算 human、
    其余算 ai。看图结论、文意裁定、模型判断来源的给 None。`e` 可以是 Event，也可以是事件 dict。"""
    g = e.get if isinstance(e, dict) else (lambda k, d=None: getattr(e, k, d))
    if g("kind") in ("vision_check", "ctx_ruling"):
        return None
    p = g("payload") or {}
    if p.get("source") in MODEL_JUDGMENT_SOURCES:
        return None
    lv = p.get("level")
    if lv in EVENT_LEVELS:
        return lv
    if g("actor") != "model":
        return "human"
    return "human" if str(g("batch") or "").split("~", 1)[0] in HUMAN_MODEL_BATCHES else "ai"


def counts_as_pin(e) -> bool:
    return event_level(e) is not None


def counts_as_human(e) -> bool:
    return event_level(e) == "human"
