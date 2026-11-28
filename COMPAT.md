# 兼容矩阵

| guji-manager | 支持的 pipeline 契约 | 对应 open-guji-cv |
|---|---|---|
| 0.6.22–0.6.23 | v1 | 同 0.6.9（建议 ≥ 0.9.0，**下限不因 W1 提高**）。W1（11-25）起只有新册钉 cv 0.9.x（全唐文 031 往后 0.9.4＋底库 b35）；已出 v0.1 的书（殿本、史記、脉经、全唐文 001–030）留在各自 0.7.x／0.9.2 patch 线照常用。manager 读 0.9.2 起切字五小步的产物布局，新旧步都认（#1001）。 |
| 0.6.12 | v1 | 同 0.6.9。 |
| 0.6.11 | v1 | 同 0.6.9。 |
| 0.6.10 | v1 | 同 0.6.9。 |
| 0.6.9 | v1 | 同 0.6.0（建议 ≥ 0.9.0，0.7.x／0.8.x 也能用）。字格永久编号 u：manager 侧写 u、按 u 认票／条目不依赖 cv 版本；cv 侧 seed_admit 按 u 查裁定（`ruling_by_u`，缺省关）、`RulingStore.put(u=)` 要 cv 带 T3 的版本（dev 线 #1848 起、殿本 patch 线 v0.7.102 起），旧 cv 上 collect 重键不写 u、seed_admit 照旧按格号 |
| 0.6.0 | v1 | 建议 ≥ 0.9.0；**0.7.x／0.8.x 也能用**（只硬核契约 v1）。差别：`guji <步> <命令>` 步骤前缀要 cv ≥ 0.9.0 的 `route` 钩子，旧 cv 上 `start`／`text`／`feedback`／`output` 前缀照样能用（manager 分组子命令兜底），**`pipeline` 前缀不行**，要写老写法（`guji job …`、`guji book …`、`guji collate …`）；cv ≤ 0.8 自带的原 Step9／`guji export` 还在，以 manager `guji output` 为准 |
| 0.0.1 | v1 | ≥ 0.5.27（含 `guji version --json`、manifest `contract_version`；2026-10-27 起 dev） |

契约正文：open-guji-cv `doc/参考/契约.md`。pipeline 讲的契约超出范围，`guji-manager check` 与所有跑批入口拒跑。
旧版 pipeline（没有 `version` 子命令）按契约 0 处理，不支持。
