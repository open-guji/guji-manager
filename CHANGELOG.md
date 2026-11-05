# Changelog

版本号规矩见 `doc/版本号规矩.md`（2026-11-03 起，同 open-guji-cv）。本文件记录**全部**版本（含 PATCH）；动代码的 PR 投 `dev`，在 `## [未发版]` 下加一行、写明档位；切 rc 时改成 `## [X.Y.Z] - 测试中`，发版时改成日期。

## [未发版]

## [0.4.2] - 测试中

- 任务库：空闲执行方不再碰 Neon（PATCH，用户 11-05 定「job 彻底从 Neon 撤掉，不要有进程不断 query」）。原先每个空闲执行方每 5 分钟把看板写进中心库 `progress.metric`，约 40 个执行方合起来每 8 秒一次，Neon 永远不休眠；现在空闲只连任务库，看板在领单、收尾、心跳（跑单中）和 `guji job submit` 交单时更新。

- eval：登记三书人裁冻结金标的 7 个评测（`db_match_books`、`match_pairs_{siku_v2,shiji,qtw}`、`rare_{siku_v2,shiji,qtw}`），集在 open-guji-dataset #64，脚本在 cv #1069（PATCH）。
- final-review：`finalize --book-yaml` 读 `params.seed_admit.ruling_override_groups`（cv #1064）作越过参校本白名单，与 `--whitelist` 不一致拒绝（PATCH）。

- 人审页模板库页型 `codepoint` 升 2.0.0（PATCH，全唐文码位线，总览 11-05 转 A31）：换专用模板 `codepoint.tpl.html`（按组看图定夺：每字一行原书字块＋码位、已认/整理本数；统一作某字／分开·互认／分开·不同字／合并到别的字，未选的组挡住下一页）；新增 `review_pages/codepoint.py` 与命令 `review-pages cp-items`（groups.json → items）、`cp-apply`（结果 → codepoints 片段＋双向 follow_ref＋不同字/未定清单）。
- final-review：参校本字取 align_char，缺时退回 cells.tsv 的 ref 列（PATCH，A24 反馈）。

- 新增 `guji-manager iterate` 子命令组（PATCH，A31，用户 11-05 定降人审迭代框架）：`round-report` 轮报告、`gold` 金标登记与校验、`audit` 滚动抽检台账、`leverage` 杠杆排序、`freeze` 三书冻结日历；`pending-stats` 的 cells.tsv 末尾追加 `ref`、`top` 两列。文档 `doc/02-粗校/轮报告与验收工具.md`。
- 一天做完一本书的自动化 P5／T2（PATCH，新增命令，A31，sheldon 11-05）：`guji-manager suggest`（诊断信号→A 档开关建议，点头后 `--apply` 文本追加写册 yaml、核合并结果、不覆盖已有键）；`guji-manager final-review`（殿本 r4 的 build／finalize／write_rulings 抽成跨书命令：run 选格＋取窗口候选＋按类 Z/N/L/P/D 分批出 A/B 判读会话清单，status 核齐，finalize 门槛＋金标，write 金标 0 错才写 ctx_ruling）；`pending-stats` 的 cells.tsv 末尾加 ref、top、tok 三列；`_cv` 登记 RulingLog 等六个名字（`_FALLBACK`）。文档 `doc/02-粗校/终审判读与开关建议.md`。

## [0.4.1] - 2026-11-05

- 执行方自更新修复（PATCH，A30）：`_RUNNER_PATHS` 去掉拆分 P5 后已不存在的 `open_guji_cv/jobs`（否则 `_runner_outdated` 永远判不出 cv 侧更新）；自更新 re-exec 把老入口 `-m open_guji_cv.jobs` 换成 `guji_manager.jobs`（`_reexec_argv`）。

## [0.4.0] - 2026-11-05

- 拆分 P6 收尾（MINOR，A31，用户 11-04「继续 都做完」，计划里 P6 即发 0.4.0）：控制台门面搬来 `guji_manager/console_api.py`（179 个名字，cv 的与本包的照旧惰性取；cv `open_guji_cv.console_api` 改成转发到这里，guji-console 换 import 后删）。cv 那边 `cli_v2`、`manager_api` 归 pipeline、去掉 `MANAGER_CLI_MODULES` 过渡件，守卫的 pipeline→manager 存量清零——**cv 里已没有 manager 一侧的代码**。Wiki 已按 v0.4 重改（重画分工图；全景、安装、任务库、产物包、待审原因页按 0.3.1–0.4.0 改）；README 现状改写。

