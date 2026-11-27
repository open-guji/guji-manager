"""事件级别：人裁（human）、已放行的 AI 钉（ai）、不算钉（None）。2026-11-26 统一口径（GM4 批量规则，CV0）。

**「算落定」的口径只在本模块定义一处**（2026-11-27 清理计划 1.8）：`event_level`／`counts_as_pin`／`settles_cell`。
cv `open_guji_cv.feedback.events.event_level`、中心库 `events.level` 虚拟列（guji-workspace-data#37，Worker 读时现算的落定条件读它）
与 Worker `pendinglive.ts` 的 `HUMAN_VS` 都是对本模块的**镜像**，改口径先改这里、再同改另三处；
`tests/test_event_levels.py` 用同一张用例矩阵逐条比对四处，已知的分歧登记在 `KNOWN_DIVERGENCES`，多一条少一条都会红。
本模块不经 `_cv` 取 cv 的函数：钉 0.7.x patch 线的执行机也要按同一口径数。

裁定事件的**来源三字段**（`payload.level／by／channel`）见 cv `doc/formats/裁定事件规范.md` §4.1；本模块的 `provenance()` 是
manager 写入点统一取这三个键的入口（现在无写入点在用，2.4 改必填时逐个接）。

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

#: 来源三字段的合法取值（同 cv `events.PROVENANCE_LEVELS／PROVENANCE_CHANNELS`、`guji_feedback_event_v1.schema.json`）。
#: `machine`（规则自动补的）合法但**不算钉**，`event_level` 给 None。
PROVENANCE_LEVELS = ("human", "ai", "machine")
PROVENANCE_CHANNELS = ("console", "web_vote", "opinion", "script", "llm", "vision")

#: 人裁里算「定了这一格」的 `payload.v`（`kind=confirm`、`target.unit=cell`）。`feedback/web_votes.HUMAN_VS` 引用它；
#: Worker `pendinglive.ts` 的 `HUMAN_VS` 是镜像。
SETTLED_VS = ("confirm", "seg_defect", "not_a_char", "damaged", "figure")


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
    if lv == "machine":      # 规则自动补的：不算钉（中心库 events.level 同样给 machine，Worker 只认 human／ai）
        return None
    if g("actor") != "model":
        return "human"
    return "human" if str(g("batch") or "").split("~", 1)[0] in HUMAN_MODEL_BATCHES else "ai"


def counts_as_pin(e) -> bool:
    return event_level(e) is not None


def counts_as_human(e) -> bool:
    return event_level(e) == "human"


def settles_cell(e) -> bool:
    """这条事件算不算**把这一格落定**（网站待审读时现算、后台对账 resolved 都按它）：
    `kind=confirm`、单位是格、`payload.v ∈ SETTLED_VS`、且 `counts_as_pin`。`e` 可以是 Event 或事件 dict。

    注意「落定」不等于「配上了这格」：按身份配格要 `(书, 册, u)` 三元组，u 是册内唯一的，只按 u 配会跨册误配
    （见清理计划 v2 第一节）。本函数只回答**这条事件本身**够不够格，不管它配给哪一格。"""
    g = e.get if isinstance(e, dict) else (lambda k, d=None: getattr(e, k, d))
    if g("kind") != "confirm":
        return False
    t = g("target") or {}
    unit = t.get("unit") if isinstance(t, dict) else getattr(t, "unit", None)
    if unit != "cell":
        return False
    if (g("payload") or {}).get("v") not in SETTLED_VS:
        return False
    return counts_as_pin(e)


def provenance(level: str, by: str, channel: str) -> dict:
    """裁定事件的来源三字段（并进 `payload`）。取值不合法直接 ValueError——写入点用它，不要自己拼。"""
    if level not in PROVENANCE_LEVELS:
        raise ValueError(f"payload.level 须是 {PROVENANCE_LEVELS} 之一，拿到 {level!r}")
    if channel not in PROVENANCE_CHANNELS:
        raise ValueError(f"payload.channel 须是 {PROVENANCE_CHANNELS} 之一，拿到 {channel!r}")
    if not by or not str(by).strip():
        raise ValueError("payload.by 不能为空：写人的账号、模型名或脚本名")
    return {"level": level, "by": str(by), "channel": channel}
