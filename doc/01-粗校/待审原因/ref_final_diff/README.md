# P02 `ref_final_diff`：定字与参校本不同

> 2026-11-06 由 `ref_mismatch`（和参校本不一致）改名，旧名数据照认。

> [待审原因总览](../README.md)

**一句话**：对位时和参校本一致（或按坐标对位），最后定字成了别的字，可能是真异文。

**在哪一步判出来**：先在 Step6 `align_ref` 不是 replace 段（是 `equal`，或走坐标对位），然后看最后定字：`context_decide`（文意）→ `seed_admit`（各放行通道、字组、护栏）定出的字≠参校字，就是 P02。常见疑问码 `context_vs_ref`、`iron_vs_ref`、`signal_conflict`。

**和 P01 的区别**：P01 是识别字在对位时就不同；P02 是对位时相同、后面定字才不同，见 [P01](../ref_ocr_diff/README.md)。

## 定义与判定

- 大类：与参校本不一致（P）；判定顺序 priority 62（小的先判，第一条命中即主原因）。
- 判定依据：其余机器字≠整理本（context_vs_ref / iron_vs_ref / signal_conflict 等）
- 去向：大模型统一过一遍（只收 high，其余回人审）（route `llm`）；最终谁看：大模型先过，只收 high，其余回人；网页卡片 `pick`。
- 负责改算法／数据：A24。
- 旧字段对应：{"cause": ["E", "I"], "cls": ["ref_conflict", "other"], "taxonomy": ["R1"], "v2": "P 机器字≠整理本"}

## 常见成因

对位相同，但文意、字组等后面的步骤把字定成了别的（context_vs_ref、iron_vs_ref 等），可能是真异文，也可能是后面的步骤改错了。

## 怎么处理

1. 先过 L1 规则，再 L2 文意裁；判不了人审。
2. 真异文保留刻本字。

## 回流与防再犯

真异文记进交接单。

## 不要做

不要默认按参校本改。

## 现状（2026-11-06，★main 包口径，正文页）

四库总目 374、史记 68、全唐文 0 格。来源 ai-team `domain/CV/质检/三书待审原因统计/`。
