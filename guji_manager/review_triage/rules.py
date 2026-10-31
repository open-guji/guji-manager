"""快审分流：每个候选格落进 skip / withdraw / pass / review 之一。

用户在史記第 2 轮定下的规则（2026-10-31，Sheldon）：

| 去向 | 条件 | 含义 |
|---|---|---|
| skip     | 列首、列尾、双行小注格 | 最常切到版框、小字格挤，不进快审 |
| skip     | 参校字为空或不是汉字（私用区、外文符号等） | 没有可比的参考答案 |
| skip     | 参校字是 己已巳、日曰 | 这几个字靠形分不清，要靠文意，走字组流程 |
| pass     | OCR＋几何模型的「会被拦」概率 < 阈值 | 直接放行，不上页 |
| withdraw | OCR 首选字 ≠ 参校字 | 多半是切分有问题，「确定不匹配」，撤下不审，这轮不进字形库 |
| review   | 其余（OCR 认成参校字、但模型没把握） | 上页给人审 |

先判 pass 再判 withdraw：模型已经有把握的格，OCR 首选不同（异体、生僻字）也放行。
"""
from __future__ import annotations

import unicodedata

from .cells import COL_LEN, skip_reason

CONTEXT_GROUPS = set("己已巳日曰")


def is_han(ch: str | None) -> bool:
    if not ch or len(ch) != 1:
        return False
    try:
        return unicodedata.name(ch).startswith("CJK ")
    except ValueError:          # 私用区等没有名字
        return False


def route(cell_id: str, ref: str | None, p_bad: float | None, ocr: str | None,
          threshold: float = 0.02, col_len: int | None = COL_LEN) -> tuple[str, str]:
    """返回 (去向, 原因)。p_bad / ocr 为 None 表示还没打分（只判 skip）。"""
    pos = skip_reason(cell_id, col_len)
    if pos:
        return "skip", pos
    if not is_han(ref):
        return "skip", "ref_not_han"
    if ref in CONTEXT_GROUPS:
        return "skip", "context_group"
    if p_bad is not None and p_bad < threshold:
        return "pass", "model"
    if ocr is not None and ocr != ref:
        return "withdraw", "ocr_mismatch"
    return "review", "uncertain"
