# 第一步　新书启动（start）

从一个 book ID 到先行册（2–3 册）能整册跑、能分批迭代。下一步：[第二步 自动化流程](../2-自动化流程/)。
怎么做见 Wiki [第一步-新书启动](../../wiki/第一步-新书启动.md)。命令前缀 `guji start`（[命令速查](../00-总览/命令速查.md)）。

## 小步

| 小步 | 输入 | 输出 | 命令 | 教程 |
|---|---|---|---|---|
| 1a 元数据与资源 | book ID、已知资源 | book-index 条目；原图进 R2 与页表；国内书影（压缩版）进 COS `srcbw` 并记账；整理本进中心库 `corpus/`；工作区仓、书仓 `code/`；册进中心库 | `guji start new`（新书仓初始文件）、`guji start source`（含 `cos-tier`）、`guji start corpus init`、`guji start code release`、`guji db init／push` | [元数据与资源](../../wiki/新书启动/元数据与资源.md) |
| 1b 页面分析与参数 | 原图、整理本 | 版式档案（工作区 README）；页型声明；套书 `seg_set`；册 yaml 与书级开关；开书体检单、目标人审率 | `guji start pagekinds`、`guji start suggest`、`guji pipeline binarize／calibrate／survey`、`guji pipeline pending-stats` | [页面分析与参数](../../wiki/新书启动/页面分析与参数.md) |
| 1c 选页试运行 | 册配置、页型、套书 | dev_set 试跑叠图；整理本页钉位；借库首跑；首批字形入库并钉 `glyph_pin` | `guji start source pull`、`guji pipeline <管线> <册> --pages dev_set --no-pack`、`guji pipeline product overlay`、`guji pipeline seg check`、`guji pipeline triage`、`guji pipeline review-pages` | [选页试运行](../../wiki/新书启动/选页试运行.md) |

册配置字段见 [册配置](../参考/册配置.md)；钉子与产物包见 [产物包与版本钉](../参考/产物包与版本钉.md)。

## 入口条件

- 用户定了书和版本（多个扫描本选善本，理由写进[案例](../案例/)）。
- 有 book-index 写权限、R2 写令牌（[环境与令牌](../00-总览/环境与令牌.md)）。
- 工作区仓已在 `guji-workspace` 组织下建好，组织装了 Claude 的 GitHub App。云会话建不了（组织级接口 403），用 ai-team `process/repo_create.py`（relay `POST /repo`）建；建好后在克隆目录跑 `guji start new <书id> --title …` 一次出齐 workspace.yaml、.gitignore、README、开书进度.yaml、开书经验.md、layout_profile.yaml、实验记录/、日志.md、tools/（已有文件不覆盖）。

## 出口（关口 A，会话自判）

| 小步 | 标志 | 怎么核 |
|---|---|---|
| 1a | book-index 有 Work／Book，Book 只挂一个最新原图资源 | `check_schema.py`、`check_v2.py` 过 |
| 1a | 原图在 R2，页表页数对，对开拆页核对图看过 | `guji start source commons … --dry-run` |
| 1a | 国内书影已压缩上 COS：每册账在、对象数＝源图数、抽页 IoU ≥0.9 | `guji start source cos-check <书id> <册>`（close-check 第 15 项同） |
| 1a | 有逐列整理本，或记下「没有」 | 中心库 `corpus/` |
| 1a | 册在中心库 | `guji db status`：behind 0、unpushed [] |
| 1b | 版式档案写好；每个新页型有叠图给用户看过（只告知） | `guji start pagekinds` 无漏 |
| 1b | 开书体检单出了，用户定了目标人审率 | 后台「迭代轮次」有目标线 |
| 1b | 按页行款核过：每个异形页（序文大字、目录、表）的列数与每列字数都抽页叠图看过，`expected_cols_pages`、`chars_per_line_pages` 各处都写；体检按列统计待审率、按页量边列宽（< 中位数 80% 报） | 叠图；`guji pipeline pending-stats` 按列；见 [开书体检](../../wiki/新书启动/开书体检.md) |
| 1c | 先行册无整页／整列成片切分错（`cut_gate` 无整页拒，按页碎格数无异常页） | `guji pipeline seg check` |
| 1c | 放行 ≥90%、正文 ≥95%；常用字有 15–20 个本书刻例 | `guji pipeline pending-stats`；字形库深度 |

## 用户参与

| 时机 | 做什么 | 规模 |
|---|---|---|
| 1a 开头 | 给 book ID 和已知资源，开书授权 | 一次，5 分钟 |
| 1a | 建工作区仓、装 GitHub App；有歧义时选版本、参校本 | 一张决定卡 |
| 1b | 看新页型叠图（不阻塞）；定目标人审率 | 每型 1 分钟；约 10 分钟 |
| 1c | 先行册首批字形快审（第一次进库的字必须人裁） | 每册 1–2 小时 |

## 谁做

各书线（史記 SJ、全唐文 QTW、殿本 ZM）；切分不适配交 CV2，字形库 CV3，形近字 CV4；跨书框架 GM2。
