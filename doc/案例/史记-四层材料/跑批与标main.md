# 跑批与标 main（SJ 跑批线程，r33–r42 经验，11-12）

## 交单
- **自己直接交单**：`python -m guji_manager.jobs submit <spec.json> [--dry-run]`。
  - 令牌：`gsecrets.py export --names JOBSDB_TOKEN,JOBSDB_PASSWORD` 解密后用，只拿 `[ -n ]` 判断有没有，不打印。
  - 环境变量：`GUJI_REQUIRE_JOBSDB=1`。
- **spec 放书仓 `jobs/rN/<册>.json`**，交单前先提交、推上去。`why` 里写全以下几项：
  - cv、k、g 三个版本；
  - 中心库 rev 下限；
  - base 包；
  - 起跑步骤；
  - 改了什么、出包后要核什么。
- **版本怎么钉**：
  - cv 钉发版 tag（`"cv": "v0.7.9"`）。
  - 书级代码 k 写在中心库 book_defaults 的 `code:`。
  - **执行机只跟书仓 origin/main，单子钉不了书仓 ref**（11-13 r59 教训）：r59 在跑时 A24 把 k9（要 cv ≥0.7.31）合进书仓 main，还没领单的 19、20、39、42 四册检出 k9 后报 BookCodeError 失败；A24 把 main 恢复成 k8 状态后原号重排才过。所以：**新 k 合回书仓 main 必须等本轮所有单跑完**。新 k 先只打 tag，本轮收口后由跑批线程通知收件箱，再由 k 的作者合回 main、排下一轮。新 k 要的 cv 版本还没出 tag 时，也不能先合 main。
  - 字形库 g 写在各册 yaml 的 `glyph_pin`，spec 里同时写 `book_overrides.glyph_pin`。
  - 新开关放到它原有的位置（如 `align_ref.coord_relaxed` 在各册 yaml 里，新开关就紧挨着它），不另加单书开关。
- **从哪步起跑**：取受影响的最早一步，宁早勿晚。
  - 改字形库、对位参数、人裁：从 `glyph_match` 起，十册约 20 分钟。
  - 改切分钉子、行切：从 `row_segment` 起，而且整册重跑，不单跑一页，免得一册出两个包。
  - 改清格（k 号）：从 `cell_shrink` 起。
- **base 写带 job 号的包标签**，用当前 main 或上一轮的包，如 `cv0.7.7-c4-g17-m2-k6-job2057`。
- **改中心库的流程**：
  1. `db pull --force`。**不加 `--no-rebuild`**：11-10 曾因此把旧字形库推上去覆盖了中心库。
  2. 改 yaml。
  3. `db push --no-admit --dry-run`，确认 `glyph_exported:false`。
  4. 真推。
  5. pull 会覆盖书仓 workspace.yaml 的注释，不要把这个改动提交进书仓。

## 通知与兜底（11-11 的教训）
- 任务库的收尾通知，是按 `GUJI_JOBS_WHO` 去花名册找人。
  - r33–r41 交单用的名字是「SJ-跑批线程」，不在花名册里，通知收到 404 后就静默放弃了。
  - 花名册的名字只能英文开头，现已登记 `SJ-batch`（用 `register.py`）。
  - 改名之后 notified_at 有写入，但线程仍然没有被唤醒，原因还在查。
- **所以每次交单都要用 `send_later` 定 60–90 分钟的兜底检查**。到点或收到通知，就接着做：取包、比对、标 main、交下一轮。不要停下来空等。
- **执行机失联**：任务日志里出现「worker 失联，次数用完」，就是这种失败，与产物无关。用同一份 spec 重交即可，再把等待脚本里的单号换掉。

## 缓存（#1414）
- `cache get/warm` 自建 RunContext 时，cv <0.7.7 会丢掉书仓 defaults 的参数，再生的字块可能少偏旁。
- 每次升 cv、换 k，都要清 `cache/<册>/{column_image,column_raw,char_patch}`，并通知 Console 同样升级、清缓存。
- 用缓存字块出的图（清格对比）只能当参考。改字盲读一律用原图按 `bbox_page` 裁，不走缓存。

## 比对口径（图为准）
- `seed_admit` 逐格对 main，分三类：改字（chg）、新放行（newadm）、新退回（newrev）。另外看三项：格数变化、人裁有没有丢、绑定丢失数。
- **盲读**：拼图上只标格号，不给字，先看图认字，再对照参校本和上下文。
  - 判对错的依据是原页图，不是 main 的字，也不是整理本的字。
  - 日曰、己已巳按文意判。
- **抽清格**：从收紧过框的格里固定种子抽 30 格，用对应 k 号取字块，看有没有伤字。
- **切分快筛**：结构类问题要清零，装饰类问题只看计数下降。
- **对照外部清单**：某一轮专门要修的格（如 A31 的 40 格对照表），逐格核有没有纠正过来，没纠正的回给出表的那条线。

## 标 main 的条件
- 改错的格不多于改对的格。
- 没有新出现「main 原来对、现在错」的格。
- 清格没有造成伤字。
- 满足以上三条就直接标（`products pack promote`，`--why` 写清本轮改了什么）。不满足的报总览，不自己下判断。
- 包与 main 逐格一致的册不重标。
  - 例外：对位等中间产物变了，就十册都标，好让 main 的版本统一。
- **标完要做的**：
  - 通知 Console：标签、cv 版本、书仓检出、是否要清缓存。
  - 通知 A23。
  - 在 Jira 卡上写一条。
  - 记台账 `inbox/轮次台账.md`。
  - 写 `rounds/rN/` 汇总。

## 跑批清单（开新书或下一轮照做）
1. 开工先跑 `register.py SJ-batch`（会话换了就重新登记），确认各项令牌都在。
2. 收齐本轮改动（钉子、人裁、参数、cv 发版），问清各线有没有遗漏，最多等 1 小时。
3. 改中心库：pull 不加 `--no-rebuild`，先 dry-run，确认 `glyph_exported:false`。
4. 有新 cv：建 worktree，清缓存。
5. 写 `jobs/rN`，提交并推上去，先 dry-run 一册，再交十册。用 `GUJI_JOBS_WHO=SJ-batch`。
6. 用 `send_later` 定兜底检查。
7. 取包，跑 `cmp` 脚本，看图盲读改字和新放行，抽清格，对照外部清单。
8. 按条件标 main，做标完后的那几项通知。
9. 有失败的单：失联就重交，真错误报总览。

脚本：/tmp/claude/r20s/ 下的 `cmpNN.py`（逐格比对）、`cropsLNN.py`（原图盲读拼图）、`waitNN.sh`（取包循环）、`cleanselNN.py`；清格对比脚本在 `rounds/r37/清格对比脚本/`。这几份已复制到 exp/四层材料/跑批脚本/。它们还没入仓，要复用的话可以收进 guji-manager。
