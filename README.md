# guji-manager

古籍 pipeline 的 **manager**：新建工作区、原图登记／取图、打包上传中心库、R2、任务库等一切与外界的交互。
识别算法（切分、识别、定字）不在这里，在 [open-guji-cv](https://github.com/open-guji/open-guji-cv)（**pipeline**）。

分界线：凡会影响最终识别产物字节的在 pipeline，其余在这里。所以改这个仓**不需要给 pipeline 发版**，也不会让任何一册的产物过期。

- 文档：[doc/](doc/README.md)（整理全流程：开新书、粗校、精校、点校、反馈迭代）
- 设计：open-guji-cv 仓 `doc/design/拆分-pipeline与manager.md`
- 接口契约：open-guji-cv 仓 `doc/契约.md`；本仓 [COMPAT.md](COMPAT.md) 记每个 manager 版本支持哪些契约
- 调用方式：只通过子进程跑 `guji-cv`（`GUJI_CV_BIN` 指定，缺省 PATH），不 import `open_guji_cv` 内部
- 版本：`m-vX.Y.Z` tag；**不钉到册、不进产物指纹**

## 现状（2026-10-27）

骨架阶段：`guji_manager.pipeline`（调用与兼容检查）、`guji-manager check`。
cv 仓里 manager 一侧的包（`datastore` `jobs` `ops` `console` `review` `snap` `opinions` `exp` 等）还没搬过来，搬迁（设计 M4）等换图源批量收尾、pipeline 的下一个 PATCH 发出后再做。

## 开发

```
pip install -e ".[dev]" && pytest
```

## 已搬来的子命令（过渡期两边都有，cv 自带的优先）

| 子命令 | 来自 cv | 状态 |
|---|---|---|
| `guji opinions` | `opinions/`、`cli_opinions.py`、`config/opinions/rules.json` | 代码已复制进本仓，测试 80 项通过；cv 的 PATCH 删掉后本仓的才生效 |

装法：先装 open-guji-cv，再 `pip install -e .`（本仓经入口点组 `guji.commands` 把子命令并进 `guji`）。

## 搬迁工具

`python tools/move_from_cv.py --cv <cv 检出> --pkg <包> --cli <cli_xxx> --tests <测试>`：复制包（和命令行模块、测试），自动改 import，并列出要人看的 `__file__`／`parents[`／`REPO_ROOT` 用法。只复制，不删 cv 里的。

踩到的坑（下次别重来）：
- 数据文件跟着包走（`opinions/rules.json` 要进 `package-data`，路径改成包内相对）。
- 指向 cv 仓里脚本或数据的 `parents[N]` 要改成 `open_guji_cv.__file__` 推出来的路径。
- `exp`、`snap` 暂未搬：`exp` 的测试用 cv 的 `tests/helpers.py`、`scripts/`，`snap` 的命令 `cmd_snap` 还在 cv 的 `cli_v2.py` 里。要搬先把测试公共件（helpers、conftest 里的夹具）抽成两边共用，或把用到的搬过来。
