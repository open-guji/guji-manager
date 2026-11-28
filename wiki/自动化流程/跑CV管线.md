# 2a 跑 CV 管线

> 属于 [第二步 自动化流程](第二步-自动化流程)。

每轮统一冻结、发版、重跑一次，交任务库在执行机上跑，取包逐格比对 main，过切分不回退闸和标 main 前硬检查，标 main、收尾、出分析派活。

**输入**：上一轮各层攒下的修复（cv PR、书仓 `code/` 新 `k`、字形库新 `g`、册 yaml／钉子／裁定）。
**输出**：新的 ★main 产物包；本轮人审率与轮次进后台；待审按 `pending_reason` 归层的派活表；时间账。
**命令**：`guji pipeline job submit／show／precheck／stats`、`guji pipeline status`（cv）、`guji pipeline rerun --stale`、`guji pipeline products pack／diff`、`guji pipeline cache warm`、`guji pipeline round-check`、`guji pipeline close-check`、`guji pipeline iterate`、`guji pipeline pending-stats`、`guji pipeline exp`、`guji pipeline perf`。

一轮的十个固定动作以 [迭代流程 第三节](迭代流程#三一轮的固定动作每轮都一样) 为准。

## 实测与常踩（三本书 11-17～11-20 的时间账）

- **排队比运行长**：整批交单后排队中位 44–163 分，运行中位 13–38 分；一轮从交单到出齐 1.4–8.5 小时。瓶颈在执行方调度，不在各书流程。
- **第二大耗时是交单后返工**，三类都能在交单前挡住：册 yaml 的钉子压过 book_defaults（史記 r56／r75、殿本 r12g24b）、起跑步写错（全唐文 a3 撤 44 单）、交单后别的线又推修复（史記 r77、殿本 r11g23）。所以交单前一定跑 `guji pipeline job precheck`，并在本书线程里宣布截单时刻。
- **只重跑受影响的页是缺省做法**（用户 11-20 定）：落人裁、AI 裁定只影响几页时，不要整册进队列（殿本 vol32 改 3 格，4 分 44 秒里只有 1 分是重跑）。
- **静默出错比慢更贵**：新包把旧 main 已放行的字改成别的字、人裁掉格（unanchored）都不报错，要在第 5 步逐格比对和收轮检查里主动看「旧放行、新改字」与人裁掉格数。
- 原始数字与提速待办：ai-team [各书换单汇总](https://github.com/open-guji-core/ai-team/blob/main/domain/CV/粗校/换单各书汇总-2026-11-17.md)、[流程慢痛点汇总](https://github.com/open-guji-core/ai-team/blob/main/domain/CV/粗校/流程慢-痛点汇总-1120.md)。

## 相关页面

- [重跑需求与执行规范](重跑需求与执行规范)：任务库怎么交单、spec 写法、谁执行、结果在哪
- [两档轮与交单检查](两档轮与交单检查)：两档轮（D 轮、S 轮）与交单前逐册核钉子
- [受控重跑方法论](受控重跑方法论)：先算影响面再决定跑什么、跑多大
- [冻结基线与重跑分级](https://github.com/open-guji/guji-manager/blob/dev/doc/2-自动化流程/冻结基线与重跑分级.md)：冻结基线与 L0–L3 重跑分级
- [收轮检查单](收轮检查单)：标 main 前每册的 seg check×2→gate→diff→premain→待审分层，一条任务单做完
- [轮报告与验收工具](轮报告与验收工具)：轮报告、金标、抽检台账、杠杆排序命令

## 什么时候重跑、跑多大

- **不是每次有新版本都重跑。** 小修复攒一批再统一跑；预期收益很小的不单独跑。
- 改动只落在 seed_admit（规则、字组、码位、文意表）→ 只从 seed_admit 重落；动了切分或更早的步 → 只重跑受影响页；`guji pipeline status` 无过期步 → 不跑。
- 需求单写清：为什么跑、范围、预计收益、起点步（和 `guji pipeline status` 对得上）、对比基线。
- **新册首跑**（没有 main 的册）跑完自动标 main。
- 重跑完默认直接标 main、推库；标 main 后钩子自动重出线上单。有 `.punct.json` 的册或旧单已有票的只提示，交第四步。
- 分析一律用上线那一版的包（`guji pipeline products pack list／fetch`，按 cv 版本和上线时间对上），否则格号对不上。
- 换图源、整套迁移之类的大批量重跑见 [1.0后的反馈](1.0后的反馈) 与 [重跑需求与执行规范](重跑需求与执行规范)。

## 派活：哪类问题交给谁

| 问题 | 交给 | 交什么 | 对方回什么 |
|---|---|---|---|
| 字形库缺字、生僻字识别、模板 | A23 | 字清单、册页格号、整理本字 | 补库／5b 改进，PR 号 |
| 形近字组、文意表缺、护栏 N | A24 | 字组／字对表、带图样例 | cv PR、文意表推库 |
| 对位问题 | A34（或 A23） | 页／列样例、错行类型 | 对位算法改动 |
| 切分系统错 | A22 | 页／列清单、看图结论 | cv 修复 PR |
| 要用户定的码位 | 用户 | 带图字对表 | `codepoints.yaml` 决定 |

发现系统性识别错误：记样例反馈 A22（切分）或 A34（对位／迭代），不要逐个手补。
