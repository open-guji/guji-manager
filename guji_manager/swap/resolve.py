"""重切发布批：同一块图上，谁覆盖谁（文本修订全流程总分析第五节；sheldon 2026-11-09 定）。

优先级（高→低）：新人裁（明确推翻） > 旧人裁（绑定 valid／rebound） > 机器新结果 > 现行文本里的机器旧字。
手改字先补录成人裁事件，补录后并入「人裁」，这里不单列一级。机器只能挑战人，不能覆盖人。

本模块是纯函数，不读写文件。调用方（``swap release``）先用对照表和绑定表把每个新格的事实收齐：

- ``cur``：现行发布文本该块图的字（缺格为 None）
- ``new``：新包放行的字（新包退回待审写 ``□``；该块图在新包里没有格写 None）
- ``human``：绑定有效的最新人裁字（没有为 None）
- ``human_invalid``：有旧人裁但绑定 review／void，不可采信（True 时 ``human`` 应为 None）
- ``flaw``：机器错字检测命中（相邻重复字、字丢失等）
- ``new_pending``：新包里这块图是待审。**待审时 ``new`` 填首选字**（sheldon 11-09 定：book-text 不因待审改成 □，
  待审≠阙文）；没有首选字填 None／``""``。``new_lacuna``：新包认定是真阙文（审过定阙），此时 ``new`` 填 ``□``。
  □ 只表示真阙文。
  **待审且首选字≠现行字（现行有字）时文本不动**（sheldon 11-10 定）：等人裁定了确是另一字再改，少改 book-text 提交；
  现行是 □／缺格时才写首选字。
- ``new_not_char``：新包认定这块图**不是字**（cv#1358 起 row_segment 给列端框线格打格级旗 ``frame_line``，
  该格不进 char 产物）。无人裁→删格放行（机器改字默认放行），不当「字丢失」；有人裁→人裁优先、报用户。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

BLANK = "□"

# kind
SAME = "same"                         # 无变化
HUMAN_KEEP = "human_keep"             # 人裁与现行一致，保留
HUMAN_RESTORE = "human_restore"       # 现行不是人裁字，恢复为人裁字
PROTECTED_CONFLICT = "protected_conflict"   # 新包与人裁不一致：保留人裁，逐格报用户
HUMAN_INVALID = "human_invalid"       # 旧人裁失效（图块变了）：不采信，进复审单
NEW_ADMIT = "new_admit"               # 现行 □／缺格，新包有字
MACHINE_CHANGE = "machine_change"     # 无人裁，机器改字：默认放行
RETURN_TO_BLANK = "return_to_blank"   # 现行有字，新包认定真阙文（□）：不改文本，进复审单
PENDING_SAME = "pending_same"         # 新包待审但首选字与现行一致：文本不动，只多一张待审单
PENDING_KEEP = "pending_keep"         # 新包待审、首选字≠现行字：文本不动，等人裁定了再改（sheldon 11-10 定，少改 book-text 提交）
PENDING_NO_CHOICE = "pending_no_choice"  # 新包待审且没有首选字：文本保持现行，待审单
NOT_CHAR = "not_char"                 # 新包认定不是字（frame_line）、无人裁：删格放行
MACHINE_FLAW = "machine_flaw"         # 机器错字：回退现行字
REMOVED = "removed"                   # 新包里该块图没有格：结构变化，交对照表处理

KEEP, ADOPT, REVIEW, REVERT = "keep", "adopt", "review", "revert"


@dataclass(frozen=True)
class Decision:
    kind: str
    action: str          # keep 保持现行｜adopt 采纳新包字｜review 进复审单（文本保持 result）｜revert 回退现行字
    result: str | None   # 落进文本的字
    auto: bool           # False＝必须报用户（保护格冲突）
    note: str = ""
    to_review: bool = False   # 另外要出一张待审单（文本不因此改动）


def _blank(c: str | None) -> bool:
    return c is None or c == BLANK


def resolve(cur: str | None, new: str | None, human: str | None = None, *,
            human_invalid: bool = False, flaw: bool = False,
            new_pending: bool = False, new_lacuna: bool = False,
            new_not_char: bool = False, same: Callable[[str | None, str | None], bool] | None = None) -> Decision:
    """``same(a, b)``：同字判定（``charnorm.CharNorm.same``），缺省字面 ``==``。归一后同字不算冲突、不算机器改字、不进复审
    （审视文档 §二-4：别／別 不能被当成「机器推翻人裁」）。"""
    eq = same or (lambda a, b: a == b)
    if new_not_char:
        if human is not None:
            return Decision(PROTECTED_CONFLICT, REVIEW, human, False, f"新包认定不是字（frame_line），人裁「{human}」，保留人裁")
        if human_invalid:
            return Decision(HUMAN_INVALID, REVIEW, cur, True, "新包认定不是字，旧人裁绑定失效，进复审单")
        if _blank(cur):
            return Decision(SAME, KEEP, None, True, "新包认定不是字，现行也没有字")
        return Decision(NOT_CHAR, ADOPT, None, True, f"新包认定不是字（frame_line），删去现行「{cur}」")
    if human is not None:
        if new is not None and not eq(new, human) and new != BLANK and not new_pending:
            return Decision(PROTECTED_CONFLICT, REVIEW, human, False, f"新包「{new}」≠人裁「{human}」，保留人裁")
        if eq(cur, human):
            return Decision(HUMAN_KEEP, KEEP, human, True)
        return Decision(HUMAN_RESTORE, ADOPT, human, True, f"现行「{cur}」→人裁「{human}」")
    if human_invalid:
        # 旧人裁不可采信：文本保持现行（缺格才取新包），旧裁字只作复审参考
        return Decision(HUMAN_INVALID, REVIEW, cur if cur is not None else new, True, "旧人裁绑定失效，进复审单")
    if new_pending and not new_lacuna:
        if not new or new == BLANK:
            return Decision(PENDING_NO_CHOICE, KEEP, cur, True, "新包待审且无首选字，文本保持现行，出待审单", True)
        if eq(cur, new):
            return Decision(PENDING_SAME, KEEP, cur, True, "待审但首选字与现行一致，文本不动，只出待审单", True)
        if not _blank(cur):
            # 现行有字、待审首选字不同：文本不动，等人裁定了确是另一字再改（sheldon 11-10 定）
            return Decision(PENDING_KEEP, KEEP, cur, True, f"待审，首选字「{new}」≠现行「{cur}」，文本不动，人裁后再改", True)
        # 现行 □／缺格：写首选字（走常规 NEW_ADMIT），另出待审单
        d = resolve(cur, new, None, flaw=flaw, same=same)
        return Decision(d.kind, d.action, d.result, d.auto, d.note, True)
    if new is None:
        return Decision(REMOVED, KEEP, cur, True, "新包无对应格")
    if eq(cur, new):
        return Decision(SAME, KEEP, cur, True)
    if flaw:
        return Decision(MACHINE_FLAW, REVERT, cur, True, "机器错字检测命中，回退现行字")
    if _blank(cur):
        if new == BLANK:
            return Decision(SAME, KEEP, cur, True)
        return Decision(NEW_ADMIT, ADOPT, new, True)
    if new == BLANK:
        return Decision(RETURN_TO_BLANK, REVIEW, cur, True, "新包退回待审，文本保持现字，人裁后定")
    return Decision(MACHINE_CHANGE, ADOPT, new, True, f"机器改字「{cur}」→「{new}」，无人裁，默认放行")


def detect_flaws(cur_seq: list[str | None], new_seq: list[str | None],
                 not_char: set[int] | frozenset[int] = frozenset()) -> set[int]:
    """逐位对照两个等长字序列（按对照表配好的块图），返回机器错字的下标。

    规则：新字改了现行字，且与相邻新字相同（改出了重复字）；新字丢失（现行有字、新为空串）。
    ``not_char``：新包明确认定不是字（frame_line）的下标，不算字丢失。
    """
    n = min(len(cur_seq), len(new_seq))
    bad: set[int] = set()
    for i in range(n):
        c, w = cur_seq[i], new_seq[i]
        if c and w == "" and i not in not_char:
            bad.add(i)
        if w and w != BLANK and w != c:
            for j in (i - 1, i + 1):
                if 0 <= j < n and new_seq[j] == w:
                    bad.add(i)
    return bad
