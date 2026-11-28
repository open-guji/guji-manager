# benchmark 统一入口 `guji bench`

2026-11-28 起（Sheldon 定「每个 benchmark 统一接口、命令接进 guji-manager」）。任何一本书上测任何一个 bench，一条命令，资源自动取。
登记表与结果格式在 cv `open_guji_cv/eval/bench.py`，各 bench 的实现在 cv `eval/benches/`；本仓只管取资源（`guji_manager/bench/resources.py`，GM2 维护）与命令。
分派与接入验收：ai-team `domain/CV/规范/bench统一接口-2026-11-28.md`。

## 命令

| 命令 | 做什么 |
|---|---|
| `guji bench list [--book <书>] [--step <Step>]` | 列 bench；给了书标有没有金标、缺什么环境。末尾列还没接的老评测器和报表类命令 |
| `guji bench fetch <bench> --book <书>` | 只备资源不跑，打印每样资源的路径与版本 |
| `guji bench run <bench|@套> --book <书> [--vol …] [--arg k=v] [--params JSON] [--against <结果目录>]` | 备资源、跑、打分、对照、验护栏、写结果；regressed 时退出码 1 |
| `guji bench ab <bench> --book <书> --params JSON` | A（现行）、B（加覆盖）各跑一次，出 B 对 A 的翻转清单；有变坏退出码 1 |
| `guji bench guard [--heavy] [--legacy]` | 发版护栏：每个有护栏的 bench × 有金标的书（显式表读表，约定式分片看测试集仓里的书目录）；有金标却 skipped／no_gold、或读不到测试集仓，都按不过算；`--legacy` 连老框架 `guji eval guard` 一起验 |
| `guji bench show <bench> --book <书> [--history]` | 看最近一次 report.md；`--history` 列历次 |
| `guji bench run <bench> --book <书> … --job [--cv <tag／分支／提交>]` | 不在本机跑，交任务库由执行机跑（见下「交执行机」） |

例：`guji bench run cut-2d --book 988g3f0wsu`、`guji bench run decide --book 988g3f0wsu --arg set=small`。

## 资源从哪来

需要中心库读令牌（`eval "$(python3 ~/guji-dev-secret/gsecrets.py export)"`）。缓存根 `$GUJI_DATA_HOME/bench-cache/`（`--cache` 改）。

| needs | 取法 |
|---|---|
| gold | 测试集仓（`--dataset`，缺省 `GUJI_DATASET_DIR` 或 cv 旁边的 open-guji-dataset），记 commit。都没有（干净云会话、执行机）就自动稀疏克隆到 `bench-cache/dataset/`，只检出要的分片与 `guards/`；`--dataset-ref` 钉版本 |
| code | 书仓 guji-workspace/<书id>-*，克隆到 `bench-cache/books/<书>/`（本机 `~/guji-workspace` 或 `GUJI_BOOKS_DIR` 有就从本机克隆）；`--ws` 用现成的。缓存里已有就 `git pull --ff-only`，拉不动报缺资源（`--offline` 才用旧检出） |
| config | `guji db pull --no-glyph`，跳过事件、身份账、待审单、审阅、output（部分副本，bench 不写库）；底库、PUA 表、组配置进 `datahome/main/.borrowed/` |
| glyph_lib | 改成整拉 `guji db pull`（连借库）并重建 `glyph.db`（没钉 glyph_pin 的册用它）；钉了版的册按 `guji glyph-db pin-build` 建 `glyph-g<N>.db` |
| raw | 只取金标涉及的页（bench 的 `plan` 给了页时），否则整册；按册钉的页表版本 |
| products | 各册 main 指针的产物包（`--label` 改），按标签缓存；先取到临时目录、完整了再改名 |
| corpus | 按各册**生效的** `corpus:` 总号（同 `guji job precheck`；不看钉子账最后一行）展开三层清单，缺的按 sha 从 R2 取回（同 `guji corpus fetch`）。`ctx.res["corpus"]`＝`{pin, by_vol, book_corpus: [本书整理本…], general_corpus: [引擎通用语料…]}`，`env.corpus` 记每册总号与清单哈希。没钉 corpus 的册报缺资源 |
| models | cv 运行时按钉子自己取回，这里只核令牌 |
| bench5b | 5b 评测集 `cache/glyph_bench`、`oov_bench`：缺了按钉死的 sha 核对冻结包 `train_bundle.zip` 再解（`eval/bench_bundle.py`，GM4 交来），包不在或 sha 不符报缺资源 |
| torch、gpu、ocr | 只核环境 |

**钉子**：各册生效的 cv_version、code、glyph_pin、corpus、model 及来自哪一层（含配置组），与 `guji job precheck` 同一读法（`jobs.precheck.pins_of`），整份记进 `env.pins`。`mode: run` 的 bench 开跑前再核：书仓 `code/` 与钉的 `k<N>` 不一致报缺资源；册钉的 cv_version 与本机 cv 不同只提醒（记 `env.pin_warnings`），因为 bench 本来常拿新 cv 量老书。

同机同书备资源串行（`bench-cache/locks/<书>.lock`），执行机同时领到两张 bench 单不会抢同一缓存。

缺任何一样报 `skipped` 并写明怎么补，不出半截结果；不回退到本机别处的字形库或产物。不写任何正式数据（`--arg update=…` 直接拒）。

## 结果

`./bench-results/<bench>/<书>/<时间>/`（`--out` 改）：`result.json`（schema 1：主指标、全部指标、护栏、对照、`env` 里的 cv／manager／测试集／书仓／中心库 rev／产物包标签）、`items.jsonl`（逐样本，翻转清单用）、`report.md`、`ctx.json`（资源路径）。
status 只有 ok、regressed、skipped、no_gold，跑崩了记 failed（护栏按不过算）。

## 交执行机（`--job`）

`guji bench run <bench> --book <书> [--vol …] [--arg k=v] [--params JSON] [--publish] --job [--cv <ref>] [--why …]`
交一张 kind=bench 的单（字段见 `guji_manager/jobs/spec.py` 模块头）。`--cv` 缺省本机 cv 的提交（有没提交的改动就拒）。
执行机照样 `guji bench run`，资源自己备（缓存 `$GUJI_DATA_HOME/bench-cache`，同机同书有锁），把 `result.json`、`report.md`、
`items.jsonl`（前 200 KB）写回任务结果，`guji job show <号>` 看。**不存包、不推库、永不标 main**（单上不收 book、base、
compare_to、run，output.pack 恒 false）；带 `--publish` 才另写 `bench_runs` 一行（用写令牌）。
结局：ok／regressed／no_gold 算成功（结论照实在结果里）；skipped（执行机缺资源）记 blocked，补齐后 `guji job retry`；跑崩记 failed。
不收 `--against`、`--ws`、`--dataset`、`--cache`、`--out`、`--offline`。heavy 级建议这样跑，light 级本机跑更快。

## 写进中心库（`--publish`）

Sheldon 11-28 定：建 `bench_runs` 表，只有带 `--publish` 才写（`run`、`ab` 的 B、`guard` 都认），`--baseline` 标基线、`--note` 写一句。一次 run 一行（主键 `<bench>/<书>/<时间>-<result.json 短 sha>`，重发不重写；`ran_at` 是 UTC），存 result.json 原样与常用列（状态、主指标、cv／manager 版本、测试集、中心库 rev、参数、谁跑的），不存逐样本。跑崩的不发。`guji bench show <bench> --book <书> --central` 看库里历次（缺省只列 ok／regressed，`--all-status` 全列）。要写令牌与 `GUJI_ACTOR`。
