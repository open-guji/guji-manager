# 第二步　自动化流程（pipeline）

多册分批（一般 10 册一批），一轮一轮跑 CV 管线、修切分、补少见字、处理形近字，把人审率压到本书目标线；本批判停后标 **v0.1**、导入 book-text、上网站。
怎么做见 Wiki [第二步-自动化流程](../../wiki/第二步-自动化流程.md)（主文 [迭代流程](../../wiki/自动化流程/迭代流程.md)）。命令前缀 `guji pipeline`（[命令速查](../00-总览/命令速查.md)）。

## 小步

| 小步 | 输入 | 输出 | 命令 | 教程 |
|---|---|---|---|---|
| 2a 跑 CV 管线 | 上一轮各层的修复（cv PR、书仓 `k`、字形库 `g`、册 yaml／钉子／裁定） | 新 ★main 产物包；本轮人审率进后台；待审按 `pending_reason` 归层的派活表；时间账 | `guji pipeline <管线> <册>`、`job precheck／submit／show`、`status`、`rerun`、`products pack／diff`、`round-check`、`close-check`、`iterate` | [跑CV管线](../../wiki/自动化流程/跑CV管线.md) |
| 2b 切分检查与优化 | `seg check／gate` 的结构列清单；下游报回的切分错 | 修好的切分（cv PR、书仓 `k`、册配置、`manual-cells`）；根因台账、本书尺子 | `guji pipeline seg check／gate／premain／pin／pins-stale／ruler` | [切分检查与优化](../../wiki/自动化流程/切分检查与优化.md) |
| 2c 少见字入库、OCR 候选 | L 类待审（`lib_missing`、`lib_sparse_*`、`lib_unrecognized`…）；回库候选 | 字形库快照 `g<N>` 并钉住；回库与库文一致报告 | `guji pipeline review-pages build char_grid`、`triage`、`events route`、`glyph-db snapshot／pin-verify`、`recheck` | [少见字入库与OCR候选](../../wiki/自动化流程/少见字入库与OCR候选.md) |
| 2d 形近字处理 | Z（字组）、N（形近护栏）、V（异体）类待审；反复出现的字对 | 每组判法（刻形模板／CNN、码位归一、书级形近表，或交第三步）；金标；码位口径 | `guji pipeline groups`、`promote mine`、`pair-attr`、`model` | [形近字处理](../../wiki/自动化流程/形近字处理.md) |
| 出 v0.1 | 本批 b–d 判停 | 收口单、R1–R6 验收、book-text 文本线 0.1.0 | `tools/开书/出v01.py`、`guji pipeline close-check --tier rough` | [出v0.1与导入book-text](出v0.1与导入book-text.md) |

人审进库（人裁事件 harvest、落字形库）在本步做（cv 原 Step8 移来）。不用 AI；靠文意才能定的字留给[第三步](../3-文意与知识/)。

## 规格与事实

- [冻结基线与重跑分级](冻结基线与重跑分级.md)：L0–L3；**已出 v0.1 的册默认不整册重跑**，改待审单出裁定事件、`feedback collect` 落 book-text（第零节，用户 11-25 定）
- [出v0.1与导入book-text](出v0.1与导入book-text.md)：判停三问、R1–R6
- 待审原因：[参考/待审原因](../参考/待审原因/)；5a／5b 模型、形近字对归属表：[参考](../参考/)

## 入口条件

- 第一步关口 A 已过。
- 册在中心库、原图在 R2；册 yaml 钉好 `cv_version`、`code`、`corpus`、`glyph_pin`；没跑过的册钉最新 cv 版本。

## 出口

本批判停三问都是「是」（见 [降人审迭代框架](../../wiki/自动化流程/降人审迭代框架.md)），标 v0.1、导入 book-text。人审率目标 <1%（不卡出口，写原因）；自动放行错放目标 0。

## 初期人多、后期人少

| 小步 | 初期人做的 | 换成机器的条件 |
|---|---|---|
| 2b | 看新页型叠图 | 本书尺子覆盖已知根因；`seg gate`／`seg premain` 不挡 |
| 2c | 第一次进库的字人裁 | 自动入库闸：分层盲读 ≥100 格 0 错 |
| 2d | 金标、码位口径、新放行类别上线 | 金标放行子集 0 错，独立盲读抽样 0 错 |

用户一轮花的时间超过 30 分钟，说明上游预选或金标没做好。

## 谁做

各书线掌握节奏（殿本 ZM、全唐文 QTW、史記 SJ）；GM2 流程与工具（原 A31）；CV2 切分、CV3 字库、CV4 判定字（形近字）；对位原 A34 已归档，暂归 GM2。派活表见 [跑CV管线](../../wiki/自动化流程/跑CV管线.md)。
