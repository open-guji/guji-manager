# 数据库

guji-manager 用到四个库。每个库「怎么连」只写在连库配置 `databases.toml` 里，代码按库名取；换地方只改配置。
各表装什么、怎么用的教程版在 Wiki [数据库表一览](../../wiki/数据库表一览.md)。

| 库名（配置里的键） | 放什么 | 放在哪 | 怎么连 | 谁写 | 谁读 | 规格 |
|---|---|---|---|---|---|---|
| `central` 中心库 | 册配置、裁定事件、字形库账、整文件、进度看板 | Cloudflare D1 `guji-data-main`（11-18 从 Neon 迁来） | guji-data Worker `data.open-guji.com/v1/sql` | 各线程、执行机（`guji db push/sync`）；控制台写看板 | 所有人（`guji db pull`）；cv 跑批经数据目录读 | [中心库.md](中心库.md) |
| `webinbox` 网站收件箱 | 读者的票、改字意见、讨论、线上待审单、网站键值 | 与中心库同一个 D1 库，表 `web_inbox` | Worker `/v1/web/inbox` | 网站边缘函数（webinbox 令牌）；`guji feedback pending` 放待审单 | `guji feedback cellvotes`、`opinions ingest`；网站 | [网站收件箱.md](网站收件箱.md) |
| `jobs` 任务库 | 重跑／评测单、领单记录、进展、结果、执行方、耗时统计 | Cloudflare D1 `guji-jobs`（11-23 从美国机 Postgres 搬来，旧库只读保留到 12 月初） | guji-data Worker `/v1/sql?db=jobs` | `guji pipeline job submit`、执行方 | `guji pipeline job ls/show`、`guji pipeline perf`、控制台 | [任务库.md](任务库.md) |
| `catalog` 目录库 | 书目、实体、book-text 元数据（只读） | 美国机 Postgres `catalog_latest`／`catalog_rN` | 直连（只在美国机上） | A11 的 book-index 同步任务（每 15 分钟） | 网站搜索、专名识别；manager 现不连 | [目录库.md](目录库.md) |

## 谁负责哪个库、哪些表（11-23 用户定）

按 guji-manager 的步骤分工：**哪一步写这些数据，哪一步的 Project 负责**——表结构、字段去重、空表、读法优化、旧数据删减都由它自己做。
一件事要跨项目改（比如同时动 Worker、cv、manager），由下表「主导」的那个 Project 一家做完所有改动，别人配合核对，不各改一半。

| 库／表 | 负责的步骤 | 负责 Project | 说明 |
|---|---|---|---|
| 中心库 同步底座：`workspaces`、`source_files`、`changes`、`imports`、`db_meta`、`_guard`；guji-data Worker；整库备份 | 公共命令 `guji db`、`datastore` | CV0 | 各表通用的列（`raw`、`rev`、`row_sha`、`ingested_at`）也归这里 |
| 中心库 `books`、`files`（kind=config）、`corpus_files` | 第一步 `start` | GM1 | 11-23 由 CV0 移交 |
| 中心库 字形库各表 `glyph_*`、`glyphs`、`files`（kind=glyph_misc） | 第二步 `pipeline` | GM2 | 字形库算法归 CV3，表与同步归 GM2 |
| 中心库 看板 `progress_*` | 第二步 `pipeline`（`guji pipeline progress`、任务看板） | GM2 主导 | 第四步的 `progress-sync` 也写，改结构由 GM2 做 |
| 任务库 `jobs`（D1 `guji-jobs`） | 第二步 `pipeline`（`guji pipeline job`、执行方） | GM2 | Worker 的 `/v1/sql?db=jobs` 路由归 CV0 |
| 第三步 `text` | — | GM3 | 第三步暂无专用表；裁定写 `events`，由第四步（GM4）管。裁定是否直落 book-text 未定 |
| 中心库 `events`、`consumed`、`verdicts`、`anchors`、`anchor_patches_meta`、`files`（kind=list、batch、feedback_misc） | 第四步 `feedback` | GM4 | |
| 网站收件箱 `web_inbox` | 第四步 `feedback` | GM4 主导 | 网站（Web）写入端配合；Worker 接口改动也由 GM4 提、CV0 部署 |
| 第五步 `output` | — | — | 不写库 |
| 目录库 `catalog` | — | A11 | manager 不连 |

各表的明细与优化方向见 [中心库.md](中心库.md)「按流程分类」一节。

不算数据库、但常一起提到的：R2（大文件、产物包、原图、模型、语料，按 sha 寻址）、本机数据目录 `~/.guji-data/<分支>/<工作区>/` 和 `glyph.db`（中心库的本地副本，可重建）。

## 连库配置 databases.toml

查找顺序，后者按库逐键盖前者：

1. 包内缺省 `guji_manager/config/databases.toml`
2. 用户文件 `~/.config/guji/databases.toml`
3. 环境变量 `GUJI_DB_CONFIG` 指的文件（指了但文件不在就报错）
4. 各库 `env_*` 键点名的单项环境变量（老用法，如 `GUJI_DATA_URL`、`GUJI_DATA_SQLITE`、`JOBSDB_URL`）

| 键 | 含义 |
|---|---|
| `driver` | `d1-worker`（经 Worker）、`sqlite`（本机文件，测试用）、`pg-tunnel`（美国机 Postgres 经 wss 桥）、`postgres`（直连） |
| `url` | Worker 或桥的地址 |
| `db` | Worker 上的库名：中心库 `main` 或实验分支 `exp/GUJI-…` |
| `path` | `sqlite` 的文件 |
| `token`、`password` | 依次试的**环境变量名**（令牌值不进配置文件）；某把 401 换下一把 |
| `exp_token` | 连实验分支时插在第一把之后的令牌变量 |
| `user` | `pg-tunnel` 的 Postgres 角色 |
| `dsn_env` | `postgres` 的 DSN 放在哪个环境变量 |
| `inherit` | 沿用另一个库的全部键，再盖自己的（`webinbox` 继承 `central`） |
| `env_url`、`env_db`、`env_path`、`env_user` | 哪个环境变量能单项盖 `url`／`db`／`path`／`user`（设了 `env_path` 指的变量就改连 SQLite） |

```toml
# ~/.config/guji/databases.toml：例，把任务库指到 D1（切换后包内缺省就是这样）
[jobs]
driver = "d1-worker"
url = "https://data.open-guji.com"
token = ["JOBSDB_TOKEN"]
env_url = "GUJI_JOBS_URL"     # 同一节的键是逐项合并的：不改这项，执行机上的 JOBSDB_URL（wss 桥）会盖掉 url
```

`guji db where` 打印每个库最后解析出的连法、来源文件、哪些令牌变量已设（不打印令牌值）。
cv 的 datastore 客户端只认 `GUJI_DATA_URL`：manager 装载时若它没设，就按 `[central].url` 设上（`dbconfig.apply_env`）。
