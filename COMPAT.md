# 兼容矩阵

| guji-manager | 支持的 pipeline 契约 | 对应 open-guji-cv |
|---|---|---|
| 0.6.0 | v1 | 建议 ≥ 0.9.0；**0.7.x／0.8.x 也能用**（只硬核契约 v1）。差别：`guji <步> <命令>` 步骤前缀要 cv ≥ 0.9.0 的 `route` 钩子，旧 cv 上 `start`／`text`／`feedback`／`output` 前缀照样能用（manager 分组子命令兜底），**`pipeline` 前缀不行**，要写老写法（`guji job …`、`guji book …`、`guji collate …`）；cv ≤ 0.8 自带的原 Step9／`guji export` 还在，以 manager `guji output` 为准 |
| 0.0.1 | v1 | ≥ 0.5.27（含 `guji version --json`、manifest `contract_version`；2026-10-27 起 dev） |

契约正文：open-guji-cv `doc/参考/契约.md`。pipeline 讲的契约超出范围，`guji-manager check` 与所有跑批入口拒跑。
旧版 pipeline（没有 `version` 子命令）按契约 0 处理，不支持。
