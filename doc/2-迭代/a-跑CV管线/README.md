# 2a 跑 CV 管线

> 第二步「迭代」的小步。总览见 [第二步 README](../README.md)。

每轮统一冻结、发版、重跑一次，交任务库在执行机上跑，取包逐格比对 main，过切分不回退闸和标 main 前硬检查，标 main、收尾、出分析派活。

**输入**：上一轮各层攒下的修复（cv PR、书仓 `code/` 新 `k`、字形库新 `g`、册 yaml／钉子／裁定）。
**输出**：新的 ★main 产物包；本轮人审率与轮次进后台；待审按 `pending_reason` 归层的派活表；时间账。
**命令**：`guji job submit／show／precheck／stats`、`guji status`（cv）、`guji rerun --stale`、`guji products pack／diff`、`guji cache warm`、`guji round-check`、`guji close-check`、`guji iterate`、`guji pending-stats`、`guji exp`、`guji perf`。

一轮的十个固定动作以 [迭代流程 第三节](../迭代流程.md#三一轮的固定动作每轮都一样) 为准。

## 实测与常踩（三本书 11-17～11-20 的时间账）

- **排队比运行长**：整批交单后排队中位 44–163 分，运行中位 13–38 分；一轮从交单到出齐 1.4–8.5 小时。瓶颈在执行方调度，不在各书流程。
- **第二大耗时是交单后返工**，三类都能在交单前挡住：册 yaml 的钉子压过 book_defaults（史記 r56／r75、殿本 r12g24b）、起跑步写错（全唐文 a3 撤 44 单）、交单后别的线又推修复（史記 r77、殿本 r11g23）。所以交单前一定跑 `guji job precheck`，并在本书线程里宣布截单时刻。
- **只重跑受影响的页是缺省做法**（用户 11-20 定）：落人裁、AI 裁定只影响几页时，不要整册进队列（殿本 vol32 改 3 格，4 分 44 秒里只有 1 分是重跑）。
- **静默出错比慢更贵**：新包把旧 main 已放行的字改成别的字、人裁掉格（unanchored）都不报错，要在第 5 步逐格比对和收轮检查里主动看「旧放行、新改字」与人裁掉格数。
- 原始数字与提速待办：ai-team [各书换单汇总](https://github.com/open-guji-core/ai-team/blob/main/domain/CV/粗校/换单各书汇总-2026-11-17.md)、[流程慢痛点汇总](https://github.com/open-guji-core/ai-team/blob/main/domain/CV/粗校/流程慢-痛点汇总-1120.md)。

## 本目录

- [重跑需求与执行规范](重跑需求与执行规范.md)：任务库怎么交单、spec 写法、谁执行、结果在哪
- [两档轮与交单检查](两档轮与交单检查.md)：两档轮（D 轮、S 轮）与交单前逐册核钉子
- [受控重跑方法论](受控重跑方法论.md)：先算影响面再决定跑什么、跑多大
- [冻结基线与重跑分级](冻结基线与重跑分级.md)：冻结基线与 L0–L3 重跑分级
- [收轮检查单](收轮检查单.md)：标 main 前每册的 seg check×2→gate→diff→premain→待审分层，一条任务单做完
- [轮报告与验收工具](轮报告与验收工具.md)：轮报告、金标、抽检台账、杠杆排序命令
