# guji-manager

古籍 pipeline 的 **manager**：新建工作区、原图登记／取图、打包上传中心库、R2、任务库等一切与外界的交互。
识别算法（切分、识别、定字）不在这里，在 [open-guji-cv](https://github.com/open-guji/open-guji-cv)（**pipeline**）。

分界线：凡会影响最终识别产物字节的在 pipeline，其余在这里。所以改这个仓**不需要给 pipeline 发版**，也不会让任何一册的产物过期。

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