## [0.3.4] - 2026-11-04

- 拆分 P5 底层（PATCH，A31，用户 11-04「继续 都做完」；归属照 11-04 决策卡推荐项「读的归 pipeline，写的归 manager」）：从 cv 搬来 21 个模块——`datastore` 除取件 `client` 外全部（connect、gitsource、importer、materialize、neonapi、packs、pull、r2、scope、sources、workcopy、wsbridge，连 `schema.sql`）、`feedback` 的消费者一组（consumers、routes、collate_consumers、glyph_audit）、`gold.atomic`／`v2_align`、`eval.round_check`、任务库存储（`jobs.spec`／`store`／`jobsdb`，连 `schema.sql`）。新增 `ops/model_upload.py`：模型、字体、底库语料往 R2 上传从 cv `ops/model_blobs` 拆来（取件留 cv），`guji model upload`／`font upload`／`corpus upload` 改用它。Step 读人裁用的 `verdict_store` 已在 cv `gold.store`，`_cv` 经 `gold_store_verdict_store` 取；`feedback/__init__` 照旧登记消费者与路由表。`_cv` 新增 98 个名字。命令与参数不变。测试 41 个文件搬到 `tests/from_cv/`（与前几批同名的另存 `*_p5.py`）。cv 那一半等本版发出后再合。

## [0.3.3] - 2026-11-04

- 拆分 P4 中层（PATCH，A31，用户 11-04「继续 都做完」）：从 cv 搬来 31 个模块——`ops` 剩下的（prep、glyph_snapshot、corpus_pack、central_glyph、cache_verify／cache_warm、emb_pack_build、rare_index_build、rerun_stale、page_kinds_report、products_diff、pack_purity、glyph_release_gate、exclusion_rebind、exp_record；model_blobs 留 cv）、`render.overlay`、`review.verdict_view`、`feedback.vision`、`exp.compare／labels／stats`、`jobs.perf_push`、`cli_products`（products）、`cli_perf`（perf），以及从 cv `cli_v2` 拆出的 `cli_runs`（rerun、pagekinds、cache、product）。命令与参数不变。新增 `hooks.py`，经入口点 `guji.hooks` 给 cv 的 `guji` 登记四个钩子：startup（派生缓存取件器、耗时推任务库、步内计时）、prepare（开跑前备钉版字形库／模型／语料、预建 Step5-b 模板索引）、finished（整册跑完自动存包、提醒没存包）、status（收尾闸、裁放不一致、看图待审、没存包）——原先都夹在 cv `cli_v2` 里。`_cv` 新增 102 个名字（`datastore.workcopy.read_state` 叫 `workcopy_read_state`，避开 `exp.runner.read_state`）。测试 25 个文件搬到 `tests/from_cv/`（与前几批同名的另存 `*_p4.py`）。cv 那一半等本版发出后再合。

## [0.3.2] - 2026-11-04

- 拆分 P3 jobs（PATCH，A31，用户 11-04「继续 都做完」）：任务库的执行方与命令从 cv 搬来 `guji_manager/jobs/`（runner、cli、board、notify、exit_trace、`__main__`；spec、store、jobsdb 仍在 cv，经 `_cv` 取）。`guji job` 由本包提供；执行方改为 `python -m guji_manager.jobs work`（cv `scripts/guji_jobs.sh` 同步改，老命令行 `python -m open_guji_cv.jobs` 在 cv 留转发）。执行方空闲换代码时除了 cv 的 runner 检出，也看本包检出（ensure_manager 管的那份，`GUJI_MANAGER_DIR` 缺省 /opt/guji-manager-seed）是否落后 main，落后就切到 main 再 exec；开发机自己的检出不动。15 个测试文件搬到 `tests/from_cv/`。

## [0.3.1] - 2026-11-04

