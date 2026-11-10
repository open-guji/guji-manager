# 换包落 book-text：格号变了（增删格、改号）怎么走

> 状态：**已定，在用**（2026-11-10，sheldon 同意 ZM 的整理：格号变动只走这一条路；殿本 vol15、17、19、20 实跑）。
> 口径以 [待审单-人裁事件-book-text格子](../00-总览/待审单-人裁事件-book-text格子.md) 总纲为准，本文只写**做法**。
> 代码：`guji_manager/swap/booktext.py`；cv `republish.py` 的 `bump_book_text` 遇增删格自动调它。

## 一句话

格号是切分的编号，不是字的身份。新包落 book-text 时，**先按新旧 cord 的框出一张「旧格→新格」对照表，字的取舍和标点专名挪锚都只认这张表**；
不按格号比，也不按文字猜对齐（`auto_remap` 不带 `--cell-map` 会重标改字所在句，切坏专名、丢挂法）。

## 什么时候自动走

`guji swap run`（auto_cycle → proof_cycle → `republish issue/push --book-text`）里，导出的 char 与 book-text 现文**格号集合或次序不同**时，
`bump_book_text` 不再走「待重标清单」，而是交 `swap.booktext.remap_in_repo`，过了守卫就照常升版、本地检查、提交推 dev、出新单。
只换字（格号不变）的册仍走原路；格号不变但有增删字的也交它（cv#1393）。守卫或本地检查不过时 auto_cycle 报 **guard-stop**（旧称 need-A33），线上单不换：切坏的交切分线重出包，锚点挪不了的交 A33，修好后用下面的命令补落、补推单。

## 手动补（已导出、没落成的册）

```
guji swap book-text --books vol17,vol19 -w <工作区> --book-text <book-text 仓> --cv <cv 仓> --push --sheet
```

- 导出缺省取 `reports/<册>/_cycle/` 下最新的 `export/`（`--export` 指定）。
- 在独立 worktree 里做（缺省 `<book-text>-swap`，稀疏检出，每册重置到 origin/dev）：swap run 在共享目录里会 `checkout -- .`，不能混用。
- `--push`：0.x 推 dev；1.x 推 `swap/<册>-1x` 分支，PR 由人或会话开（全流程第七节 C 类通道）。
- `--sheet`：guard-stop 时 auto_cycle 停在推库之前，新单（`reports/<册>/_publish/<rev>`）没换上线；落好文本后补推这张单并 `guji db sync`。网站随下一次发布上线。

## 每册做什么（顺序）

| 步 | 做什么 | 停点 |
|---|---|---|
| 1 | 导出的 char／cord／norm／fig 换进 worktree（char 用 guji-format `dumps` 写，版本号留现行） | — |
| 2 | **对照表**：新旧 cord 按框 IoU≥0.5 一对一配，配不上的同页按中心距再配（同字或同号）；类别 同格／改号／删／新增。格式同 A31 回放脚本、book-text `remap_anchors.py`，写在 `reports/_swap/book-text/<册>/` | — |
| 3 | **逐块图判字**（`resolve.resolve`）：新包 □ 而现行有字 → 保持现字；待审且首选字≠现行 → 保持现字；改出相邻重复字 → 回退；其余机器改字、□ 补字照采纳；新增格照新包 | — |
| 4 | **挪标点专名**：`remap_anchors.remap_data` 按表挪（同格改字刷新校验字，改字落进专名的列复核）；两端都对上、中间插进新增格的专名（語子→語孟子）伸长并列复核；标题前的分段符被整段新增格隔开时，挪到标题前一格（F-OV-12） | — |
| 5 | **守卫**：专名条目 id、条数、类型、挂法与其余字段（entity_id／status／targets／group／decomposition／level／coarse／note）不变，专名不被切短（少的字数不超过锚区间里被删的格数）；标点按 mark／kind／source／pos 计数不变；**人裁账平**（A34 11-10）：有效人裁（旧文本该格正是人裁字）与 char-edits 手改经对照表到新格、按人裁最高判字，旧格被「删」或新包与人裁冲突就停（原先就不同的多为异体／归一，只报） | 不过不写，报 guard-stop |
| 6 | 文本、标点、实体三线升 **patch**，`sync_headings`，`local_check --dev` | 不过不提交，报 local-check-fail |
| 7 | 提交（提交信息含对照表计数、字的取舍计数、复核与留待重标清单、`版本记录:` 行），推 | — |

挪不了的锚点不改不删，提交信息列出，由 closeout 现算成待审格 A01–A03（[标main后收尾](标main后收尾.md)）。
bump 时校验器发现锚点对不上就停（例：vol18 31:3 卷端题名整行新包切成四个 □、框也对不上，交切分线）。

## 合并后收尾（R8）：`guji swap finish-merged`

```
guji swap finish-merged --books vol17,vol19 -w <工作区> --book-text <book-text 仓> [--table <tsv>] [--commit <合并提交>]
```

- **对照表入库**：`swap book-text` 提交前把对照表放进 `<版本目录>/lineage/revisions/<册>-<run>.tsv`（随文本提交走，中心库不另存）。
- **旧格号 redirect**：就是这些对照表。`finish-merged` 沿历次表串成 `reports/_swap/finish/<册>/redirects.tsv`（旧格→现行格，删了的现行格为空），网站链接与意见池里的旧格号按它迁。册1 #419、#436 等更早的增删格没有对照表，补不出来。
- **无锚人裁**（ZM 11-10）：人裁按旧格号挂，改号的格上 iou=0 的 backfill 旧人裁会错位还被优先采信。命令把「对照表里改号的格上的人裁」写成 `republish --recheck` 清单 `reports/_swap/finish/<册>/recheck_unanchored.tsv`，进下一张单让用户重投覆盖；删掉的格（及对照表里没有的人裁格）没有新格号，只在报告里列。
- **度量**：`reports/_swap/metrics.jsonl` 追加一行。
- **票要先落库**：网站已投未落的票须在换包**前**用 `guji cellvotes` 落库；本命令不替做。

## 坑

| 坑 | 做法 |
|---|---|
| need-A33 后新单没上线（线上还是旧 rev） | `--sheet` 补推；或 `republish.py push --book <册> --rev <rev> --yes --no-pack` 后 `guji db sync` |
| 按格号比「新包为 □ 就保持现字」 | 格号挪了会把别的块图的字放回来；只能按对照表比（本命令已做） |
| 失败的册留下改动带进下一册 | worktree 每册 `reset --hard origin/dev` 后再做（本命令已做） |
| `guji db sync` 报要操作人 | 设 `GUJI_ACTOR`（本命令缺省 `swap-book-text`） |
| 推中心库报 StaleBase | 别人刚写过，重跑 `guji db sync` |

## 相关
[全流程与覆盖优先级](../04-反馈迭代/全流程与覆盖优先级.md)（总分析，第六、七节）、ai-team `domain/CV/质检/重跑轮次/标main后自动收尾-方案.md` §6（对照表是一等产物）、
ai-team `domain/文本/殿本实体点校线-经验-11-10.md`（实战记录）、整体整理 `格号变动-综合整理.md`（ZM 11-10，项目文件 `zm/`）。
