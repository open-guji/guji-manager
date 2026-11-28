# benchmark 统一入口 `guji bench`

2026-11-28 起（Sheldon 定「每个 benchmark 统一接口、命令接进 guji-manager」）。任何一本书上测任何一个 bench，一条命令，资源自动取。
登记表与结果格式在 cv `open_guji_cv/eval/bench.py`，各 bench 的实现在 cv `eval/benches/`；本仓只管取资源（`guji_manager/bench/resources.py`）与命令。
分派与接入验收：ai-team `domain/CV/规范/bench统一接口-2026-11-28.md`。

## 命令

| 命令 | 做什么 |
|---|---|
| `guji bench list [--book <书>] [--step <Step>]` | 列 bench；给了书标有没有金标、缺什么环境。末尾列还没接的老评测器和报表类命令 |
| `guji bench fetch <bench> --book <书>` | 只备资源不跑，打印每样资源的路径与版本 |
| `guji bench run <bench|@套> --book <书> [--vol …] [--arg k=v] [--params JSON] [--against <结果目录>]` | 备资源、跑、打分、对照、验护栏、写结果；regressed 时退出码 1 |
| `guji bench ab <bench> --book <书> --params JSON` | A（现行）、B（加覆盖）各跑一次，出 B 对 A 的翻转清单；有变坏退出码 1 |
| `guji bench guard [--heavy] [--legacy]` | 发版护栏：每个有护栏的 bench × 登记了金标的书；`--legacy` 连老框架 `guji eval guard` 一起验 |
| `guji bench show <bench> --book <书> [--history]` | 看最近一次 report.md；`--history` 列历次 |

例：`guji bench run cut-2d --book 988g3f0wsu`、`guji bench run decide --book 988g3f0wsu --arg set=small`。

## 资源从哪来

需要中心库读令牌（`eval "$(python3 ~/guji-dev-secret/gsecrets.py export)"`）。缓存根 `$GUJI_DATA_HOME/bench-cache/`（`--cache` 改）。

| needs | 取法 |
|---|---|
| gold | 测试集仓（`--dataset`，缺省 `GUJI_DATASET_DIR` 或 cv 旁边的 open-guji-dataset），记 commit |
| code | 书仓 guji-workspace/<书id>-*，克隆到 `bench-cache/books/<书>/`（本机 `~/guji-workspace` 或 `GUJI_BOOKS_DIR` 有就从本机克隆）；`--ws` 用现成的 |
| config | `guji db pull --no-glyph`，跳过事件、身份账、待审单、审阅、output（部分副本，bench 不写库）；底库、PUA 表、组配置进 `datahome/main/.borrowed/` |
| glyph_lib | 改成整拉 `guji db pull`（连钉版字形库与借库） |
| raw | 只取金标涉及的页（bench 的 `plan`），按册钉的页表版本 |
| products | 各册 main 指针的产物包（`--label` 改），按标签缓存 |
| models、corpus | cv 运行时按钉子自己取回，这里只核令牌 |
| torch、gpu、ocr | 只核环境 |

缺任何一样报 `skipped` 并写明怎么补，不出半截结果；不回退到本机别处的字形库或产物。不写任何正式数据（`--arg update=…` 直接拒）。

## 结果

`./bench-results/<bench>/<书>/<时间>/`（`--out` 改）：`result.json`（schema 1：主指标、全部指标、护栏、对照、`env` 里的 cv／manager／测试集／书仓／中心库 rev／产物包标签）、`items.jsonl`（逐样本，翻转清单用）、`report.md`、`ctx.json`（资源路径）。
status 只有 ok、regressed、skipped、no_gold，跑崩了记 failed（护栏按不过算）。写进中心库 `bench_runs`（`--publish`）待用户定。
