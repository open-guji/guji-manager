# Changelog

## [未发版]

- 新增 `guji_manager.review_triage`（`guji-manager triage prepare/eval/train/route/sheet`，可选依赖 `[triage]`）：参校字快审分流。按位置和字跳过，OCR＋裁图几何的 GBDT 自动放行，OCR 不一致撤下，只出拿不准的格的快审页。文档 `doc/01-开新书/快审减量.md`。
- 新增 `guji_manager.online_lists`：经入口点 `guji.post_promote`，标 main 后自动在后台重出这册线上待审单（挂标点层／旧单有票／无 rev 包的册只提示）；取代 ai-team 的 2 小时轮询任务。
- 搬来 `jobs`（任务库：spec/store/board/runner/cli，4 个测试文件）；`guji job` 经插件并入，cv 自带的优先。RUNNER_ROOT 改读 GUJI_JOBS_RUNNER 或 open_guji_cv 所在检出。
- 搬来 `opinions`（+ `cli_opinions`、`rules.json`）与 80 项测试；`guji_manager.commands` 经入口点 `guji.commands` 并进 `guji`。

## [0.0.1] - 2026-10-27

- 骨架：`guji_manager.pipeline`（子进程调 `guji-cv`、契约版本核对）、`guji-manager check`、COMPAT.md。
