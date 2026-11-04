# Changelog

版本号规矩见 `doc/版本号规矩.md`（2026-11-03 起，同 open-guji-cv）。本文件记录**全部**版本（含 PATCH）；动代码的 PR 投 `dev`，在 `## [未发版]` 下加一行、写明档位；切 rc 时改成 `## [X.Y.Z] - 测试中`，发版时改成日期。

## [未发版]

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
