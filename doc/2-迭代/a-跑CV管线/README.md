# 2a 跑 CV 管线

> 第二步「迭代」的小步。总览见 [第二步 README](../README.md)。

每轮统一冻结、发版、重跑一次，交任务库在执行机上跑，取包逐格比对 main，过切分不回退闸和标 main 前硬检查，标 main、收尾、出分析派活。

**输入**：上一轮各层攒下的修复（cv PR、书仓 `code/` 新 `k`、字形库新 `g`、册 yaml／钉子／裁定）。
**输出**：新的 ★main 产物包；本轮人审率与轮次进后台；待审按 `pending_reason` 归层的派活表；时间账。
**命令**：`guji job submit／show／precheck／stats`、`guji status`（cv）、`guji rerun --stale`、`guji products pack／diff`、`guji cache warm`、`guji round-check`、`guji close-check`、`guji iterate`、`guji pending-stats`、`guji exp`、`guji perf`。

一轮的十个固定动作以 [迭代流程 第三节](../迭代流程.md#三一轮的固定动作每轮都一样) 为准。

## 本目录

- [重跑需求与执行规范](重跑需求与执行规范.md)：任务库怎么交单、spec 写法、谁执行、结果在哪
- [两档轮与交单检查](两档轮与交单检查.md)：两档轮（D 轮、S 轮）与交单前逐册核钉子
- [受控重跑方法论](受控重跑方法论.md)：先算影响面再决定跑什么、跑多大
- [冻结基线与重跑分级](冻结基线与重跑分级.md)：冻结基线与 L0–L3 重跑分级
- [收轮检查单](收轮检查单.md)：标 main 前每册的 seg check×2→gate→diff→premain→待审分层，一条任务单做完
- [轮报告与验收工具](轮报告与验收工具.md)：轮报告、金标、抽检台账、杠杆排序命令
