# 换包落 book-text：新包与现文本有增删格时的做法

> 状态：试行（2026-11-10，ZM 实体/点校线写；殿本 vol06、13 起实测）。口径以 [待审单-人裁事件-book-text格子](../00-总览/待审单-人裁事件-book-text格子.md) 总纲为准，本文只写**操作**。
> 适用：0.x 册，把新的 ★main 包（如 r9c）落进 book-text，而新旧文本**格序不一致**（有增删格）。1.x 册另走 [全流程与覆盖优先级](../04-反馈迭代/全流程与覆盖优先级.md) 第六节。

## 先分流：这一册走哪条路
`guji swap run --books volNN …` 会替你做「取包 → 导出 → 叠人裁 → 本地检查 → 出单 → 同步」。结果有三种：

| swap 的结论 | 含义 | 怎么办 |
|---|---|---|
| `done` | 单格替换为主，文本、标点、实体都已提交 dev | 完成（`GUJI_SWAP_NO_PUBLISH=1` 时网站未发） |
| `blocked`，原因「旧单 … 还有 N 格的票没落成人裁」 | 旧线上单的票还没落库 | 先 `guji cellvotes draft/write` 把票落成人裁，再重跑 swap |
| `need-A33`，日志里有「新旧文本的格序不一致（有增删字）」 | 增删格，swap 不支持 | **本文的手工路径** |

> `need-A33` 的日志在 `<工作区>/reports/_swap/<册>.log`，细节在 `reports/<册>/_cycle/<rev>/apply.out`；导出在 `reports/<册>/_cycle/<rev>/export/`。

## 前置
1. `guji db pull -w <工作区>`（约 6 分钟，含取图）；`export GUJI_WORKSPACE=<工作区> GUJI_ACTOR=<名字> GUJI_SWAP_NO_PUBLISH=1`。
2. 包里的 cv 提交在浅克隆里可能缺：`git -C <cv 仓> fetch --depth=1 origin <cv_commit>`（`Not a valid object name <sha>^{commit}`）。
3. **手工活在独立 worktree 里做**：`git worktree add -B zm-manual <路径> origin/dev`。swap 在共享的 book-text 目录里遇到 need-A33 会 `git checkout -- .` 清理，会冲掉你同目录的未提交改动。
4. 跑 swap 时用工具的后台执行，不要在命令里写 `nohup … &`（会话结束被杀）。

## 手工路径（每册）
1. **看差异**（只读）：对比 book-text 现 `NNN.char.json` 与导出的 `export/NNN.char.json`：新增格、删除格、改字格。
2. **按总纲规则定每格的字**：
   - 新包为 □（待审无首选字／真阙文）而现行有字 → **保持现行字**，不改成 □；
   - 机器放行的改字 → 采纳（垂／埀录埀等已定口径照办）；
   - 绑定有效的人裁 > 机器；机器想推翻人裁 → 保留人裁字、进复审单（swap 已处理的部分不重复）。
3. **写 char**：用导出的 char，按 guji-format 的排版（一格一行）写回；版本号先留现行值。**cord、norm、fig 整体用导出的**，fig 图有变动的拷图（`fig/NNN/*.png`）。
4. **升版**：`bump_original.py <版本目录> --line text --level patch --chapter NNN --note "…"`（≤50 处逐处改算 patch；整批改字多于 50 处按 minor）。它会打印「版本记录: …」行，**原样放进提交信息**（不再有 CHANGES.md）。
5. **平移标点、实体**：`auto_remap.py <版本目录> --base HEAD --vols NNN --write`。`--base` 要用**改动之前**的提交（先 bump 再 remap，但别提交，`HEAD` 还是改动前）。
6. **守卫（必须做，auto_remap 不会替你做）**：把偏移行（`*offset*`、`span`）和 `source` 滤掉，比较前后：
   - 条目数不变；
   - 实体 `matched` 的挂接不降级、不换挂，`group`、`type` 不变（vol01 #428/#433 实例：梁國治被重标成「國治」、禮部尚書 compound 丢失、內務府被套成「府總」）；
   - 标点只应有标题符／分段符位置修正（F-OV-12），以及 `source` 标签变化。
   有问题的从 `origin/main`（或改动前提交）取原条目，格号 ±n、偏移 ±n 后手工放回，并逐条核对锚点字。
7. `local_check.py --dev` 全过 → 提交（提交信息：标题行 + `版本记录:` 行 + 署名）→ `git push origin <分支>:dev`（推前先 `git fetch origin dev && git rebase origin/dev`）。

## 验收
- `local_check.py --dev` 全部通过；`validate_text_format.py . --strict --baseline scripts/format_baseline.json` 退出码 0。
- 标点、实体 diff 里除偏移和版本号外，只有已解释的差异。
- 提交信息里有每条线的「版本记录」。

## 坑
| 坑 | 做法 |
|---|---|
| swap 的 `need-A33` 不说是哪种原因 | 看 `apply.out` 末尾：「格序不一致」＝本文路径；「锚点落空」＝标点实体问题，走 punct_redo |
| 对导出的 char 整体 `json.dump` | 会改整个文件的排版，diff 爆炸；用 guji-format 的 `dumps`（一格一行）或行内替换 |
| 导出的 char 排版与 book-text 现行不同（多行 cell） | 解析后用 `dumps` 重新序列化；先断言「现行文件 `dumps(load(f)) == f`」 |
| 把 main 合回 dev 时在冲突里 `git rebase` | 会把 merge 提交线性化逐个重放；用 `git merge`，推送用 `git push origin 本地分支:dev` |
| auto_remap 重复跑 | 版本行会重复；先 `git checkout` 回改动前再跑 |
| stop hook 提示未跟踪文件 | 工作区仓里的 `reports/`、`_packs/` 是生成物，不提交 |

## 工具（试行，雏形）
`tools/swap_manual/`：`manual_swap.py`（导出 → book-text 的 char/cord/norm/fig，含「□ 不覆盖现字」规则与格式断言）、`do_vol.sh`（再加 bump、auto_remap）、`batch.sh`（批量，含守卫、local_check、推 dev）。路径写死在 ZM 云会话（`/home/user/bt2` 等），用时改顶部变量。**建议由 A31/A32 评估并入 `guji swap`**（增删格路径 + 守卫），做完本文即可删。

## 相关
[标main后收尾](标main后收尾.md)（锚点待审原因 A01–A03）、[全流程与覆盖优先级](../04-反馈迭代/全流程与覆盖优先级.md)（总分析）、ai-team `domain/文本/殿本实体点校线-经验-11-10.md`（实战记录）。
