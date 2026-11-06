# S04 `seg_defect`：切坏格

> [待审原因总览](../README.md)

**一句话**：这一格切得不完整，机器认不出字；请看书影，把字直接写进框里

## 定义与判定

- 大类：切分位置（S）；判定顺序 priority 10（小的先判，第一条命中即主原因）。
- 判定依据：人或闸标了切坏格（confirm v=seg_defect，或单上 cls=seg_defect）；史記夹注两行分法不均、按整理本切的格（doubt 码 jiazhu_uneven，cv#1011）也归这里，细分 jiazhu_uneven
- 去向：一定人审（route `human`）；最终谁看：人；网页卡片 `free`。
- 负责改算法／数据：A22。
- 旧字段对应：{"cls": ["seg_defect"]}

## 常见成因

格本身切坏：笔画被切掉、两字粘连、框线残留；史記夹注两行分法不均（`jiazhu_uneven`）也归这里。同字对照自检（`seg_selfcheck`）带框重档会补进来。

## 怎么处理

1. 人审页直接看书影录字（卡片可自由录字）。
2. 同类成片出现时报 A22 修切分（cell_shrink、jiazhu_step 等），而不是一格一格录。
3. 细分看 `seg_kind`：merged／clipped／bleed／frame_residue／jiazhu_uneven。

## 回流与防再犯

切分修了要回看这些格是否自然消失；带框格清框、不进字库只管重档。

## 不要做

切坏的字块不要进字形库。

## 现状（2026-11-06，★main 包口径，正文页）

四库总目 0、史记 20、全唐文 0 格。来源 ai-team `domain/CV/质检/三书待审原因统计/`。
