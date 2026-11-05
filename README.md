# guji-manager

古籍 pipeline 的 **manager**：新建工作区、原图登记／取图、打包上传中心库、R2、任务库等一切与外界的交互。
识别算法（切分、识别、定字）不在这里，在 [open-guji-cv](https://github.com/open-guji/open-guji-cv)（**pipeline**）。

分界线：凡会影响最终识别产物字节的在 pipeline，其余在这里。所以改这个仓**不需要给 pipeline 发版**，也不会让任何一册的产物过期。

- 文档：[doc/](doc/README.md)（整理全流程：开新书、粗校、精校、点校、反馈迭代）
- Wiki：[看图懂系统](https://github.com/open-guji/guji-manager/wiki)，源文件在 [wiki/](wiki/)，发版合进 main 时自动同步；**每升一次 MINOR 版要整体重改一遍**（见 Wiki「版本与 Wiki 维护」）
- 设计：open-guji-cv 仓 `doc/design/拆分-pipeline与manager.md`
- 接口契约：open-guji-cv 仓 `doc/契约.md`；本仓 [COMPAT.md](COMPAT.md) 记每个 manager 版本支持哪些契约
- 调用方式：只通过子进程跑 `guji-cv`（`GUJI_CV_BIN` 指定，缺省 PATH），不 import `open_guji_cv` 内部
- 版本：`vX.Y.Z` tag，规矩同 open-guji-cv，见 [doc/版本号规矩.md](doc/版本号规矩.md)；**不钉到册、不进产物指纹**
- 分支：**PR 一律投 `dev`**；发版从 dev 切 `rc/vX.Y.Z`，测完 merge 进 `main` 打 tag。main 只接发版。合 PR 前跑 `python scripts/check_rc_target.py <目标分支>`

## 现状（2026-11-05，v0.4.0：拆分完成）

cv 里 manager 一侧的代码已全部搬来（P0–P6，2026-10-27 至 11-04）。cv 只剩 pipeline：Step、引擎、产物契约、Step 读人裁、取钉版输入、Step9 汇总、`guji pipeline／step／status` 等识别命令。本包用 cv 的名字一律经 cv `manager_api`（本包 `_cv.py`），控制台经本包 `console_api`。下面是各批记录。

**2026-11-04 拆分 P2 第四批**：cv 里已没有别的模块依赖的 manager 一侧代码整批搬来，按 cv 的原路径放（`guji_manager/review/cards.py` 即原 `open_guji_cv/review/cards.py`）：
`review`（除 `verdict_view`）、`feedback` 生产侧（harvest、step8、cell_review、web_votes、questions、figures 等）、`eval`（除 rulers、colgeom、round_check）、
`exp`（除 compare、labels、stats）、`formats`、`render`（除 overlay）、`snap`、`ops` 大部分（freeze、close_check、promote、glyphlib、release_check…）、
`report.html／run／progress`、`gold.transfer`、`datastore` 的 backup／spreads／verify／source_xform，以及 5 个命令模块。还在 cv 的：`jobs` 的 spec／store／jobsdb（执行方与命令 P3 已搬来）、`datastore` 主体、
`feedback.consumers` 等、`gold.store`、`ops.prep` 等 `guji pipeline` 要用的、`console_api`。搬来的代码用 cv 留下的东西一律经 `_cv`；
原来按 `Path(__file__).parents[2]` 找 cv 仓（脚本、formats/、doc/）的改用 `_cv.cv_repo()`。

**2026-11-04 拆分 P4**：`ops` 剩下的（prep、glyph_snapshot、corpus_pack、cache_*、rerun_stale…，只留 model_blobs 在 cv，cv 测试开跑要用它取模型）、`render.overlay`、`review.verdict_view`、`feedback.vision`、`exp` 剩下的、`jobs.perf_push` 与 `cli_products`、`cli_perf` 搬来；`guji rerun／pagekinds／cache／product` 从 cv `cli_v2` 拆出搬来。`guji pipeline`／`status`／启动时原先夹在 cv 里的 manager 行为（开跑前取钉版的字形库、模型、语料，整册跑完自动存包，status 的收尾闸等报告）改成 cv 调钩子、本包经入口点 `guji.hooks` 登记（`hooks.py`）；没装本包时 cv 照跑，只有册钉了字形库／模型／语料时 `guji pipeline` 拒跑并提示装法（`--no-prep` 放行）。

**2026-11-04 拆分 P5**：`datastore` 除取件 `client`、`feedback` 的消费者一组（consumers、routes、collate_consumers、glyph_audit）、`gold.atomic`／`v2_align`、`eval.round_check`、任务库存储（`jobs.spec`／`store`／`jobsdb`）搬来；Step 读人裁用的 `verdict_store`、同字判定留 cv（是识别的输入）。模型、字体、语料往 R2 上传拆进 `ops/model_upload.py`（取件留 cv）。

**2026-11-04 拆分 P6**：控制台门面 `console_api` 搬来（cv 那份只留转发，控制台换完 import 后删）；cv 的 `cli_v2`、`manager_api` 归 pipeline，守卫的 pipeline→manager 存量清零。

2026-11-02 定的分拆计划：P0 安全网 → P1 拆 cli_v2 → P2 冷的顶层 → P3 opinions、jobs → P4 review／ops／eval → P5 consumers／gold／datastore → P6 收尾；**每批 manager 新增与 cv 删除同一天合，不先复制并存**（10-27／10-31 复制来的 opinions、jobs 几天内就过期了，已删）。

## 开发

```
pip install -e <open-guji-cv 检出>[dev] && pip install -e ".[dev]" && pytest -s -n auto
```

`tests/from_cv/` 是第四批起从 cv `tests/` 搬来的测试，借 cv 仓的 `tests/conftest.py`（环境隔离、`ws` 等夹具）、`tests/helpers.py`
和冻结数据，所以 cv 要**可编辑安装**；不是的话这个目录整个跳过（有提示）。CI 把 cv dev 检出在 `_cv/` 再装。

## 已搬来的子命令

| 子命令 | 来自 cv | 搬迁 |
|---|---|---|
| `guji opinions` | `opinions/`、`cli_opinions.py`、`config/opinions/rules.json` | P2，2026-11-02 |
| `guji source` | `cli_source.py`（原图：R2 源件、页表） | P2 第二批，2026-11-02 |
| `guji cellvotes` | `cli_cellvotes.py`（网站格级投票落事件） | P2 第二批，2026-11-02 |
| `guji freeze` | `cli_freeze.py`（冻结登记） | P2 第二批，2026-11-02 |
| `guji exp` | `cli_exp.py`（A/B 实验） | P2 第三批，2026-11-04 |
| `guji snap`／`archive`／`release`／`deploy` | `cli_ops.py` | P2 第三批，2026-11-04 |
| `guji events`／`gold`／`batch`／`label-batch` | `cli_feedback.py` | P2 第三批，2026-11-04 |
| `guji eval`／`check`／`groups`／`cards`／`progress`／`collate` | `cli_eval.py` | P2 第三批，2026-11-04 |
| `guji close-check`／`exit-check`／`audit`／`char-diff` | `cli_close.py` | P2 第四批，2026-11-04 |
| `guji db` | `cli_db.py`（中心库 sync／pull／push…） | P2 第四批，2026-11-04 |
| `guji store`／`recheck`／`glyphlib`／`rekey-cells`／`promote`／`corpus` | `cli_glyph.py` | P2 第四批，2026-11-04 |
| `guji glyph-db` | `cli_glyph_db.py` | P2 第四批，2026-11-04 |
| `guji model`／`font` | `cli_model.py` | P2 第四批，2026-11-04 |
| `guji job`（`python -m guji_manager.jobs`，执行方 `work`） | `jobs/`（runner、cli、board…） | P3，2026-11-04 |
| `guji rerun`／`pagekinds`／`cache`／`product` | `cli_runs.py` | P4，2026-11-04 |
| `guji products`／`perf` | `cli_products.py`／`cli_perf.py` | P4，2026-11-04 |
| `guji pipeline`／`status` 的开跑准备、自动存包、收尾闸报告 | `hooks.py`（入口点 `guji.hooks`） | P4，2026-11-04 |
| （模块）datastore、消费者、任务库存储、模型上传 | `datastore/`、`feedback/consumers…`、`jobs/spec…`、`ops/model_upload.py` | P5，2026-11-04 |
| 控制台门面 | `console_api.py` | P6，2026-11-04 |

装法：先装 open-guji-cv，再 `pip install -e .`（本仓经入口点组 `guji.commands` 把子命令并进 `guji`，经 `guji.hooks` 登记 `guji pipeline` 的钩子）。

## 搬迁工具

`python tools/move_from_cv.py --cv <cv 检出> --pkg <包> --cli <cli_xxx> --tests <测试>`：复制包（和命令行模块、测试），自动改 import，并列出要人看的 `__file__`／`parents[`／`REPO_ROOT` 用法。只复制，不删 cv 里的；cv 的删除另开 PR，同一天合。

踩到的坑（下次别重来）：
- 数据文件跟着包走（`opinions/rules.json` 要进 `package-data`，路径改成包内相对）。
- 指向 cv 仓里脚本或数据的 `parents[N]` 要改成 `open_guji_cv.__file__` 推出来的路径。
- 测试公共件不用抽：`tests/from_cv/conftest.py` 直接借 cv 的 conftest 与 helpers（cv 可编辑安装）。
- 包在 cv 还留着一部分（如 `review` 留着 `verdict_view`）时两边各有 `__init__`：cv 那边删掉指向已搬模块的 import，本包这边照抄并经 `_cv` 取留在 cv 的。
- 已搬来的名字在 `_cv._LOCAL` 里（先查它），老代码 `from ._cv import X` 照样能用。
- 测试里别让整理脚本的 `ensure_manager` 拉 main 重装本机的包（cv conftest 设 `GUJI_NO_ENSURE_MANAGER=1`）。
