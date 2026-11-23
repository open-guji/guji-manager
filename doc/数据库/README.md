# 数据库

guji-manager 用到四个库。每个库「怎么连」只写在连库配置 `databases.toml` 里，代码按库名取；换地方只改配置。
各表装什么、怎么用的教程版在 Wiki [数据库表一览](../../wiki/数据库表一览.md)。

| 库名（配置里的键） | 放什么 | 放在哪 | 怎么连 | 谁写 | 谁读 | 规格 |
|---|---|---|---|---|---|---|
| `central` 中心库 | 册配置、人裁事件、字形库账、整文件、进度看板 | Cloudflare D1 `guji-data-main`（11-18 从 Neon 迁来） | guji-data Worker `data.open-guji.com/v1/sql` | 各线程、执行机（`guji db push/sync`）；控制台写看板 | 所有人（`guji db pull`）；cv 跑批经数据目录读 | [中心库.md](中心库.md) |
| `webinbox` 网站收件箱 | 读者的票、改字意见、讨论、线上待审单、网站键值 | 与中心库同一个 D1 库，表 `web_inbox` | Worker `/v1/web/inbox` | 网站边缘函数（webinbox 令牌）；`guji feedback pending` 放待审单 | `guji feedback cellvotes`、`opinions ingest`；网站 | [网站收件箱.md](网站收件箱.md) |
| `jobs` 任务库 | 重跑／评测单、领单记录、进展、结果、执行方、耗时统计 | 美国机 170.106.66.156 Postgres 库 `jobs`（11-03 从 Neon 搬来）；**计划搬 D1 `guji-jobs`** | wss 桥 `relay.open-guji.com/jobsdb` | `guji pipeline job submit`、执行方 | `guji pipeline job ls/show`、`guji pipeline perf`、控制台 | [任务库.md](任务库.md) |
| `catalog` 目录库 | 书目、实体、book-text 元数据（只读） | 美国机 Postgres `catalog_latest`／`catalog_rN` | 直连（只在美国机上） | A11 的 book-index 同步任务（每 15 分钟） | 网站搜索、专名识别；manager 现不连 | [目录库.md](目录库.md) |

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
db = "jobs"
token = ["JOBSDB_TOKEN"]
```

`guji db where` 打印每个库最后解析出的连法、来源文件、哪些令牌变量已设（不打印令牌值）。
cv 的 datastore 客户端只认 `GUJI_DATA_URL`：manager 装载时若它没设，就按 `[central].url` 设上（`dbconfig.apply_env`）。