- 拆分 P2 第四批（PATCH，A31，用户 11-04「继续 都做完」）：cv 里已没有别的模块依赖的 manager 一侧代码 118 个模块（约 3 万行）整批搬来，按原路径放：`review`（除 verdict_view）、`feedback` 生产侧、`eval`（除 rulers／colgeom／round_check）、`exp`（除 compare／labels／stats）、`formats`、`render`（除 overlay）、`snap`、`ops` 大部分、`report.html／run／progress`、`gold.transfer`、`datastore` 的 backup／spreads／verify／source_xform，以及命令模块 `cli_close`（close-check、exit-check、audit、char-diff）、`cli_db`（db）、`cli_glyph`（store、recheck、glyphlib、rekey-cells、promote、corpus）、`cli_glyph_db`（glyph-db）、`cli_model`（model、font）。命令与参数不变。用 cv 留下的东西一律经 `_cv`（新增 270 个名字）；已搬来的名字进 `_cv._LOCAL`；按 `__file__` 找 cv 仓的改用 `_cv.cv_repo()`（顺修第三批 `cli_ops`／`cli_feedback` 里默认仓根指到本仓的错）。测试 101 个文件搬到 `tests/from_cv/`（借 cv 的 conftest 与 helpers，cv 要可编辑安装；CI 改为检出 cv dev 再装）。`review/pending_reasons.yaml` 进 package-data。cv 那一半等本版发出后再合。

## [0.3.0] - 2026-11-04

- 拆分 P2 第三批（PATCH，A31）：从 cv 搬来 4 个命令模块、15 条命令——`cli_exp`（exp）、`cli_ops`（snap、archive、release、deploy）、`cli_feedback`（events、gold、batch、label-batch）、`cli_eval`（eval、check、groups、cards、progress、collate），以及 9 条命令层测试（其中 4 条 `guji snap` 的经 cv 的 `guji` 入口跑，夹具照抄 cv）。参数与 cv 逐一相同；底下逻辑仍在 cv，经 `_cv` 取（新增 73 个名字，整模块导出用「包_模块」名，如 `snap_pack`）。cv 那一半等本包发版后再合，在那之前 cv 自带的同名命令优先、本包这份不生效。
- pending-stats 加新书体检（MINOR，A24，sheldon 11-04 定形近字长期计划 G1）：报告新增「零·二、诊断信号」一节，按待审原因分布给方向（版式为主、借来的字形不像、字组弃权、字对、符号位、遮挡、写法待定、缺字、极难形近、刻例太少），每条带依据、往哪努力、难度档 A／B／C 和谁做；`summary.json` 加 `signals`。纯函数在 `guji_manager/diagnose.py`，阈值是殿本 r4、史記／全唐文 11-02 定的经验值。框架见 ai-team `domain/CV/规划/形近字领域-长期计划与总览-草稿-2026-11-04.md`。

## [0.2.1] - 2026-11-04

- 成因码细分改名（PATCH，A31，sheldon 11-04 定）：待审单的 `cause`／`cause_detail` 改名 `pending_reason_cause`／`pending_reason_cause_detail`（pending_reason 下的细项），`cls` 不再出单；taxonomy、pending-stats 先读新名、老单退回旧名；瘦单改按「没有 ref／ctx／库候选」判（原先看有没有 cls）。
- cellvotes draft 事件带待审原因（PATCH，A31）：草稿行写投票时那张单上该格的 `pending_reason`，单对不上或格不在单上写 `unknown`；码表经 `_cv.pending_reason_specs` 取（cv `manager_api` 同步登记）。
- pending-stats 按待审原因统计（PATCH，A31，sheldon 11-03 定 `pending_reason`）：报告新增「零、按待审原因」一节（码、名、去向取 cv `review/pending_reason.py`，没装 cv 只列英文名），`summary.json` 加 `by_reason`，`cells.tsv` 加 `pending_reason` 列；单上没有这个字段的格记 `unknown`。旧大类／小类保留过渡。
- 版本号规矩（PATCH，Sheldon 11-03「全部仿照 open-guji-cv」）：新增 `doc/版本号规矩.md`；分支改为 dev 集成、发版切 `rc/vX.Y.Z`、main 只接发版并在合并提交上打 `vX.Y.Z`；搬来 cv 的 `scripts/check_rc_target.py`（合 PR 前核目标分支）与 `scripts/check_release_tags.py`（发版后核 tag）及测试；新增 `.github/workflows/release.yml`（推 tag 自动建 Release、挂 wheel＋sdist＋SHA256SUMS）、`tests/test_version.py`（两处版本号一致）；CI 也在 dev／rc 上跑。Wiki 的 `m-vX.Y` 改写成 `vX.Y`（中转站只收 `vX.Y.Z` tag），Wiki 与文档里指向 `blob/main` 的链接改指 `dev`。基线 tag `v0.2.0` 打在 main `61cc28e`。

