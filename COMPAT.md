# 兼容矩阵

| guji-manager | 支持的 pipeline 契约 | 对应 open-guji-cv |
|---|---|---|
| 0.0.1 | v1 | ≥ 0.5.27（含 `guji version --json`、manifest `contract_version`；2026-10-27 起 dev） |

契约正文：open-guji-cv `doc/契约.md`。pipeline 讲的契约超出范围，`guji-manager check` 与所有跑批入口拒跑。
旧版 pipeline（没有 `version` 子命令）按契约 0 处理，不支持。