## [0.2.0] - 2026-11-02（基线 tag `v0.2.0` 打在 2026-11-03 main `61cc28e`，含其后的 Wiki 首版与全唐文工具）

- 新增 GitHub Wiki（源文件 `wiki/`，13 页，多用真截图与示意图）与 Action `wiki-sync`（合进 main 自动同步）。规矩：每升一次 MINOR 版，对照上个 MINOR 以来的 PATCH 整体重改 Wiki，MINOR 发版 PR 里写明「Wiki 已按 m-vX.Y 重改」。
- 拆分 P2 第二批：搬来 `cli_source.py`（`guji source`）、`cli_cellvotes.py`（`guji cellvotes`）、`cli_freeze.py`（`guji freeze`）与它们的命令层测试；底下的逻辑（`datastore.sources`、`feedback.web_votes`、`ops.freeze_register` 等）仍在 cv，经 `_cv` 取（`_FALLBACK` 支持导出整个模块）。版本升到 0.2.0，cv 的 `MIN_MANAGER_VERSION` 据此要求。cv 同日删除。

## [0.1.0] - 2026-11-02

- 版本升到 0.1.0：cv 的 `MIN_MANAGER_VERSION` 据此不认旧种子里的过期副本（云端快照 10-27 的种子带着当时的 opinions）。
- 拆分 P2 第一批：搬来 `opinions/`、`cli_opinions.py`（`guji opinions`）、`rules.json`（原 cv `config/opinions/`，现随包）与 `tests/opinions/`；用 cv 内部经 `_cv`（新增 data_home、central_data_dir、CentralError）。cv 同日删除并登记 `MOVED_TO_MANAGER`。`commands.run` 可不经 cv 直接跑本包子命令。`test_online_lists` 夹具顺带把 `push_pack_rate` 也换成空操作（#37 起测试会去连库）。
- 拆分 P0：加 CI `.github/workflows/test.yml`，推送／PR 时跑，另每天对 cv dev 最新跑一次。
- 拆分 P0：本包用 cv 内部一律经 `guji_manager._cv`（转 cv 门面 `open_guji_cv.manager_api`，cv #874；旧 cv 按兜底表直取），守卫 `tests/test_cv_surface.py`。`tools/` 下的一次性脚本不受限。
- 删掉 10-27／10-31 复制过来的 `jobs`、`opinions`（+`cli_opinions`）与其测试：复制后 cv 那份又改了十多次，这里的已过期，且 cv 自带的命令优先、这两份从未生效。改为每批搬迁当天 manager 新增与 cv 删除同时合（P3 再搬）。
- 新增 `guji-manager central-gc`（`guji_manager.central_gc`）：中心库定期清理，按保留规则（现行 main＋上一份 main、冻结、线上单所用版本、N 天内、排队任务要用）列出 R2 里可删的产物包；`--apply --from-list` 照审过的清单删，要正式令牌。方案见 ai-team `通用/中心库维护方案.md`。
- 任务看板（`jobs/board.py`）少读：已成功任务只取 steps／pages，结果包只取看板上的任务（同 cv #869）。

- `online_lists.record_main`：标 main 时把 ★ main 标签记到后台看板（progress.volume.extra 的 a31.main），页面据此标出线上单是否落后于 main；无库连接静默跳过。

- 新增 `guji_manager.review_triage`（`guji-manager triage prepare/eval/train/route/sheet`，可选依赖 `[triage]`）：参校字快审分流。按位置和字跳过，OCR＋裁图几何的 GBDT 自动放行，OCR 不一致撤下，只出拿不准的格的快审页。文档 `doc/01-开新书/快审减量.md`。
- 新增 `guji_manager.online_lists`：经入口点 `guji.post_promote`，标 main 后自动在后台重出这册线上待审单（挂标点层／旧单有票／无 rev 包的册只提示）；取代 ai-team 的 2 小时轮询任务。
- 搬来 `jobs`（任务库：spec/store/board/runner/cli，4 个测试文件）；`guji job` 经插件并入，cv 自带的优先。RUNNER_ROOT 改读 GUJI_JOBS_RUNNER 或 open_guji_cv 所在检出。
- 搬来 `opinions`（+ `cli_opinions`、`rules.json`）与 80 项测试；`guji_manager.commands` 经入口点 `guji.commands` 并进 `guji`。

## [0.0.1] - 2026-10-27

- 骨架：`guji_manager.pipeline`（子进程调 `guji-cv`、契约版本核对）、`guji-manager check`、COMPAT.md。
