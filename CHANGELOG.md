# Changelog

版本号规矩见 `doc/版本号规矩.md`（2026-11-03 起，同 open-guji-cv）。本文件记录**全部**版本（含 PATCH）；动代码的 PR 投 `dev`，在 `## [未发版]`
- PATCH（11-25，CV0，W1 冻结期修复）：`seg_pin.column_basis` 改读 `colview.merged_windows`——cv 切字五小步后 band／trim 在 2b／2c，原先只读 column_warp 的 `column_windows`，换到新 cv 后全部人工指定格钉子的 col_sha 都变、`basis_status` 误报 stale（全唐文切分 11-25 问）。拼回后 sha 与拆步前整份记录相同；column_warp 指纹变仍报 maybe。
 下加一行、写明档位；切 rc 时改成 `## [X.Y.Z] - 测试中`，发版时改成日期。

## [未发版]

- MINOR（11-27，待审清理计划 2.2，新命令）：`guji pending-settle`——待审条目对账。格已落定（同册同 u 有 `levels.settles_cell` 够格的裁定事件）而条目还 open 的，追加 resolved 版本并记 `event` id；按 `(书, 册, u)` 配，不会跨册误配；**复审格（`doc.recheck`）要裁定晚于复审开出才关**；撤下／已关／已裁的不碰；缺省只算不写，`--apply` 写、`--sync` 推回中心库、`--roots` 扫一个目录下各工作区。执行方定时：`GUJI_PENDING_SETTLE_S`（秒，缺省 0＝不跑，只在一台机器上开）。库里 open 数与网站（Worker 读时现算）一致；唯一的差是复审格——网站现在连复审格有旧裁定的也藏掉（11-27 约 128 格），按设计应显示到有更晚的裁定。新增 `review/settle_sync.py`、`cli_settle.py`、`tests/test_settle_sync.py`。L0（只新增命令，不改已有路径）。

- MINOR（11-27，GM4，待审清理计划 1.7，**改出单行为**）：出单入口从 cv 的整张换单脚本迁到 `guji land`。①`online_lists`（标 main 后 `post_promote` 钩子）：不再子进程跑 cv `republish.py issue`／`proof_cycle.py status`，改成「★main 包与 `_land/landed.json` 记的包不同 → 取 main 包 → `guji land <册> --apply`」（land 自己推库、只发有变的册）；去掉「旧单已有票就不自动换」「线上单没存 rev 包也照换」两套 rev 判断，`--audit` 改比 landed 包；book-text 默认不动，`GUJI_AUTO_LAND_TEXT=1` 才加 `--book-text --text-apply`；不再要求 cv 仓。②`guji swap run`：不再调 cv `auto_cycle.py`，每批每册取 main 包后一次 `guji land <这批> --apply`（带 `--book-text` 时 `--text-apply`，`--no-text-apply` 关），册结论 verified／fresh／publish-mismatch／blocked／land-failed；`--ack-unlanded-votes`、`--land-votes`、`--hand-cells`、`--no-single-sync`、`--publish-batch` 保留但不起作用（打印提示）；删 `parse_cycle_log`、`expected_rev`、`wait_live_rev`、`apply_hand_cells`、`_cv_supports_defer_sync`。③`guji swap doctor`：不再要 cv `auto_cycle.py`、不再查各册引擎 worktree，只认 cv 检出里有 `open_guji_cv` 包。cv 侧 `republish.py`／`proof_cycle.py`／`auto_cycle.py` 已标 DEPRECATED（open-guji-cv#1963），本 PR 合入、cv 保留一个版本后可删。

- PATCH（11-27，CV0，册号位数统一第二步）：新工具 `python -m guji_manager.ops.renumber`：一部书的册号改位数（book-text cv 版本的章文件按前缀通配改名、`fig/<章>/`、`index.json` 的 `file` 与全部 `*_file`；数据目录 `feedback/lists/**/<书>/<章>.*` 改名；基础配置 `volume_width` 改、`chapter_width` 删）。缺省只出清单，`--apply` 写回滚清单，`--rollback` 还原；新旧并存算冲突整书不动；已发待审单 rev 不改写。不改任何已有代码路径，L0。脉经 dry-run：5 个改名、2 处编辑、无冲突。

- PATCH（11-27，CV0，册号位数统一第一步）：用户 11-27 定册号位数按全书册数（1–9 册 1 位、10–99 两位、100 起三位），迁移前后 1、01、001 并存，比对册号处改按数值认：`ops/exit_check.find_chapter`（字面没对上再按数值／`n`）、`pending_stats` 非正文页表（`_nonbody_for`，先字面再数值）、`review/vis_review` 取单（`_by_number`）。原来对得上的照旧先认字面，行为不变；`swap.chapter_of` 暂不动，随迁移工具一起改。L0，不碰 cv 指纹。方案：https://claude.ai/artifact/GFATExpvckttdKaHSHRuTz
- PATCH（11-27）：放行格回库事件（`ops/lib_backfill.admit`）的 OCR 通道从 `payload.channel` 改叫 `payload.ocr_channel`，给裁定事件来源 `channel` 腾位置，并写 `level=machine／by=lib_backfill／channel=script`（仍不算钉）；`feedback/consumers._admit_backfills` 重放先读 `ocr_channel`、没有再读老事件的 `channel`，库内证据格式不变。

## [0.6.50] - 2026-11-27

- 发版说明：护栏 `guji eval guard` 云端会话没有书的字形库，**未验证**，已请有真工作区的书线补跑。

- PATCH（11-27，GM4，SJ 报）：点校 AI 摘要对位 `dian_trace.load_notes`／`find_note` 按（册，u）建键并**归一册标签**（去 `vol` 前缀、前导 0：037／37、vol35／035 同册），老行没有 `book` 就用文件名 `<册>.jsonl`；`released_list` 每条加 `book`（u 是册内编号，跨册会撞号，页面合并多册时据此区分）。网站现算侧（Worker pending-live）已同步按（册，u）匹配，见 guji-workspace-data#45。
- PATCH（11-27，CV0）：`guji glyph-db rebind-audit --show-rows` 把非 keep 的行打到输出，任务库 command 单只留 6000 字输出尾巴、拿不到 TSV 时用（只读，行为不变）。

- PATCH（11-27，CV0 线程，清理计划 1.6／1.8／1.4；行为不变，只多 `machine` 一档与新函数）：「算落定」口径只在 `feedback/levels.py` 定义一处——新增 `settles_cell`（confirm＋格＋`SETTLED_VS`＋算钉）、`SETTLED_VS`、`provenance()`（裁定事件来源三字段 `payload.level／by／channel` 的统一取法，校验取值）；`payload.level=machine` 明确不算钉；`web_votes.HUMAN_VS` 改引用 `SETTLED_VS`、`latest_human` 改调 `settles_cell`。`tests/test_event_levels.py` 加四处一致性矩阵（manager／cv／中心库 `events.level` 表达式／Worker `HUMAN_VS`），登记 3 类已知分歧。新文档 `doc/4-反馈迭代/裁定事件写入点清单-2026-11-27.md`（各写入点现不写三字段，只列不改）、`按u配事件审计-2026-11-27.md`（只按 u 配的地方，只列不修）。

- PATCH（11-27，GM3，SJ 报）：`write_notes.py` 状态 released 必须带 `--release-batch`（放行事件批名），摘要文字写「已放行」而状态不是 released 也拦；模板与 wiki 加「放行事件没进库不写已放行」。

- PATCH（11-27，GM3，sheldon 反馈）：AI 判字摘要给用户看的字样一律白话——`dian_trace` 加 `plain_zh`／`jargon_hits`，`dian.why` 不再产出「L2 已(mid)」改「浅层文意判『已』（把握中等）」，`ai` 块 s／d／log 兜底换白话；`tools/dianjiao/write_notes.py` 写入前换、剩内部词报错；新增统一提示词模板 `tools/dianjiao/prompt_ai_analysis.md`（禁内部代号英文、禁自相矛盾、不套别组提醒）。

- PATCH（11-27，GM3，QTW 提）：新增 `tools/dianjiao/carve_pairs.py` 与 `carve_pairs/全唐文.tsv`——各书「按刻形记」的字对不走 AI 放行（按对拦，各书可挂自己的表）。

- PATCH（11-27，GM3，文档）：wiki「AI分析两层做法与待审格摘要」第三节放行标准改为「两次独立判断一致且都高置信即放行」（Sheldon 11-27 晚定，高置信 56/56 对），取代 11-26 易混字组阈值。

- PATCH（11-27，GM2，CV0 采纳执行方建议）：执行方切 cv（`Job.checkout`，eval／command 单）遇「未跟踪文件会被新版本跟踪」时自动让路：只处理 checkout 报出的那几个文件，先带时间戳备份到工作区外（缺省 `~/.guji-jobs/checkout-bak/<UTC 时间>-<pid>/<仓名>/`，`GUJI_CHECKOUT_BAK` 可改），再移走、重切，备份路径进单子事件和 run.log；不整仓 clean，清单里有仓外／已跟踪／不存在的路径就一个都不动、照原错失败。新模块 `guji_manager.jobs.safe_checkout`（也可 `python -m` 用）。准备脚本 rerun_prep.sh 同一规则在 cv 仓。

## [0.6.49] - 2026-11-27

- PATCH（11-27，GM4）：`guji collect --batch` 在「没票、`--no-ai`、批次事件全是只给 u 锚的」时不再算全书绑定表（`current_human`，QTW 004 要 30 多分钟，一格也用不上）。

- PATCH（11-27，GM4）：`guji collect --batch` 对「只给 u 锚、page/col/slot 空」的人裁事件（全唐文寇/𡨥 213、市 98）改按 u 直接在 book-text `*.char.json` 里查格落字（同 u 取批次内最新，查不到或多于一格不落并列出，不用产物核格框）；之前这类事件绑定表判 unanchored 落不进去。新增 `collect.batch_u_cells`。

## [0.6.48] - 2026-11-27

- 发版缘由：网站会员号迁移（voter 36 位 uid → 8 位会员号，旧票带 voter_prev），manager 要先认 voter_prev 网站才能真跑迁移。
- PATCH（CV0 11-27，网站会员号迁移）：网站把会员 voter 从 36 位 uid 换成 8 位会员号，迁移过的票带 `voter_prev`＝原 uid；新增 `voter.voter_ident`（有 `voter_prev` 按它认），同格同人去重、人裁事件「意见来源」、u 回填配票都改用它，迁移前后同一会员的票认成同一人，旧键清掉前不会算两票。
- PATCH（11-27，GM2，汉书 WYG 报）：`cos-check`／close-check 第 15 项抽页时另算摆位分（两边墨迹各落在对方膨胀一格内的比例取小，≥0.95，不放宽），墨迹 IoU 线可由书配置 `cos_iou_min`（或 `--iou-min`）放宽，缺省仍 0.9。汉书小注密的页 1600 宽 IoU 0.88–0.90 是笔画偏粗、摆位 ≥0.986，不是错位。
- PATCH（11-27，CV2）：review-pages `cut_check` 1.4.0：折线卡（项带 `poly`）加「这条线不对」按钮，不拖线也能标错，记 `label=bad`、`bad:["poly"]`；Sheldon 审史記折线页时反映 1.3.0 折线卡只有「看不出」、没法点错。旧项不受影响。

## [0.6.47] - 2026-11-27

- 发版缘由：清退 files——feedback/lists 下 tsv／json 小清单按块进 `file_chunks`（#1130），带上 #1134 与 wiki 更新（#1133–#1140）。PATCH。
- PATCH（11-27，GM2，WYG 请求；用户 11-26 定上 COS 必须是压缩版、压缩是流程一步）：新增 `guji start source cos-tier <书id> <册>`——读页表＋旁车，每张源图出 1-bit 无损 WebP（宽＝`--width`＞书配置 `src_w`＞缺省：文淵閣 1600、其他 3840），过闸（VP8L、只有 0/255、尺寸对）才传 COS `srcbw`，传完记只增不改的账 `r<NNN>.cos.v<K>.json`（实际宽度、对象 md5、每页 `bim:cos`）；`--adopt` 给网站仓脚本已传的册补账。新增 `guji start source cos-check`（账、对象数、线上抽查、墨迹 IoU≥0.9），并进 close-check 第 15 项（两档都计；没有页表指针的册 skip）。代码 `datastore/cos_tier.py`，原网站仓 `ops/iiif/src_bw_tier.py` 等三支脚本的逻辑搬进来。
- PATCH（11-27，GM4，清退 files）：`feedback/lists/` 下的 `.tsv`／`.json` 小清单（stale_verdicts.tsv、known-errors.tsv、opinions 老的 text_versions.json）按块进 `file_chunks`，往返逐字节同，不再占 files；本机文件照旧，cv 读法不变。

## [0.6.46] - 2026-11-27

- 发版缘由：`guji land --text` 刷新导出参数错误（MJ 11-27 报，非殿本都会碰到）。

- PATCH（11-27，GM2，MJ 报）：`guji land --text` 刷新导出改调本包 `output/guji_format_export`，参数同 cv `republish.py from-pack`（char-cord、`--keys cv`、book-text dev 现行 `--text-version`、`--meta`、`--prev-char`）。原拼 `guji export format <册> -w …` 在 cv 0.9.7 吃不到册后参数、非殿本无 meta 退出、也不出 char.json。

## [0.6.45] - 2026-11-27

- 发版缘由：补 0.6.44 漏收的一张 proofing 单，让 files 里 proofing 行清零。
- PATCH（11-27，GM4，清退 files）：`proofing/**.pending.json` 逐行进不了 `list_rows` 的（缩进多行、单行超限）一律进 `file_chunks`，不再按大小判（原先只收 ≥0.9 MB，北行古本、99k3i35yww 三张里漏了 633 KB 那张）。

## [0.6.44] - 2026-11-27

- 发版缘由：史記 11-26 回库贴错图的防再犯与补救（#1105）；带上清退 files 的 #1120、#1122、#1124（含新表 `file_chunks`，库与 Worker 已先上线）与 #1123。
- PATCH（11-27，CV3，史記回库贴错图 #1105）：`glyphdb_admit` 本机没有该页现行切分产物时不再按事件原键取字块缓存（缓存是现行切分、事件键是裁决当时的，换过切分的页取到邻格）：`_bindings_lookup` 返回 None，默认不取图不进库、计 `res.no_products`，`GUJI_ADMIT_NO_PRODUCTS_OK=1` 放行旧行为。新增 `guji glyph-db rebind-audit`：窗口内人裁回库例按 cv `book_bindings` 分 keep／rebind／withdraw（默认只读出 TSV；`--apply` 缺省只执行 withdraw，rebind 须 `--include-rebind`，须 `--confirmed-by` 与 `--undo-file`，`--undo` 回退）。
- PATCH（11-27，GM4，清退 files）：`feedback/candidates/*.jsonl` 与 `feedback/*.jsonl`（promote、抽样裁定等零散台账）逐行进 `list_rows`（dataset=candidates／feedback_misc）；非 jsonl（tsv、json）仍整文件。

- PATCH（GM3 11-27）：放行格也能在网页看 AI 分析——`dian_trace.released_list` 取 notes 里最后一轮 `status=released` 的格，出 `[{u, ai}]`；`dian_attach` 加第 4 个参数写出该文件，ai-team `pending_list.py --released` 并进待审单顶层 `released`。顺带修 `dian_for` 没把分析状态 `st` 带进 `ai` 块的缺口。
- PATCH（11-27，GM4，清退 files）：新表 `file_chunks`——超过 D1 单行上限的整张待审单（`proofing/<册>/<章>.pending.json`，目前北行古本两张）按 30 万字符切块进库，`source_files.tbl='file_chunks'`，还原直接拼块；不再占 files。需先建表（guji-workspace-data 迁移 2026-11-27-file-chunks.sql）、部署 Worker，再发版。
- PATCH（11-27，CV0，参校本 D 块）：人审原因 `_ref_by_design` 认册配置 `reference_profile` 声明 none 的页（align_ref `ref_kind: none`／备注「本页无参照（配置）」）——这些页没有对位字是设计，不再判 S01 seg_page_unaligned／S02／R02 ref_gap，落字形类；声明 text 的页不变。
- PATCH（11-27，GM4，清退 files）：意见池 `text_versions.json` 改存 `text_versions.jsonl`（一行紧凑 json，进 `list_rows`）；读时老名字仍认，写时换新名。

## [0.6.43] - 2026-11-26

- 发版缘由：AI 分析摘要进新表 ai_notes（#1103），待审单带 ai 对象；notes 按 册+u 挂。

- PATCH（CV0 11-27，网站 #924 会员票）：登录会员的 voter 是 36 位成员 uid（UUIDv7），开头是毫秒时间戳，前 6 位同一阵注册的会员会撞；新增 `guji_manager/voter.py` 的 `voter_tag`：UUID 形取去连字符后的后 16 位随机段，匿名 16 位原样。意见 id 尾巴、刷票同源、去重、人裁事件「意见来源」、u 回填配票都改用它；隐藏单对公开短标识也认。匿名票的 id 与事件文字不变。网站公开 `who` 要用同一规则（`voter_tag(voter)[:6]`）。
- PATCH（11-27，CV1，QTW 报误报）：`seg pins-stale` 对有 geom 的钉子，几何字段变了时改按钉子框在新旧列图间的实际最大位移判（用 cv ColumnMapper 换算，cv ≥ v0.9.6），≤3px 记 ok（同 cv 换算送人核门槛），stale 说明里带位移。全唐文 ms4→ms5（outer_bar 开→关）4 列误报（032:69:1、046:87:1、053:76:8、060:3:3）属此类。旧 cv 退回只比字段。

- PATCH（GM3 11-27，新表 ai_notes，同 pending_items 先例按 PATCH）：AI 分析摘要（`feedback/notes/<册>.jsonl`，浅层、深搜、放行与不确定都写）逐行进中心库新表 `ai_notes`（原归 `files`），模式同 `pending_items`／`list_rows`：book 取行里的册、u／batch／char／conf／st（trace 最后一轮 status）等是由 raw 现算的虚拟列（schema 与 CV0 迁移一致），索引 `ai_notes_u`；非 json 行的文件退回 files。**D1 要先建表（schema_d1.sql 的 ai_notes），再升 manager。** notes 行加顶层 `st`（released／pending／unsure）；摘要三层：一句话 `s`（≤40 字）、详情 `why`（≤300 字）、检索记录 `log`（[{src,r,t}]，检索过的都写，含查无）；`summarize_trace` 出 `ai` 对象，待审单卡 `ai` 字段（网站折叠显示）；`write_notes.py` 新列（一句话、详情、检索）。
- PATCH（CV2 2026-11-26）：`review-pages ab-items`：切分 A/B（两份 row_segment 产物）只收切法变了的列，出 col_check items——框＝新切法、红线＝旧切法被换掉的线；`--flag boundary_net` 只收判官改过的列。原是 ai-team 一次性脚本（字间判官 72 列审查页）。

## [0.6.42] - 2026-11-27

- 发版缘由：身份账切回旧切分的页入账 id 撞旧行、推库被拦（全唐文 031–060 首发卡住）。PATCH（CV0 11-27）：`Ledger.append` 撞号自动加 `-r<n>`；`uid sync` 推库前把本地已写出的重复 id 改名再推；新增 `guji uid dedup-ids <册> [--write]`。从 main（v0.6.41）切出、只收这一个修复（dev 上未发版的含一个要先建 D1 表的 MINOR，不夹带）。

## [0.6.41] - 2026-11-27

- 发版缘由：整张待审单进 list_rows，清退 files。PATCH（11-27，GM4，清退 files）：整张待审单 `feedback/lists/proofing/<册>/<页>.pending.json` 改进 `list_rows`（dataset=proofing，一行一个 json 对象，逐字节还原）；单行超 1.8MB 的整份仍留 files（正文走 R2）。

## [0.6.40] - 2026-11-26

- 发版缘由：铺底后清人裁绑定缓存改按本单环境下 cv 解析的产物根／人裁根（#1095）——中心库工作区的绑定缓存在 `~/.guji-data/<分支>/<ws>/feedback/`，v0.6.39 按 `<工作区>/feedback` 清会扑空（史記 03 worker-46 疑案）。PATCH。

## [0.6.39] - 2026-11-26

- 发版缘由：执行方铺底清本册人裁绑定缓存与切分旧备份（#1088，11-26 史記 03 #17918 在 worker-46 上把 16 格没锚框的旧人裁落成 human）；cancel 收 blocked。均 PATCH。

- PATCH（11-26，GM2）：执行方铺底后清这一册的本机派生物——`feedback/bindings/<册>/`（人裁绑定缓存，只按切分 sha＋事件签名判新鲜、不含算法版本）、`products/<册>/<步>.bak-*` 与 `<步>/_prev`（绑定拿它们找旧框）；存包不再打进 `<步>.bak-*`。缘由：11-26 史記 03 #17918 在 worker-46 上把 16 格没锚框的旧人裁落成 human，别处复算是 unanchored（本机残留）。绑定缓存本就不进中心库（scope 不收），清本机即可。不动 cv 产物，L0。
- PATCH（11-26，GM2）：`guji_jobs cancel` 也收 blocked 的单（依赖没成功、等人处理），照常记事件和操作人；原先只收 queued／running，CV0 撤钉弃用 cv 60ec7603 的 6 张 blocked 单只能直接改库。L0。

## [0.6.38] - 2026-11-26

- 发版缘由：钉子护栏收尾——`seg pins-recheck` 无几何底老钉子批量重核补 geom、`pins-stale` 报「未生效」（#1085，CV1）；新待审原因 `manual_cells_remapped`（S05，读 row_segment 列旗出卡）与 wiki（#1086，GM2）。配 cv ≥ v0.9.6。均 PATCH。

- PATCH（11-26，GM2，配 cv v0.9.6 钉子护栏）：wiki 切分检查与优化补「标 main 前跑 pins-stale」「升级后跑一次 pins-backfill-geom」；新待审原因 `manual_cells_remapped`（S05，钉子换算待核，一定人审，ui=confirm，priority 9）。cv row_segment 列旗 `manual_cells_remapped`（钉子按 geom 换算、角点位移 >3px）的列：出卡（`review.cards`）与按包现算（`reasons.book_cells`）都把这一列的格捞回待审（放行了也算），挂 doubt `manual_cells_remapped`。网站按 `pending_reason` 显示，不用改。不动 cv 产物，L0。
- PATCH（11-26，CV1，CV0 批）：新命令 `seg pins-recheck <册…> [--write]`——没记几何底的老钉子在现行列图上逐条核（生效、在图内、不压墨、不跨两字、格外无墨、cell_shrink 同号字格；判据复用 cv seg_pins_check），全过补 geom，不过的列清单人核／重钉（退出 3）。`seg pins-stale` 另报「未生效」（钉子改了而该页 row_segment 没重跑，按格比，不比时间；GM2 提）。全唐文 053 实测 30 条：通过 15、不过 4（正是 outer_bar 错位的 76:4、76:5 等）、11 条本机没产物没核。不动 cv 产物，L0。

## [0.6.37] - 2026-11-26

- 发版缘由：钉状态流写入口 `guji pinstate`（#1082，配 cv #1930 的 pin_removed）。
- PATCH（GM4 11-26，待审与裁定整理）：新命令 `guji pinstate remove|expire|reactivate`（`pin_state.py`）：写 `feedback/pins/<册>.state.jsonl`（事件形状，payload 带 v／pin_id／book／reason／level／by／at／events），cv #1930 的 pin_removed 读它；`datastore/scope.py` 把这类文件归入 events 表（stream=pin_state）、随 db sync 进中心库（`voids` 视图并入）。

## [0.6.36] - 2026-11-26

- 发版缘由：拉取还原逐行文件时行号空洞＋超出 n_lines 但紧排 sha 对上就还原（#1079，殿本 vol01 卡住 ZM 推库）。PATCH。

- PATCH（11-26，GM2）：拉取还原逐行文件时，库里行号有空洞、末尾又超出 `n_lines`（导入删行不重排行号），但行数对上的，按行号紧排、sha 对上就用，不再报「库里有超出 n_lines 的行」（殿本 `instances/vol01.jsonl` 11-26 卡住 ZM 推库：空洞 8789／12708／12709，超出 14658–14660，紧排后与登记逐字节相同，库里数据没坏）。紧排对不上仍报错。L0。

## [0.6.35] - 2026-11-26

- 发版缘由：待审单给形近字组的组内全部字出选择按钮（#1075，配 cv #1921）；GM3 AI 分析摘要进待审单（#1072）；钉子几何底 geom（#1071）；layer_u 并账后重盖（#1073）。均 PATCH。

- PATCH（11-26，GM2，CV4 cv #1921 配套）：待审单给形近字组的组内全部字出选择按钮。卡上新增 `grp`（`{id, m:[字…]}`，读 Step7 `evidence.group.members`，`review/group_members.group_of`），`proof_fields` 写进 pending.json 新字段 `grp`；相似字 `alt` 把组员当近似字、并保证每个组员都在 alt 里（缺的补进去，`src=grp`，照旧按图排序，超 30 个从尾部丢非组员）；点校摘要把组员算作候选（判出的组员字当倾向字），仍在候选外的高／中把握字写成新字段 `dout`（网页当可选按钮、不预选；GM3 11-26 定候选外的字人审可直接选）；终审页 final_review 先读产物 members、没有再退回字组注册表，有 members 时每个组员都出按钮。旧产物没有 members：不出 `grp`、alt 与点校候选照旧。网站显示 `grp`／`dout` 由 Web 接，不接也能从 alt 点到组员。不动 cv 产物，L0。
- PATCH（GM3 11-26，AI 分析摘要进待审单）：点校旁路 notes 的查证摘要 `dian.why` 上限 200→400 字（`dian_trace.WHY_MAX`、`proof_fields.CTX_WHY_MAX`），notes 新增按（册，u）挂（`load_notes`／`find_note`／`dian_for` 加 `book`、`u`，`dian_attach` 读卡上的 `book`、`u`）；新脚本 `tools/dianjiao/write_notes.py`（TSV→notes，放行、未放行、判不了都写）。新规：无论浅层或深搜、确定或不确定，AI 分析（判为何字、理由、出处、置信）都要写进 notes 并随待审单出；裁定库 `why`（cv 限 60 字）只作一句话。网站显示 `ctx.why`／`dnote` 不变，只是可能更长（已知会 Web）。
- PATCH（11-26，CV1，CV0 批的钉子护栏第一步）：整列钉子写入时在 `input.column_basis` 另记几何底 `geom`（页宽、左右边线六项、矫正上下界、ruled，即 cv ColumnMapper 的全部入参；见 doc/参考/钉子上游底.md）；`seg pins-stale` 对有 geom 的钉子只比 geom。新命令 `seg pins-backfill-geom [册…] [--write]` 一次性给老钉子补 geom（只补现行列窗与当时 col_sha 一致的）。缘由：全唐文 031–060 outer_bar 把直线页变三段、列图挪了 10–32px，人钉坐标照旧套用切偏，pins-stale 不在管线里且比整条记录会误报。不动 cv 产物，L0。

## [0.6.34] - 2026-11-26

- 发版缘由：意见采纳写裁定事件（`opinions revise --write-events`，#1062／#1065）；db push 缺省不推字形库、全量扫描 --allow-delete 删得掉本地删掉的文件（#1061）。

- PATCH（CV0 11-26，配 GM4 意见采纳写事件 #1062）：意见采纳写的裁定事件改用现成的 `payload.no_glyph_lib`（审查卡「这张图不建库」的老标记，`glyphdb_admit` 与重建后重放都认：算已裁、不进库），不另造 `no_glyph`。原 `no_glyph` 没有任何消费者认，重建后重放还只认 `book_lib_sync gated` 记账，会把这类事件重放进库。
- PATCH（GM4 11-26，待审与裁定整理第 6 步）：`opinions revise --write-events`（缺省关）：真写 book-text 后对每个改字／新增格写 confirm 裁定事件（payload.level 明写：用户采纳 human／规则自动采纳 ai；锚直接带 u、bbox、cells_sha、有则 content_sha；B′ 新格 u 不在现行切分账里就只留文本不写事件；payload.no_glyph_lib 让字形库重放跳过；batch `opinion-<册>-<章>-<日期>` 不带「~」）。另修：revise 改 A／B 类格时 CELL_KEYS 漏了 `u`，会把 v0.6 char 格的 u 丢掉。

## [0.6.33] - 2026-11-26

- 发版缘由：`guji uid retire-into` 并账（#1059，ZM 殿本列末切矮格）。
- PATCH（11-26，CV0，ZM 殿本列末切矮格）：新命令 `guji uid retire-into <册> 旧u:新u … [--why …] [--write]` 并账——重切后旧 u 记了 gone、新格另发了号，看图确认是同一格时，把旧 u 改记为并入新 u（册级一行 page=0，不动各页上一份／当前一份）。换单对照表（账内 `u_table`、book-text `cell_table_by_u`）把并进去的旧格当同格／改号接到新格，人裁、标点、专名跟过去，不再报「在新包里没有对应格」。新包 char 要在并账后重新导出（`u_retired` 才带 into）。

## [0.6.32] - 2026-11-26

- 发版缘由：执行方 0 页记成功修复（#1056，11-26 全唐文 055 #17657 空跑存假包、#17802 因此全册上游缺失），要执行机尽快跟上；标 main 拦空跑包（#1058）；#1055 一并发。均 PATCH。

- PATCH（11-26，GM2，#1056）：任务库执行方——`--pages all` 而各步全是「0 页」判失败、不存包（原先记成功并把底包原样换名存包）；同会话跳过准备前先核本机原图 `data_full/<册>` 还在，没了就重新准备；各步第一条失败／阻塞页原文写进日志、任务结果 `first_failures` 并带进 job.error（全页失败时日志尾巴只剩最后一步的阻塞行）；被叫停的单 error 写明谁叫停（取最近 cancel 事件，如「QTW 要求停下」）。不动 cv 产物，L0。
- PATCH（11-26，GM2，#1058）：存包时本册产物与上次取的铺底包摘要一致（取包后一页没跑）就在 manifest 记 `unchanged_from`，`pack promote`／`push --main` 见到它拒标 main（给 `--why` 照标并记进指针）。缘由：执行方空跑 0 页仍存包，旧包换名后被标 main（11-26 全唐文 055、史記 11/28/31/34）。只拦新存的包，已有包不受影响。不动 cv 产物，L0。
- PATCH（11-26，ZM，#1055）：swap booktext：换过图源的书 fig.json 的框跟 cord 对齐（F-OV-13，殿本 vol19）。

## [0.6.31] - 2026-11-26

- 发版缘由：corpus 缺省号认运行覆盖（#1051，修 #1006 回归：执行机 rerun 单带 corpus 覆盖时语料校验读裸册 yaml）；待审清单 jsonl 逐行进 list_rows（#1052）。按用户「先升 PATCH」，cut_check 1.3.0（#1050）一并按 PATCH 发。

- PATCH（11-26，GM4，files 清退路线第 1 步，ai-team `domain/GM/GM4/files表清退路线-2026-11-26.md`）：`feedback/lists/{web,opinions,freeze,ledger,u_void}/…jsonl` 不再整文件进 `files`，改逐行进新表 `list_rows`（主键 (ws, src_path, src_line)；列 dataset、book、name，id、u 由 raw 现算）。清单里有不是 json 对象的行，整文件仍进 `files`（scan 报问题）。拉取、`db verify` 照旧逐字节还原／核对（verify 认 `source_files.tbl`）。`central_gc` 读冻结登记改为 files 与 list_rows 都读（迁移期两处都可能有）。线上要先建表、Worker `/v1/files` 要认新表（guji-workspace-data 另一 PR）；各机升级后全量推一次把已有文件挪过来。L0。

- PATCH（11-26，GM2）：`guji corpus verify／upload／fetch` 不写 `--version` 时，缺省号改读册的**生效配置**（合基础配置与运行覆盖 `GUJI_BOOK_OVERRIDE`），原先只读裸册 yaml（#1006 引入）——rerun_prep 换语料号走覆盖不改 yaml，「语料校验」便核成 yaml 里的旧号（11-26 #17727 殿本 vol03：覆盖 20、核成 19，报 CorpusDrift）。合不出生效配置才退回裸 yaml、再退回钉子账末行。不动 cv 产物，L0。
- MINOR（11-26，CV2）：review-pages `cut_check` 1.3.0：项可带 `poly`（图内像素折线），卡片上画可改的折线——拖点、点空白加点、双击删点，改过记 `label=fix` 并存 `poly`，`cutcheck-apply` 导出带 `poly`；用于 L3 折线金标人直接改线。旧项不受影响。
- PATCH（11-26，GM2）：`guji db status／sync／push` 不再把本机不存在的 `workspace.yaml` 当成「未推」改动（SJ 报：它是工作区仓里的身份文件，base 里有、本机缺时原先算成删除）；推送扫描时缺它直接说明「-w 指对了吗、先在工作区仓 git pull」，不再 FileNotFoundError。不动 cv 产物，L0。

- PATCH（11-26，GM2）：任务库 `reap` 修——在跑的单已被要求停下（cancel_requested）后执行会话失联、租约过期，原先退回排队、又被别的执行机领走白跑；现在记 **cancelled**（D1 与 PG 两种写法同改，事件「失联，已有人要求停下，记取消」）。11-26 全唐文 061–120 撤单后 #17696／#17701／#17704 又回到 queued 即此。另：`guji job submit／cancel／bump／retry` 没设 `GUJI_JOBS_WHO` 时提醒一句（否则署名记成主机名，云会话都是「vm」，事后查不出是谁）。不动 cv 产物，L0。

## [0.6.30] - 2026-11-26

- 发版缘由：待审条目逐行进 pending_items 表（#1045）。

- PATCH（11-26，GM4，待审与裁定整理方案第 4 步）：待审条目 `feedback/lists/pending/<书>/<章>.items.jsonl` 不再整文件进 `files`，改逐行进新表 `pending_items`（一行一个版本，主键 (ws, src_path, src_line)；列 item_id、ver、book、vol、cell、state、op、src、actor、at、why、recheck，u 由 raw 现算）；视图 `pending_current` 取每条最后一行。拉取按 `source_files.tbl` 逐行拼回，文件逐字节不变，工具不用改。`source_files` 对改归 pending_items 的文件指纹带表名，内容没变的文件推一次也会改归。线上要先建表（guji-workspace-data 迁移），各机升级后首推会把已有整文件行挪过来。L0。

## [0.6.29] - 2026-11-26

- 发版缘由：事件级别统一口径 feedback.levels（#1042）。
- PATCH（11-26，CV0）：事件级别统一口径（GM4 批量规则）。新模块 `feedback.levels`：`event_level`（先认 `payload.level`；无则 actor≠model 算 human，actor=model 按批次名 `~` 前缀查 9 个人授意批次，其余算 ai）、`counts_as_pin`（human 或 ai＝原 cv `counts_as_human` 的集合）、`counts_as_human`（只认 human）。字形库入库、已裁、对勘状态、近似字、插图、冻结计数、人裁冲突、u 迁移改用 `counts_as_pin`，行为不变；llm 在线准确率真值、rough_bench 标签改用严格的 `counts_as_human`，AI 钉不再当人裁真值。不经 `_cv`，钉 0.7.x 的执行机同口径。L0。

## [0.6.28] - 2026-11-26

- 发版缘由：换单开待审条目自动盖 u、uid items-u、check-u 报活条目没 u（#1039）。
- PATCH（11-26，CV0）：`guji pending reconcile／import` 换单开条目时按字格身份账自动盖 u（`u_stamp.u_map_lenient`，账里缺格的不挡、报一行）；史記第二轮复审 r2 换单开的 304 条、总目 9 条原先没 u。新命令 `guji uid items-u [册…] [--write]`：活条目没 u 的按账补（追加 op=u-fill 一版）。`guji uid check-u` 加报「活条目没 u」（只报，不计入退出码）。

- PATCH（11-26，CV2）：review-pages `cut_check` 1.2.0：`build --box N` 定卡片图高（px，缺省仍 220），一屏多放几格（Sheldon 看 L3 折线页 11-26 要卡片小些）。旧页、旧结果不变，L0。

## [0.6.27] - 2026-11-26

- 发版缘由：`db --only` 多路径（#1035）。
- PATCH（11-26，CV0）：`db pull/push/sync --only` 一个 `--only` 后可跟多个路径（原先 `--only A B C` 只认 A，B、C 落进位置参数被静默丢掉，全唐文救回人裁的 ~u 抄件因此漏推）；pull/push/sync/status/diff/migrate/init 收到多余位置参数直接报错。

## [0.6.26] - 2026-11-26

- 发版缘由：推库闸（#1031）与 u 收口先用 cv 绑定认格、u_void 撤销（#1032）；救回全唐文 56、史記 5 格误作废人裁。
- PATCH（11-26，CV0）：推库闸拦「册有字格身份账却没带 u」的新事件（格级人裁 `anchor.u`、按格裁定 `payload.u`；不经 manager 写的会绕过 append 前盖 u，史記「歲暫歸一」批 22 条）；`GUJI_DB_ALLOW_NO_U=1` 放行。新命令 `guji uid stamp <事件文件> [--write]`：按身份账给锚在同一份切分上的行就地补 u。`uid migrate-plan` 不再把 u_void 里记过作废的裁定、人裁抄回来。
- PATCH（11-26，CV0）：u 收口误作废了「整列平移」的人裁（cv 按锚框顺移绑对了格、字与 book-text 同；全唐文 56、史記 5 格，T3 核出）。`uid migrate-plan --close` 先用 cv 绑定认格（`book_bindings`→`usable`，valid／rebound 的现格号在账、字同或异体、u 没被占 → 认这格 u），认不上才走异体／列内近邻／作废；`--bind-products` 指现行 main 包产物，`--no-bind` 关。u_void 新记档 `kind=u_unvoid` 撤销同 id 之前的作废／转待审（`u_migrate.unvoid`：抄 `~u` 件带锚档、记撤销、撤下这些人裁转出的 recheck 条目）。

## [0.6.25] - 2026-11-26

- 发版缘由：只动文档，合 main 让 Wiki 同步（#1028）。`doc/参考/字格身份账.md` 按 v0.6.24 重写；Wiki「字格永久编号 u 与身份账」重写（加史記 18 截图、常见问题），全流程、换单、收单、投票页改讲 u。

- PATCH（11-25，CV0「字块随包存 R2」，用户 11-25 定；要 cv 带 `core.derived.PAGE_FETCHER`（cv #1899），旧 cv 不装、照旧现算）：新 `datastore/patch_packs.py`。一页 `char_patch` 打一个 tar 存 `derived/patch/<ws>/<册>/<页>.<链指纹>.<日>.tar`（链指纹＝cell_shrink 及全部上游这一页指纹的合哈希，切分变了才换键、只重打变了的页）；`guji cache push-patches`（执行机 rerun／ab 单存产物包后自动跑，`GUJI_PATCH_PUSH=0` 关，失败不挡单）；启动时注册取件器，识字、定字缓存缺页时整页取回、逐文件核 sha 与戳（`GUJI_PATCH_FETCH=0` 关）；`guji cache gc-patches` 每页留最新那天＋7 天内，缺省只列、`--apply` 才删。
- PATCH（11-26，GM2）：步内分段计时跟上 cv #1911（seed_admit 拆出 seed_admit_common／lanes／shapes，纯搬家）：`PERF_HOOKS` 加 `seed_admit_common._page_patch`，否则字块读取一段计不到（各处改经 `_C._page_patch` 调）。旧 cv 没这模块自动跳过。`tests/from_cv/test_code_deps_coverage` 的 NOT_IN_FP 死条目检查认 import 搬进 seed_admit helper 的（stroke_veto／wu_shape 等，新 cv 上 dev CI 原先红）。不动 cv 产物，L0。
- PATCH（11-26，GM2）：步内分段计时跟上 cv #1911（seed_admit 拆出 seed_admit_common／lanes／shapes，纯搬家）：`PERF_HOOKS` 加 `seed_admit_common._page_patch`，否则字块读取一段计不到（各处改经 `_C._page_patch` 调）。旧 cv 没这模块自动跳过。不动 cv 产物，L0。

## [0.6.24] - 2026-11-26

- 发版缘由：身份账有字旧格不配给空格（#1018，主线程 11-26 定）。
- PATCH（11-26，CV0）：身份账入账时有字旧格不配给空格（`uid.match` 第 0 条；`source.from_products` 把字块里没墨的格标 `c=""`，book-text 认领同口径）。只影响以后的 advance，已发出的 u 不改。史記 18 p2 旧「唐」u33 曾按框配给列首新切出的空格。

- PATCH（11-26，GM2）：`guji corpus verify／upload／fetch --vol` 不给 `--version` 时，总号缺省取**册 yaml 现钉的 `corpus:`**，yaml 没写才退回钉子账末行。钉子账只追加，末行可能是撤掉没用的号（W1 试跑后殿本、史記各册账末行 b35、yaml 已指回原号），原先会核／传错版本。COMPAT.md 记 0.6.22–0.6.23：cv 下限不因 W1 提高（原 #1006 想提到 0.9.2，用户 11-25 16:31 定已出 v0.1 的书不重跑、留在旧 patch 线，故撤）。不动 cv 产物，L0。

## [0.6.23] - 2026-11-26

- 发版缘由：char-cord 导出保 u 连续（#1015，史記 18 卡 local_check 丢 u33）。
- PATCH（11-26，CV0，W1 冻结期修复）：char-cord 导出保 u 连续——参考 book-text 现行同章 char（缺省自动找，`--prev-char` 指定、`--no-prev-char` 关），旧版格里有、本次没导出、作废表也没有的 u 补进 `u_retired`（gone，不复用），旧版作废的照抄；本次格里又出现旧作废 u 时警告。史記 18 卡 local_check：p2 列首新切出空格，身份账把旧「唐」u33 按框给了空格、导出丢格，u33 悬空。`uid.booktext` 加 `load_raw`。

## [0.6.22] - 2026-11-25

- 发版缘由：swap R1 闸放过身份账已作废格的刻例（#1010，W1 重切后换单带 --glyph-db 不再被拦）。

- PATCH（11-25，CV0 u T1）：`guji swap book-text --glyph-db` 的 R1 闸不再把**身份账已作废格**（旧包 u 在新包 `u_retired` 里，gone／into）的刻例算 orphan，只计数（`retired`，写进 R1 说明）。重切删掉的格本来就是库 id 留原键、读时由 cv `bindings.rebind_library_shapes` 按裁决事件换现格，不该改键；原先 W1 重切后带 --glyph-db 换单会被 r1-stop 拦。没作废却不在新包的格照旧拦。
- PATCH（11-25，CV0）：耗时统计跟上新步骤。`guji perf top`（本机与 `--remote`）按 cv 四大步（版面／切字／识字／定字，取自管线骨架 `stages:`，闸归它挂的那一步）分组；`--remote` 先列任务阶段（prep／run／push／uid／recheck…，取自任务库 event），prep 再拆分段（执行方从准备脚本「== 准备耗时」解析，记进事件 `data.prep_parts`）。新 `guji perf spans <步> [--remote]` 看一步的分段排行。步内分段名单 `PERF_HOOKS` 补第三轮：row_segment（segment_column、U-Net 判官各方法、layout_for）、column_band（band_strip）、cell_shrink、rare_candidates（rare_for_batch、CNN 批量、笔画重排）、`RunContext.image`／`raw_page`，另按 STEPS 自动给每个有 `render` 的步套壳，冷缓存再生（`<Step类>.render`）单独可见并在 top／spans 里小计。跑测试时不再往正式任务库推耗时（11-18 起有 cv／manager 测试的合成步 t_step_a 等进了 D1）。不动 cv 产物与指纹，L0。
- 文档（11-25，GM4）：wiki「换线上人审单」加第零节现行口径——`guji pipeline … --text-id` 默认收尾并写回（#1004），出包不再单独换包／换单；裁定键放宽与 `u`、`ruling_anchor_loose`、收单自动、仍要手工的兜底。只改文档（L0）。

- PATCH（11-25，CV0）：跟上 cv 切字五小步（cv #1869／#1872）的产物布局。新 `guji_manager/colview.py`：`merged_windows` 把 2b `column_bands`、2c `column_ends` 拼回列窗口（列端分档批 `label-batch column-end` 原先读 `column_warp` 拿不到 trim 直接崩）；`read_gate`／`read_gate_raw` 出口闸先读 `cut_gate` 再退回 `column_gate`／`row_segment_gate`（border_cards、页型对账 table_cols、seg_causes、overlay 用）。页型对账的 `table_cols` 也认 `column_geometry:` 下的写法。测试：四条 from_cv 用例按新步列表改；`test_code_deps_coverage` 登记 cut_gate 借常量的两处 import（另两处由 cv #1882 补进 code_deps）。不动 cv 产物，L0。

## [0.6.21] - 2026-11-25

- 发版缘由：char 导出作废号 into 目标不在本章时降成 gone（#998，史記 01 换单被 book-text 拦）。

- PATCH（11-25，CV0 u T1）：char 导出时作废号 `into` 的目标 u 不在本次 char 里（身份账有、产物没出这格：空列、插图块占掉等）→ 降成 `{u, gone}`，char 对外不留悬空引用，号照样退役不复用；降了几条打到导出日志（报告 `u_retired_dangling`）。史記 01 8 条（如 01:12:4:1–8:1 空列）在 book-text bump_original 被拦，修后实测通过。按本地产物粗扫，殿本 vol01／14／20、史記 02／09／14／23／27／30／35／41 也会碰到，下次导出自动降级；book-text 现有 char 无悬空。L0。

## [0.6.20] - 2026-11-25

- 发版缘由：史記线上待审单换新卡点（#995）：导出器配老 cv 不崩、带 u 的 char 保持 v0.6、无 rev 包旧单照换；配 cv 史記线 v0.7.107。

- PATCH（11-25，CV0 u T1）：史記线上待审单换新三处卡点。① 导出器 `guji_manager.output.guji_format_export` 配老 cv（史記 0.7.103 patch 线，没有册 yaml `gaps:`）不再崩在最后写缺页文件那步（char／cord 已写完、u 都盖了）；cv 史記线 republish 改用本导出器后 char 带 u，book-text local_check 不再报标点／专名 u 对不上。② 标 main 自动重出（`online_lists.follow_main`）遇线上单没存 rev 包（手工出的旧单，史記 001–042）不再拒，按用户 11-25「线上单总是换最新的」照换，换完存 rev 包。③ `char_schema_for` 遇带 u 的 char 写 v0.6（republish 写待审首选字后以前降成 v0.1，book-text 升版拦）。④ 章号宽度：史記中心库基础配置补 `chapter_width: 3`（配置，不是代码；`chapter_of('12')` 现给 `012`）。L0。

## [0.6.19] - 2026-11-25

- 发版缘由：同包重标 main 记「已对过」（#991）；`guji uid check-u-report` 定时只报（#992）；uid 自检按册选 cv、--only 推库撞 Stale 重推（GM2 #990）。

- PATCH（11-25，CV0 u T1）：新命令 `guji uid check-u-report [--notify]`，在本机找得到的各工作区跑 `check-u`（先 `db pull --only` 拉人裁、补锚档、身份账、作废记档）；结果非 0 而且和上次不同，就通知 CV0 和该书项目（`GUJI_UID_CHECKU_TO`／`GUJI_UID_CHECKU_PROJECTS`）。只报，不改人裁。执行方空闲时按 `GUJI_UID_CHECKU_S` 定时跑，缺省 0＝不跑，只在一台机器上开。check-u 的补锚档两项不再算已记作废的抄件。L0。

- PATCH（11-25，CV0 u T1）：同一个包撤回又重标 main（殿本 9 册撤回 r15frame）时，账里已有这份切分，`uid sync` 判「unchanged」不写也不推。但 main 指针比账里最晚一行新，自检就一直报缺、一直交 uidsync 单。修法：标 main 钩子和 uidsync 单（`--reconfirm`）遇到已对过的包，再记一笔带时间的「已对过」并推。执行机开跑前的 uid 步不变。L0。

- PATCH（11-25，GM2）：uid 自检交单与推库两处修补（A30 看 uidsync 自检单失败后提出）：① `guji uid audit --submit` 交的 uidsync 单不再一律钉 cv main，按册依次取册 yaml 钉的 `cv_version` → 产出 main 包的那版（标签 `cv0.7.104-…` → `v0.7.104`）→ main（`--cv` 给了照旧一律用它）；全唐文 052／054 的 `page_kinds: table_cols`、042 的 `glyph_sim_qtw_v2` 只有 v0.7.104 与 dev 认，钉 main 必败（#17404、#17467、#17402、#17392）。② `db push|sync --only` 提交时撞整库版本守卫（`d1conn.Stale`，多机同推一个工作区）重读重推，最多 5 次（`GUJI_DB_STALE_TRIES`）；重读时范围内文件已被别人改照旧报 StaleBase，不覆盖（#17374 等）。③ 执行方准备段报 `BookConfigError` 不再算环境类（不再换会话空重试）。L0。

## [0.6.18] - 2026-11-25

- 发版缘由：~u 人裁抄件补锚档＋`guji uid anchor-fill`＋check-u 两项（#987）；跑完通知带 warn（#985）。

- PATCH（11-25，CV0 u T1）：u 存量迁移抄人裁 `~u` 件时，把原件的补锚档（`feedback/anchors/<册>.jsonl`）也抄一行给抄件。cv 按事件 id 查补锚档，抄件查不到框，老人裁判 unanchored、seed_admit 报 human_unbound（全唐文 vj1 004 册 2,036 格）。新函数 `u_migrate.copy_anchor_patches`。新命令 `guji uid anchor-fill [册…] [--write]`：原件有档的照抄；原件也无框无档的（锚点只有 `{source_rev, u}`）按身份账取 u 在现行切分里的格框（cv `_cells_versions`＋`_cell_index` 同口径）补一行 `source: backfill:u`。`guji uid check-u` 加两项：~u 抄件缺补锚档、~u 抄件无框无档（都应为 0）。11-25 全库存量已补推：原件有档照抄 全唐文 9,935／史記 8,629／北行 1,323／殿本 377；按 u 补框 殿本 5,310／脈經 1,500／史記 264／全唐文 190（殿本 vol28 两条 u 已作废补不了）。L0。

- PATCH（11-25，GM2）：跑完通知每条单带上 warn 提醒（重试成功前那次的失败原因、失联退回、不挡单的补入账失败等），成功的单也列（只 D1 任务库）。11-25 #17277 第 1 次失败、第 2 次成功，通知里看不到，提交人以为「失败没写原因」。L0。

## [0.6.17] - 2026-11-25

- 发版缘由：执行机部分副本上补身份账 push_failed（#983）。

- PATCH（11-25，CV0 u T1）：部分副本（`db pull --exclude`，执行机缺省排除 `feedback/lists/proofing/`）也能 `db push|sync --only`，只要范围和没拉的前缀不相交（相交、整体 push／sync 照旧拒）。执行机铺底后补身份账 `guji uid sync` 不再 push_failed（ZM／GM2 报 #17277 等 20 单）。L0。

## [0.6.16] - 2026-11-25

- 发版缘由：字格身份账入账兜底（#980）：执行机铺 main 底后入账、空闲执行方定时自检交 uidsync 单、main 指针记 manager 版本。

- PATCH（11-25，CV0 u T1）：字格身份账入账兜底，不再只靠标 main 那台机器（ZM 用旧 manager 给殿本 vol01–20 标 main 没入账）：新 `guji uid sync`（拉账 → main 包入账 → 推库；切分没变写一笔 page 0「已对过」记号）；执行机铺 main 底后先 sync（`uid` 步，失败不挡）；`guji uid audit [--submit]` 自检，空闲执行方每 4 小时跑（`GUJI_UID_AUDIT_S`，0 关），缺的交新任务类型 `uidsync`；标 main 指针记 `manager_version`，自检报出旧 manager 标的。账行记 `label`。L0。

## [0.6.15] - 2026-11-25

- 发版缘由：身份账行分得出谁写的（#974：`by`、钩子 `src: promote`）。

- PATCH（11-25，CV0 u T1）：身份账行加 `by`（`GUJI_ACTOR`，没有就机器名）；标 main 钩子写的行 `src: "promote"`（手跑／本机 pipeline 仍是 `advance`）。不进行 id，老行不变。L0。

## [0.6.14] - 2026-11-25

- 发版缘由：标 main 入账的机器不用另配 book-text（#970：本机没仓就从 GitHub raw 取这一章，带缓存）。

- PATCH（11-25，CV0 u T1）：`uid advance`／标 main 入账参考 book-text 时，本机没有 book-text 仓（没设 `GUJI_BOOK_TEXT`、缺省目录也没有）就从 GitHub raw（main 分支）只取这一章的 char＋cord，缓存在 `~/.cache/guji/book-text`（`GUJI_BOOK_TEXT_CACHE`），取不到网时用缓存；仍取不到才按 v0.6.13 报错／提示。标 main 的机器不用另配 book-text。L0。

## [0.6.13] - 2026-11-25

- 发版缘由：标 main 自动入账首次实测（史記 v0.2 42 册）全挂，修 #966：旧 cv 同口径自算 cells_sha、book-text 章号两位三位都找。

- PATCH（11-25，CV0 u T1）：标 main 自动入账不挑 cv 版本：`uid.source.page_cells_sha` 先用 cv 的（≥0.7.103），旧 cv 没有时按 `bindings.page_state` 同口径自算（史記 0.7.98 线 42 册首次实测全挂「cannot import page_cells_sha」）。`uid advance` 找 book-text 时章号两位、三位、不补零都试（史記册配置没写 chapter_width，给 `01`，book-text 是 `001.char.json`，原来静默不参考）；账是从 book-text 建的册找不到 book-text 时报错（`--no-book-text` 明说不参考才放行），本机 pipeline 与标 main 的钩子只打提示不挡。L0。

## [0.6.12] - 2026-11-25

- 发版缘由：字格 u 收尾补漏与读端（#959 migrate-plan 读原样事件、check-u 全库自检；#962 转待审条目同格合并带候选字、tidy-recheck；GM2 读端 #956–#958；GM4 land／audit alt #955 #961）。版本说明：这批先误合进 main 时仍标 0.6.11（main 5411bd2，与已发的 v0.6.11 tag 7f56a81 重号），改发 0.6.12。

- PATCH（11-25，CV0 u 收尾，QTW 反馈）：u 迁移转待审的条目同格并成一条（这格已有活条目就并进去，prior 同时留人裁字、票字），并带候选字 `alt`（现行字＋旧人裁字＋票字，去重、不收占位符）。新命令 `guji uid tidy-recheck <册> --items … [--write]` 就地整理已写出的（同格多条留最早一条、其余撤下写明并入谁，补候选）。
- PATCH（11-25，CV0 u 收尾补漏）：`guji uid migrate-plan` 改读原样事件：被 cv 页表 rev 闸挡掉的换图源前旧事件（cv 本就不采信、换算件另挂新格号），每格最新是它又没 u 的，`--close` 记档作废（此前漏了，GM2 核出殿本 8,180 格）。新命令 `guji uid check-u [册…]`：有账册每格最新人裁没 u、也没记作废／转待审的（GM2 口径：confirm、unit=cell、v∈HUMAN_VS、source 非 auto／llm／vision／knn_infer），应为 0，有则退出码 1。
- PATCH（11-25，GM2 u 读端）：第二步读 book-text 伴生层改按字格永久编号 u 对格（punct／entity v0.4 以 u 为准）。新模块 `formats/layer_u.py`；出单句 `sent_export`、收口锚点现算 `closeout/derive`（u 不在 char＝锚点失效，不回退格号）按 u 找格；收口写回 `closeout/writeback`、换包挪锚（`swap/booktext` 表挪锚后、□识出字／劈格／专名伸长／分段符跟标题）挪了格位 key 就把 u 跟到新格，免得 key 与 u 打架（F-OV-18）。顺手修：分段符跟标题后重排标点不再按已删的 `char_offset`（全 0 会把所有 before 排到 after 前）。char 没上 u 的册行为不变。L0。
- PATCH（11-25，GM4）：audit alt：没卡片的格按格图算、缺模型或书影源报错；land 给手加格补 alt（只补这一个键，#955）；卡片按裸格号对上（id 去册号）、新判没 alt 保留旧 alt、手加格不再只认来源前缀、每册收完清盘（#961）。
- PATCH（11-25，GM2）：点校工具按 u：write_go 裁定带 u、to_punct 写 v0.4（#956）；collect 按页绑格时键不是「页:列:格」（册启用 u）就整册绑，不把 u 当页号（#957）。

## [0.6.11] - 2026-11-25

- 发版缘由：字格 u 收尾（CV0 T1）：#951 标 main 给书已启用 u 的没账册首次入账；#952 中心库导入文件登记最后写（推一半重推补齐）、migrate-plan --close 缺条目文件写前报错。

- PATCH（11-25，CV0 u T1）：中心库导入把「文件登记」（`source_files`、整文件 blob 表）放到最后写（删也最后）。大批 `db push` 分段提交时中途断了（Stale 等），文件还没登记，下次 push 照旧认为有改动、差分补齐；原来文件先登记、事件只进一半，再推以为没改动（11-25 全唐文账实例，复现测试 `test_push_only_cut_midway_retries_cleanly`）。L0。
- PATCH（11-25，CV0 u T1）：`guji uid migrate-plan --close --write` 有人裁要转待审却没给条目文件时，在任何写入之前就报错（`u_migrate.check_close_inputs`），不再写了 ~u 抄件、作废记档才报。L0。

- PATCH（11-25，CV0 u T1）：标 main 自动入账（`uid/promote.py`）对**这部书已启用 u、本册还没账**的册（没 book-text 的册，如全唐文 031 起）按 main 包首次入账（读序发号）并推库；书是否启用看账目录里有没有任一册账（`uid.book_enabled`）。整部书没账的照旧不碰。L0。

## [0.6.10] - 2026-11-25

- PATCH（11-25，CV0 u 收尾）：`guji uid migrate-plan --close`：清单上的人裁按高置信异体、列内近邻唯一同字再救 u；其余裁定、没字或格已不在的人裁作废（不删原事件，记 `feedback/lists/u_void/<册>.jsonl`），字不同的人裁转待审条目（recheck），格号不在账的条目撤下；出 `收口.tsv`／`收口.json`。双写期收尾：`u_stamp.current_cell` 对有账册里没 u 的记录返回 None（`latest_human`、`rulings-hits` 不再按格号认），六个写入点改 `stamp_strict`（盖不上整批报错）。`_cv` 加 `variant_group`。
- PATCH（11-25，GM4）：中心库 events 的 payload、target 已改成由 raw 算的虚拟列（线上已迁；Worker 与 importer 不写，旧版 manager 不受影响），`doc/数据库/中心库.md` 同步。文档改动，L0。
## [0.6.9] - 2026-11-25

- 发版缘由：字格永久编号 u（CV0 T1／T2）全库推完，写入以 u 为准；标 main 时自动入账（执行机跟 main 才生效）。Wiki 已补改（原拟 0.7.0，用户 11-25 定「不要总是升级 minor，先升 patch」改发 0.6.9）。
- 版本号：原拟 0.7.0 改发 0.6.9（PATCH）；`scripts/check_release_tags.py` 登记作废的 0.7.0（main 上已有 rc/v0.7.0 合并提交，不打 tag）。
- T1 #940：`guji uid advance` 参考 book-text 已发的号（`uid/booktext.py`）：新号从 `max(账 u_max, char u_max, char 最大 u, char 作废号)` 之上发，绝不发 book-text 改字工具（char_edits、意见修订 B′）已用过的号；本页要发新号的格若与 book-text 里账上还没有的 u 框对得上（IoU≥0.5，或中心距近且同字），就认领那个 u，谱系记 `src: "book-text"`。book-text 按 `GUJI_BOOK_TEXT`＋册配置找，找不到照旧只看账；`--book-text <仓>` 指定、`--no-book-text` 关。L0。

- PATCH（11-25，CV0 u：book-text 全库 cord 已删 `cells[].id`，fa159dfb）：导出有身份账时 cord 不再写 CV 格 id；意见修订 B′ 在 char v0.6 上插新格发新 u（u_max＋1）、cord 新格不带 id、`$schema` 不再降成 v0.2。manager 别处读 cord 都按格位 `a`，不读 id。
- PATCH（11-25，CV0 u T2，Sheldon「不要双写太久了，激进一点」）：**写入以 u 为准**。manager 里 `from ._cv import EventLog／RulingLog` 改拿 `u_stamp` 的子类，append 前统一盖字格永久编号 u（人裁 `target.anchor.u`、裁定 `payload.u`）；册有字格身份账而写不出 u 的（账上没这一格、格号不全）整批报错，不再静默只写格号。没账的册不变。
- PATCH（11-25，CV0 u T2）：`guji uid migrate-plan` 存量迁移口径按全库实测补齐（#925 #929 #931 本 PR）：窗口按本书归一表比；人裁比字形或读作、先认锚里 cells_sha；没记窗口的裁定按字同／各版同格；`--write` 只追加（`~u` 抄件，ts、seq 不变）。殿本 99 册、全唐文 30 册、脈經、北行、史記 41 册已迁并推库。
- PATCH（11-24／25，CV0 u T2）：裁定、人裁、待审条目、网站票、book-text 导出挂 u（#921 #924）：`u_stamp`、待审条目按 u 认、`cellvotes` 按 u 认票、`rulings-hits` 按 u 跟现格、`guji uid table`、swap 按 u 出表、导出 char v0.6／norm v0.3。没账的册逐字节同。
- PATCH（11-25，CV0 u 推全库）：字格身份账改在**标 main 时**入账：新插件 `guji.post_promote` → `uid/promote.py`，有账的册标 main 后先 `db pull --only` 拉这册的账、取回该 main 包 `advance`、有新行就 `db push --only` 推回中心库（`GUJI_UID_ON_PROMOTE=0` 关、`GUJI_UID_AUTO_PUSH=0` 只入本机）。执行机（有 `GUJI_JOB_ID`）跑完不再在 `hooks.finished` 入账：执行机不推数据回库，入了也丢，还会弄脏下张单的 db pull。没账的册不变，L0。
- PATCH（11-25，CV0 u 试点）：`guji uid advance` 只在本页 seed_admit 是在现行字块上跑的（manifest 上游 `char_index` sha＝现行 `cell_shrink` sha）时才取字；只重切到 cell_shrink、没重跑识字时旧字按格号会整列错位，误导拆格时谁沿用 u（试点 vol28 p3「業」格）。这时只按框对照。L0。
- PATCH（11-25，CV0 u 试点）：`guji uid advance` 从产物取框改成与 book-text cord 同口径（`cell_shrink` 字框 `bbox_page` 优先，空格才用格四角外接框）。原先只用格框，与 book-text 建的账对照时 vol31 有 4,518 格 IoU 不够、靠中心距才配上；改后 32,611 格全按 IoU 对上。账里已有的行不受影响，L0。
- PATCH（11-24，CV0「字格永久编号 u」T1）：字格身份账 `guji_manager/uid/`＋命令 `guji uid advance|init|show|verify`：每册 `feedback/uid/<册>.jsonl`（只追加，进中心库 events 表 stream=uid），切字后按框 IoU→中心距→拆→并→字序列对照继承 u；`guji pipeline` 跑完、该册有账时自动入账；`cell_ref()` 对有账的册返回 u（查不到报 `UidMissing`，不回退格号），没账的册照旧恒等。格式见 `doc/参考/字格身份账.md`。没账的册行为不变，cv 产物不动，L0。
- PATCH（11-24，GM4 整理第四步数据库表）：中心库 `files.doc`、`anchors.doc` 与 `raw` 同内容，importer 不再写（files 写 NULL、anchors 写空串，因该列 NOT NULL 且 D1 删不掉列）；`central_gc._file_rows` 改从 `raw` 解析。配套 cv#1845、workspace-data#35。旧版 manager 照写不报错，只是库里多存一份。L0。
- MINOR：页型 `col_check` 1.2.0：items 可带 `compact: true`＋`show_w`，列图是压缩过的矮条时按原宽显示、一屏自动换行排多列（上下压缩看左右切线用；Sheldon 11-24）。
- MINOR：页型 `cut_check` 1.1.0：items 可带 `noline: true`，不画蓝色平均切线（折线已烧在图里时只留红折线；Sheldon 11-24）。
- MINOR：页型 `col_check` 1.1.0：items 可带 `screen`（分屏键），给了就按它分屏、保持输入顺序，一屏可混放不同页的列（每列标「册·页·列」）；不给照旧一页书一屏（Sheldon 11-23：全唐文这类分得清的书整列看、一屏多放几列）。
- PATCH：`ctx-ruling write`／`rulings-hits --rekey-vis` 对齐 cv #1837 写前校验：试跑就预检（版本 seed_admit 不认的逐条列出，退出码 2）；真写遇 cv 拒写不抛栈，打原因、提示登记 `ver_equiv.yaml`，退出码 2、一条不落。`_cv` 加 `ruling_validate`（旧 cv 没有则跳过预检）。

## [0.6.8] - 2026-11-24

- PATCH：`guji db pull|push|sync --only <路径>`（可多次；目录以 / 结尾）：只拉、只推、只合这些路径，范围外库里本机都不动；不扫整个数据目录、不整表读 source_files（Worker `prefix=`，旧 Worker 自动退回整表筛）、不碰字形库、不重建 glyph.db。新鲜度按路径记在状态文件 `only_revs`；不加 `--only` 行为不变（换包按条目对账，GM4 11-24）。

## [0.6.7] - 2026-11-24

- PATCH：新命令 `guji feedback human-conflicts --books … [--batches r1,r2]`：推库前查跨批次人裁冲突，同一现格（过绑定表）几批定成不同字的列出历次与生效字（生效字取 cv `human_chars`，口径同 seed_admit／collect）；绑不上现格的单列；有冲突退出码 3（SJ 11-21）。
- PATCH：新命令 `guji text ctx-ruling write`：按「格号＋字」写终审文意裁定（group O、ctx-m1），键按 seed_admit 5c 窗口（`key_windows`，有 `evidence.vis_ctx` 就用），越过整理本、取不到窗口逐行提示；收进 ZM 会话脚本 `write_ctx_ruling_by_cell.py`（ZM 11-21）。
- PATCH：`rulings-hits --fetch`：各册并行取产物包、只解 seed_admit／align_ref；`products pack fetch --steps` 同（整包仍要下载，省解包落盘）（ZM 11-21）。
- PATCH：`rulings-hits` 开了码位表的书、产物没有 `vis_ctx` 时，窗口里有码位目标字的格原因直接写「多半是码位归一」（QTW 11-21，全唐文 陜／戸／勲）；`--data-dir` 指定读码位表的数据目录。
- PATCH：中心库收 `feedback/rulings/ver_equiv.yaml`（裁定版本等价登记表，GM4 方案②、CV4 实现，cv 读）：原先 `feedback/rulings/` 下只收 `.jsonl`，这张表推库时会被静默跳过、各机拿不到。

## [0.6.6] - 2026-11-23

- **PATCH**（11-23，GM1，中心库第一步表精简）：`files` 里 kind=config 的 `.json` 不再解析进 `doc`（无读者；kind=list 等不变，`row_sha` 只由 raw 算，不触发重推）；`workcopy` 推库前的 corpus-pack／glyph-pack manifest 保护查询由 `LIKE … OR LIKE` 改成主键区间查询，不再扫整个 ws 的 files。生产库已把 config 的 doc 置空。L0。
- **PATCH**（11-23，Sheldon「写中心库不用我同意，可以改 manager 文档」）：文档里「写中心库、推库、传 R2 要用户点头／先报条数等点头」改为：推前 `db pull`＋`push --dry-run`，常规推库不用问用户（与 ai-team 项目管理指南 11-20 白名单一致）；删数据、批量撤除、换正式库、字形账本缩水等仍先停下问。只改文档（L0）。

- **PATCH**（11-23，GM4；格式瘦身 A＋B 读端补充，guji-format #33）：`revise.dump_like`（revise／revert 写盘共用）认 v0.3 punct／entity「每条一行」写法并原样写回，改一条只动一行；v0.1／v0.2 旧写法不变。用 GM3 三册样本（殿本050、全唐文010、史記003）验往返逐字节一致、旧新格式 `plan_fixes` 结果相同；加 3 条测试。swap 写盘仍走 book-text `original_version.dump_json`，其对 v0.3 的保排版需 GM3／CV0 另核。（来源判定与换单守卫已由 GM2 #878 做。）
- **PATCH**（11-23，GM2，格式瘦身 punct／entity v0.3 读端）：`closeout` 写回（`fix-misplaced`）判人改改读 `effective_source`（条目省 source 时取 `default_source`），`char_offset` 有才更新、不新增；换单 `swap` 守卫按有效 source 比标点条目，v0.2→v0.3 迁移不误报。book-text 侧 `check_anchor_drift`／`remap_anchors`／`char_edits` 同口径（book-text #501）。L0。
## [0.6.5] - 2026-11-23

- **PATCH**（11-23，#848 直接进 main，随本版回到 dev）：runner 自更新循环修复——manager 切换（checkout）失败不再当成功；自更新后仍判过期就不再 exec，避免空闲 runner 反复「已拉新代码，重新 exec」不领单。L0。
- **PATCH**（11-23，GM2 版本普查）：执行方上线时 worker 表的 `runner` 一栏带上本机 manager 版本（如 `36f1e242 m0.6.4`），`guji job workers` 直接看全部执行机版本，不用逐台问。L0。
- **PATCH**（11-23，CV0 转用户数据库分工：字形库归 GM2）：`guji db push`／`sync` 核「库里已有哪些图」不再按工作区整表读 `glyph_instances.patch_sha`（殿本 18 万行，中心库读量大户）：要推的图 ≤2000 张时按 sha 问（`= ANY`），多了才整表读；锚图、整理本表同理。增量 pull 本来就按改动的实例取 patch_sha，全量 pull 要还原全部刻例图、仍整表读。L0。

- **PATCH**（11-23，CV3，Sheldon 定护栏按书按集、放 dataset）：新增 `guji eval guard`，读 open-guji-dataset `guards/*.yaml`（每条＝评测器＋指标＋max/min＋放宽后的门，要库的写 `lib: <书id>`、用 `--lib 书id=glyph.db` 给），逐条比、出总表，越线或未验证以 1 退出；`guji eval run` 跑到有护栏的评测器也自动比，越线记 regressed。`doc/版本号规矩.md` rc 步骤加「护栏必须全过」。新增 `eval/guards.py`、测试 `test_eval_guards.py`。
- **PATCH**（11-23，SJ／CV0 问）：COMPAT.md 写明 manager 0.6 只硬核契约 v1，cv 0.7.x／0.8.x 也能用，只是 `pipeline` 步骤前缀要 cv ≥ 0.9.0（旧 cv 写 `guji job …` 等老写法）；`swap doctor` 的 cv 版本提示改成同一口径。L0。
- **MINOR**（11-23，CV2 cut-bench L2）：新页型 `cut_check`（逐格切线审查）1.0.0——一屏原书一列，一格一张小图（上下各带半个邻格）画上、下切线，点图上半／下半标那条切线不准；列首尾与边框之间不画不审。结果 `guji review-pages cutcheck-apply`。L0。
- **PATCH**（11-23，GM4／A32，GM2 转全唐文 006–008 实测；L0）：①`guji collect` 多册串行时某册 `SystemExit`／异常不再把后面几册一起带走：记成该册 blocked 并继续，开头打印「本趟收 N 册：…」，结尾照旧列没收完的册（`--books 006,007,008`、`007-008` 本就能展开，`parse_books` 已有测试）。②`swap doctor` 加版本检查：manager < 0.5.0、cv < 0.9.0 只提示不挡；`CELLREVIEW_TOKEN` 由必需改为可选（0.5.0 起缺省读收件箱，用 `GUJI_DATA_TOKEN_READ`）。未动落票口径。

## [0.6.4] - 2026-11-23

- 发版说明：0.6.2、0.6.3 号已被别的发版占用（tag v0.6.2 在 f96528b），本版号 0.6.4。

- **PATCH**（11-23，GUJI-776 新机首次 db sync 168 秒、moved 61,251）：`glyph_instances` 标为按主键排的表（`TableSpec.key_ordered`）。cv 导出 `instances/*.jsonl` 按 instance_id 排，中间新增几行后面的行号全变；导入时文件严格按主键升序就不再逐行推「只是行号变了」（`importer.key_sorted_paths`），还原时按主键排回、整文件 sha 核对（`materialize`）。没按主键排的文件照旧。测试 `test_glyph_key_order.py`。L0。
- **PATCH**（11-23，ZM #16511／#16520 报）：任务库执行方缺省按需拉（部分副本），整册跑完的自动回库每单都报「⚠ 放行格回库失败」。部分副本推不上中心库本是预期，改成一行 ⓘ 说明（这里不回库；结果要进库，标 main 后在完整副本上 `guji db pull` 再 `guji glyph-db backfill --books … --apply`），不再去跑回库、不报失败；整拉的机器照旧回库。L0。

## [0.6.2] - 2026-11-23

- **PATCH**（11-23，QTW 报：v0.6.1 标 main 必挂）：#818 用 ruff 删「未用 import」时误删 `ops/pack_purity.py` 末尾的再导出 `describe`，`guji products pack promote`（标 main）与存包打印纯净性时 `ImportError`／`AttributeError`。补回（标 `noqa: F401`）。新测试 `tests/test_import_names.py`：静态列出本包全部相对导入（含函数里的），逐条核对目标模块真有这个名字；另把 `_warn_impure`、`_purity` 两条路径真跑一遍。#818 其余删掉的 import 逐个查过，没有别的被外部引用。L0。
- **PATCH**（11-23，CV2 修格确认页）：`col_check` 1.0.3——item 带 `focus: true` 的列加橙色粗描边、标「请确认」，同页其余列照常显示作对照（修完错格后出确认页用：整页看、刚修的列突出）。L0。

## [0.6.1] - 2026-11-23

- 发版缘由：执行机跟 manager main，任务库切 D1（#811）要发版才生效。

- **PATCH**（11-23，GM2 清理第二批：三层迭代到出 v0.1 的命令、人审页、文档）：`close-check`、`collate`、`progress` 帮助与 `tools/开书/出v01.py` 的「Step9」改称第五步产物（原 Step9），出v01 提示改写 `guji output export md`；`review-pages` 帮助与 `seg_cause` 页型说明里「A22 seg_causes」改指本仓 `review/seg_causes.py`。Wiki「人审页模板」：页型表补 `col_check`、编号去重，第七节版本列按 `registry.py` 更新并补 `ref_check`／`variant_compare`／`seg_cut`／`col_check` 四行，旧路径 `doc/01-粗校/…`、旧名改掉；另修 4 处指向旧路径的文档（无法识别字、exp_framework、切分代码结构、spreads.py）。页型版本不变，不动产物（L0）。
- **PATCH**（11-23，CV2 收 cut-bench 第 4 轮）：审阅页存档 `_store.js` 修丢标注——后台正在写时新的 flush 直接返回、不再补写，快速翻页（每页 1–2 秒）时最后几页的「本页没问题」标注没进后台（全唐文 3 页、史記 1 页、殿本 1 页）；改成写时记一笔、写完再补一轮。本机 localStorage 里仍有，重开页面会补写。所有用 `makeStore` 的页型都受益。`col_check` 1.0.2：说明改为「这一轮只确认格数与大致切分，连接处切点、框线不用细看」。L0。
- **PATCH**（11-23，Sheldon「清理照做」）：中心库删五张一直为空的表 `cv_versions`、`freeze_baselines`、`snapshots`、`glyph_pairs`、`glyph_events`（schema、`scope.py` 的表定义与行解析都去掉；`pairs.jsonl`、`events/*.jsonl` 若出现改当整文件进 `files`）。文档与发布标准里「三张登记表各一行」改为查 `feedback/lists/freeze/<册>.jsonl`。删前整库已备份。L0。
- **PATCH**（11-23，GM2 全面清理）：去掉中心库迁 D1 后的 Neon 残留——删 `datastore/neonapi.py` 空壳（`cli_db`、任务库看板直接按分支名连），`jobs.store.connect_neon` 改名 `connect_central`（旧名留别名），各命令帮助与注释里的「写 Neon 正式库」等改成中心库；`pending-stats` 报告里码表、分类规则、跟进方的出处从 cv／ai-team 旧路径改成本仓路径；待审原因 yaml 的 `owner`、`taxonomy` 的跟进方、`diagnose`／`machine_audit`／`seg_causes` 等输出里给人看的去向、`iterate freeze` 的通知名单换成 11-23 新 Project 名（CV0–CV4、GM2–GM4；进度看板的写入人 `WHO` 不动）；`guji iterate --help` 返回 0。删未用的 import 与变量、`_cv` 里三个重复键。文档：待审原因规范从 cv `doc/design/` 搬来成 `doc/参考/待审原因/规范-PendingReason.md`（补 11-09「book-text 只录首选字」后的写法）；`环境与令牌` 去掉 Neon／KV 令牌、补密钥仓取法与任务库令牌；`待审分类规范`、`按码现算.py`、两篇 Wiki 的 Neon 连法改成 D1；doc／Wiki 里「报／交／找 A2x／A3x」一类去向换新名；修 `doc/参考` 两处指向 `中心库.md` 的断链。不动产物（L0）。
- **PATCH**（11-23，Sheldon「任务库也搬到 D1」「随时切」）：**任务库缺省改连 D1 `guji-jobs`**（`databases.toml` 的 `[jobs]` → `d1-worker`，`env_url` 改 `GUJI_JOBS_URL`）；旧美国机 Postgres 挪到 `[jobs_pg]`，`jobsdb` 在 `[jobs]` 不是 pg-tunnel 时读它（搬家脚本用）。执行方空闲时自更新即改连 D1；交接期 `scripts/jobs_pg_to_d1.py sync` 反复把 Postgres 的变动同步过来。`guji_jobs` 等提交端要更新到含此改动的 manager。L1（存放位置变，命令不变）。
- **PATCH**（11-23，A31 查中心库迁 D1 后遗留）：`central-gc` 查「排队／在跑任务点名的包」原来在**中心库**连接上查 `jobs.job`，任务库 11-03 起就是单独的库，一直静默读不到、不按任务保留；改按 `databases.toml` 的 `[jobs]` 连任务库，读不了时 `--apply` 拒删。`central-gc`、`progress-sync` 读线上单／冻结清单时补上大文件（`files.body_r2=1`，原文在 R2）：原先这类行 raw／doc 为空被漏掉（北行日录 001 线上单）。`guji datastore` 入口指错模块（KeyError 'main'）修正。测试 `test_central_gc.py` 加两条。只读改动，不动产物（L0）。
- **PATCH**（11-23，Sheldon 11-22「任务库也搬到 D1」）：任务库支持 Cloudflare D1（独立库 `guji-jobs`，经 guji-data Worker `/v1/sql?db=jobs`），按 `databases.toml` 的 `[jobs].driver` 选，**缺省仍是美国机 Postgres**，数据搬完再发版改缺省。新 `jobs/schema_d1.sql`、`jobs/d1.py`（连接：一批一事务、结果按列名还原类型；`sqlite` 驱动连本机文件）、`jobs/store_d1.py`（D1 写法：一次请求一批语句，`mark` 标记找刚改的行，条件分支用 `UPDATE … RETURNING`），`store` 各函数按连接分派。执行方空闲轮询在 D1 上 60 秒一次、领单与报到并成一次请求，收回过期与通知每 5 轮一次（`GUJI_JOBS_IDLE_EVERY`）；心跳续租与报到并成一次（`heartbeat(seen=…)`）。看板、耗时推送/汇总有 D1 分支。搬家脚本 `scripts/jobs_pg_to_d1.py`（dump／check）。文档 `doc/数据库/任务库.md` 加 D1 连法、写法要点、搬家步骤。测试 `tests/test_jobs_d1.py`。Postgres 路径行为不变（L0）。
- **PATCH**（11-22，Sheldon「所有数据库尽量抽象，可随时通过配置文件改链接方式」）：连库配置 `databases.toml`（包内 `guji_manager/config/databases.toml` → `~/.config/guji/databases.toml` → `GUJI_DB_CONFIG` → 老环境变量），`guji_manager/dbconfig.py` 按库名（`central`、`webinbox`、`jobs`、`catalog`）取连法；中心库连接、网站收件箱读、R2 上传、任务库隧道改从配置取，缺省值与原来一致，老环境变量照旧能盖。新命令 `guji db where` 列各库解析出的连法（不打印令牌）。装载时若 `GUJI_DATA_URL` 没设，按配置给 cv 设上。文档 `doc/数据库/`：README（四库一览＋配置说明）、中心库（原 `doc/参考/中心库.md` 移来并按 D1 改写，含全部表）、网站收件箱、任务库、目录库。测试 `tests/test_dbconfig.py`。不动产物（L0）。
- **PATCH**（11-23，A23 识字 benchmark 第 2 期 d）：`guji eval run @read`（另有 `@read-3a`／`@read-3b`）一次跑齐识字子基准；`--save-dir` 存各评测器 JSON 与报告，`--against <旧目录>` 逐项比指标、列误认／错例清单的新增与消失，钉版不同先提示（`eval/compare.py`）；rare_* 的钉版记字表与模型而不是 glyph.db。测试 `test_eval_compare_read.py`。L0。
- **PATCH**（11-23，A23 识字 benchmark 第 2 期）：`guji eval run` 的识字评测器按 `--out` JSON 取数（`eval/extract.py`）——match_pairs*／sim_bench 不再报「跑不起来」，match_bench 报 same 精度／覆盖／novel 误放／rank1／auroc，rare_* 头条改为生产用的 emb 路与 unseen top10，**emb top10 为 0（缺向量包）判失败**不再静默报 ok；报告加 `lock`（cv、dataset 提交、glyph.db sha16），命令行打「钉版」一行。测试 `test_eval_extract_read.py`。另登记 3a 库外拒识 `advset`／`advset_shiji`／`advset_qtw`（cv `eval_advset.py`，dataset `glyph-match/advset-*`）与 3a 退化 `match_pool`／`match_pool_shiji`（cv `eval_match_pool.py`，dataset `glyph-match/damaged-*`）、3b 首次字头格 `rare_qtw_firstseen`（dataset `007-qtw-firstseen`）。只动评测，不动产物（L0）。
- **PATCH**（11-23，Sheldon 点抽查页反馈）：`col_check` 1.0.1——第 1 列排到最右（原先反了），页面说明补「格框带框线不算错，这一轮只看字间切点」。
- **PATCH**（11-23，A22 切字 benchmark 银标抽查）：审阅页加页型 `col_check`「整列切分抽查」——一页书一屏、各列从右到左叠格框，点并字／劈字／框歪的格标红，整列没问题翻页记全对；结果 `review-pages colcheck-apply` 导出（`review_pages/col_check.py`）。测试 `test_col_check_screens_and_labels`。只加页型，不动产物（L0）。
- **PATCH**（11-23，史记 2 册 8:2:13b 待审格在网站显示成阙字）：`close-check` 2c「□ 有去向」加一条——待审单上、非人裁、有首选字（`first_choice`）的格，导出里若仍是 □ 就报错（`pending_blank`）。原先「在待审单上」即算有去向，v0.1 首发单没带候选，1,332 个待审格落成 □＋lacuna 也过了关。`release_gates.load_pending_blank_cells`，测试 `test_pending_blank_with_first_choice_flagged`。L0。

## [0.6.0] - 2026-11-22

- 要求 open-guji-cv ≥ 0.9.0（cv 那边删了原 Step9 代码与 `guji export`，由本版 `guji output` 接手）。Wiki 已按 v0.6 重改。

- **MINOR**（删命令，用户 11-22 定）：`guji` 命令按五步加前缀 `guji <步> <命令>`，步为 `start` 新书启动／`pipeline` 自动化流程／`text` 文意与知识／`feedback` 反馈迭代／`output` 排版输出（`guji_manager/steps.py`）；不带前缀的老写法照旧能用，`guji <步> commands` 列本步命令。前缀经 cv 新钩子时点 `route` 去掉（cv #1786）；cv 旧版没有该时点时 `start`／`text`／`feedback`／`output` 靠同名子命令兜底，`pipeline` 前缀不可用。原只能 `guji-manager <命令>`／`python -m` 调的 `pending-stats`、`central-gc`、`triage`、`review-pages`、`progress-sync`、`iterate`、`suggest`、`pair-attr`、`final-review`、`online-lists`、`datastore` 并进 `guji`。**删除** `guji release`、`deploy`、`batch`、`label-batch`、`cards`、`store`（及 `ops/release_check.py`）。
- **MINOR**（用户 11-23 定「cv 原第 9 步的代码整个搬进 manager」）：第五步排版输出的代码从 cv 搬进 `guji_manager/output/`：cv `report/` 的 collate、collation_grade、same_char、absent、tiers、strips 六个模块，`scripts/` 的 render_guji_markdown、export_guji_format、export_guji_page、convert_pages_to_char_cord、reflow_md、export_wikisource、build_collation_report 七个脚本改成模块（`python -m guji_manager.output.<模块>`）。命令 `guji output export md／format／wikisource／reflow`（原 cv `guji export md／format`，改为同进程调用，口径不变）、新增 `guji output collation-report`。cv 的 `report/slots.py`、`report/witness.py` 管线要用，留在 cv。只读产物，不动产物与指纹（L0）。要求 cv ≥ 0.9.0（cv 那边删掉这些代码）。
- 文档：doc 只留规格与事实，教程、做法、坑搬进 Wiki（`wiki/<步名>/`）；四步改名新书启动／自动化流程／文意与知识／反馈迭代，加第五步排版输出（cv 原 Step9 移来）。

## [0.5.0] - 2026-11-21

- **MINOR**：网站票、改字意见缺省改读中心库 `web_inbox`（D1 为真源，网站 KV 已淘汰，A20 11-22；缺省变了所以升 MINOR）：`cellvotes draft`、`opinions ingest`、收单 `votes_from_flag()` 不带参数即读收件箱；`--from`/`--from-dir` 文件离线读不变；应急读旧 KV 用 `--from-kv` 或 `GUJI_VOTES_FROM=kv`（网站已不再写 KV）。

- PATCH：`cellvotes reconcile` 的 KV 管理读改为读 3 遍取并集（按票身份）：两次读条数相同、缺的却是不同的票（995ejelvk0 条目票 372／373），只比条数会误报「只在收件箱」。

- PATCH：`cellvotes reconcile` 加 `--rev all`（收件箱里出现过的每张单都比）；KV 管理读失败重试，并再读一遍取条数多的那次（11-21 殿本首轮对账 3 票「只在收件箱」、2 张单 500，都是 KV 管理读不稳，重读即一致）。

## [0.4.82] - 2026-11-20

- PATCH：`guji collect` 落按格写的文意裁定（ZM 11-21 batch5 兩/雨 3 格、閔 1 格 landed 0 且无提示）：`ai_ruling_chars` 加第三路，seed_admit 没有 ask（字组没进）或 ask 同组同版本但窗口小变的格，按格号取最新一条非 O 文意裁定，conf=high、字是整理本字／库前五／组员、窗口紧邻 2 字相同且相似度 ≥0.8 才落，来源 `AI文意/<组>/按格`；对不上、终审裁定把握不够／admit_ok 假的都写进 notes，不再静默跳过。待审分类 V01 不再把 兩雨 味未 玉王 傅傳 箸著 住往 奕弈 寥𡚶 算异体（字典边实为形近，`review.reasons.NOT_VARIANT_PAIRS`）（#778）。

## [0.4.81] - 2026-11-20

- PATCH：`guji collect` 提速（ZM 11-21 性能反馈）：`--jobs N` 多册并行（子进程各用 `<检出>-collect-<册>` worktree，拉库／推库／发站各一次，推 dev 被抢先 rebase 重推）；产物包分段并发取，每册收完删解出的包（`--keep-pack` 留）；开头显式更新 origin/dev（单分支检出 `local_check --dev` 不再因旧引用整册不过）；提示词版本／字组改名、窗口没变的文意裁定照落并按现行版本补键；失败原因带出报错行（含格号），每趟结果记 `reports/_collect/runs/`（#769）。
- PATCH：网站票、改字意见可改读中心库网站收件箱 `web_inbox`（A20 11-21：网站 KV 与 D1 双写，之后淘汰 KV）。`cellvotes draft --from-inbox`（按单版、按条目两种键都认，按键名排序，产出与 `--from-kv` 逐字节相同；`--allow-empty` 也认它）、`opinions ingest --from-inbox`（改字意见与按单版精校票读收件箱，hidden.txt 照读中心库）、`guji collect` 设 `GUJI_VOTES_FROM=inbox` 改读收件箱、新增 `cellvotes reconcile` 双写对账（KV vs 收件箱逐票比）。缺省仍读 KV，对账通过后再改。忽略 `probe:` 探测条目；墓碑（`value.deleted: true`，网站删了 KV 键）读到跳过、对账算一致；`web_inbox.by_prefix` 按键前缀不按书读（thread 等无 book 的）。

## [0.4.80] - 2026-11-20

- PATCH：`rulings-hits` 终审裁定未放行的兜底原因不再断言「产物早于裁定」（QTW 11-20：裁定 11-19、包 11-20 仍报这条），改写裁定时间并列两种可能（产物早于推库／5c 时邻格字被码位归一、pair_form 改过 manager 看不出），产物有 `evidence.vis_ctx` 时另说；新增可核原因：裁定库按窗口键取到的是同窗口更晚的另一条、裁定没写 `ctx.hash`（可补键）、这页 align_ref 没锚定（同 cv 不认整理本字，窗口也按此算）（#765）。

## [0.4.79] - 2026-11-20

- PATCH：裁定键窗口按 seed_admit 5c（`_vis_ruling_pass`）当时的状态算：5c 之后才放行（consensus_lib、near_knn gap、symbol_ref_blank、textlayer_ref、vis_ruling）的邻格退成未放，之后才降审（stroke_veto、evict_review、symbol_review、human_unbound、jiazhu_uneven、src_code_conflict）的邻格退成放行字；产物带 cv 记的 `evidence.vis_ctx` 时直接用它。影响终审 `final-review` 写键、`vis_review export`、`rulings-hits` 判因与 `--rekey`（全唐文 001–030 26 格裁定 6 格因此不命中，例 027:59:4:7）。`rulings-hits` 清单加「差在」列，写出窗口差在哪几个字（#761）。

## [0.4.78] - 2026-11-20

- PATCH：`guji job submit` 纯重放不再缺省按页（`--pages auto` 按事件 ts 比铺底包生成时间，判定早于铺底包、推库晚于它的裁定会漏页，全唐文「閒」14 条）；显式 `--pages auto` 先打警告（#753）。

## [0.4.77] - 2026-11-20

- PATCH：`rulings-hits` 改走 `_cv` 门面（修 #746 起 dev 测试红）（#750）。
- PATCH：`datastore.r2.upload_files` 本机缺的图不先 stat，R2 已有就跳过，真要传才记 missing_local（ZM vol28 出单读旧单字块图 FileNotFoundError）（#751）。

## [0.4.76] - 2026-11-20

- PATCH：`guji rulings-hits` 越过整理本按 `--override-groups`（书级白名单）真核，不再误报；放行后又被后面一遍降审的格单列原因（#748）。

## [0.4.75] - 2026-11-20

- PATCH：`guji rulings-hits` 终审看图裁定未放行逐格给具体原因（已人裁／疑点／子类不收／对位字变／窗口变／半格／越过整理本／产物旧），`--vis-subclasses` 按书级子类算；`--rekey` 也给只是窗口变了的终审裁定补键（#746）。

## [0.4.74] - 2026-11-20

- PATCH：`guji round-check` 收轮检查加两项：人裁掉格（新包比 main 多出的人裁解绑，有就不过）、放行字变（旧字是人裁或等于参校本的标可疑）（#739）。
- PATCH：新命令 `guji rulings-hits`：AI 文意裁定按格有、按窗口没命中的格（窗口变了／提示词版本）列出来，`--rekey --batch` 按产物窗口补写；终审看图裁定可放行却仍待审的也列出（#740、#741）。
- PATCH：新命令 `guji seg pins-stale`：钉子记下钉时的列窗依据，换切分包后判过期／可能／未知，有过期退出码 3（#742）。
- PATCH：`guji collect` 缺省把 AI 裁定一起直接落 book-text（文意按窗口命中且 high、字在组内；终审看图 high＋admit_ok、对位字没变、非半格）；人裁优先，AI 落的格不在单上结案；`--no-ai` 关（#743）。
- PATCH：`guji job submit` 新增 `--pages auto`，纯重放（从 context_decide／seed_admit 起、cv 同铺底包、没改配置）缺省只跑铺底包之后有新人裁／AI 裁定的页；没新反馈拒交；`--pages all` 整册（#744）。

## [0.4.73] - 2026-11-20

- PATCH：`guji swap run` 状态按「册＋主包」记：现在的 ★main 与上次记下的不同，上次的 verified／done 作废、重做（全唐文 11-20 d2 29 册假 verified）；新增 `--land-votes` 透传 auto_cycle（缺省关）（#735）。配套 cv #1754（auto_cycle 自己的状态文件同改，只改 scripts/zhengli）。
- PATCH：`guji job show` 失败单直接列「日志要点」（✗、⚠、XxxError／Drift 行）；`guji job submit` 核 base 包在 R2 在不在，没有就拒（`--no-base-check` 跳过）（#736）。
- PATCH：`guji db sync` 结尾报近 7 天还没被消费者处理的人裁事件（漏 route、本机缺包没消费），按批次×消费者列条数并给补跑命令（`GUJI_SYNC_UNCONSUMED_DAYS`）（#737）。

## [0.4.72] - 2026-11-20

- PATCH：roundcheck 单可按单覆盖分层配置：`guji job submit --rc-set seg_defect=true`（可多次；键 order／cov_min／lib_min／seg_defect），进 spec `roundcheck.config`（进指纹；不给不出键，老指纹不变）；`guji round-check` 加 `--set`；summary.json 记 `layer_overrides`。起因史記 #5968：执行机 `db pull` 用中心库的 workspace.yaml 盖掉书仓检出的那份，书仓里开的 seg_defect 没生效。

## [0.4.71] - 2026-11-20

- PATCH：修 roundcheck 单（及只给 `--book-id` 的单）在新执行机上备不了工作区（QTW 11-20 首批 #5944–#5965 全挂 prep「更新工作区」）：`WS_REPOS` 补全唐文 `995ejelvk0 → guji-workspace/995ejelvk0-quan-tang-wen`，`guji job submit` 加 `--ws-repo`。ws_repo 不进指纹，失败的单直接重交即可。
- 文档（不动代码）：`doc/01-粗校/无法识别字.md` 补「route 归谁」——每书固定一条线（全唐文＝字形线），别的线只报不补，route 前先升 manager ≥ v0.4.45。

- 文档（不动代码）：`doc/01-粗校/无法识别字.md` 加「落库以后必须过消费（谁落谁 route）」——手写事件批次落库后由落库的人当场 `guji events route`，附自查三样与全唐文 007:77:9:15 实例。

## [0.4.70] - 2026-11-19

- 发版说明（A31 11-19）：dev 头，PATCH。为带上 #722（单子体检 overturn_empty 只提示、照常上单，Sheldon 11-19 定）。

- PATCH：单子体检 `overturn_empty`（新包把人裁格判成 □／无字）从「拦」改成「提示」，缺省照常上单复审，不用再 `--ack-sheet-audit`（Sheldon 11-19：「一切以新包、新结果为准。不要用命令，直接默认」；殿本 vol02、vol16 换单曾被整册拦下）。
## [0.4.69] - 2026-11-20

- PATCH：任务库新单型 `roundcheck`（收轮检查，只读，QTW 11-20 要）＋命令 `guji round-check`：执行机上取 main 与候选包各 `seg check`（缺省 `--no-defect`）→ `seg gate`（切分根因台账交单时从 ai-team main 取最新、只留本书行随单带上，执行机不连 ai-team）→ `products diff` 翻转数 → `seg premain` → 待审格分四层（QTW cls36 口径，判序与阈值 workspace.yaml `round_check:` 书级可配）＋按 `pending_reason` 计数；结果写回任务结果，`guji round-check --collect <号段>` 收成一份汇总 tsv。交单 `guji job submit --kind roundcheck --rc-pack … --rc-ledger-book …`。文档 doc/01-粗校/收轮检查单.md。老单型的指纹不变。
- PATCH：Neon 项目 11-19 已删：任务库不再在测试分支或 `GUJI_REQUIRE_JOBSDB=0` 时退回 Neon（没有 JOBSDB_TOKEN 一律报错）；几处连库说明改成 D1 口径。

## [0.4.68] - 2026-11-19

- PATCH：`cellvotes draft --items` 不再把旧单上投的条目票按条目现格写新事件（ZM 11-19 复测 v0.4.67：vol01 r9／r15／r16 单上的票拿现行包同号格的字框写，88:1:12a 写成「領」、18a 写成「武」）。条目票的投票单 `rev` 不是现行单的，拿出来列进 `old_sheet.tsv`（当年落过的人裁由绑定表跟着改绑；没落过的要用当年出单包另落），只报不写；`guji collect` 的落文本跟着不再带这些格。

## [0.4.67] - 2026-11-19

- PATCH：修 v0.4.66 `guji collect` 落错格（ZM vol01 演练 11-19：88:1:12a 領 应改绑到 13a、88:1:18a 武 是迁移前旧格）：要落的字一律取 cv `feedback.lookup.human_chars`（seed_admit 人裁通道同一口径：过绑定表，只认现格 valid／rebound、按改绑后的格号），不再按事件原格号取字；`--batch` 也过绑定表取改绑后的格；`human_chars` 算不出（缺缓存等）就停、不落 book-text。
- PATCH：`cellvotes draft` 判「与已有人裁一致」只认在出单包上绑定有效、且现行 `human_chars` 就是这个字的人裁：迁移锚、改绑、作废、被撤的旧人裁不再让新票被跳过（ZM 11-19：vol02 75:7:11、vol18 33:4:7a、70:6:16），这些格的票照写新事件；`--no-bind-check` 关掉。

## [0.4.66] - 2026-11-19

- PATCH：新命令 `guji collect`（`guji_manager/collect.py`，收单快路，ZM 第一册线要的「一条命令收一张单」）：没换包时，读票（`cellvotes draft --from-kv --items --pack rev-<rev>`）→ 写人裁 → 定字票逐格对 book-text dev 现文、不同就直接写人裁的字（格框对不上、以图代字格不写，等重放），标点专名校验字跟改、升 patch、`local_check --dev`、推 dev（1.x 推分支开草稿 PR）→ 条目结案 → `db sync` 一次 → 只发这一章并核线上单。不重放 seed_admit、不重出单；`--batch` 另把库里早先写下、还没进 book-text 的人裁批次也落了（过绑定表、每格取最新）；断点续跑（`reports/<册>/_collect/<rev>/state.json`）；`--dry-run` 演练；`--books auto` 读一遍网站条目票挑有新票的册；「与已有人裁一致」跳过的票也落（早先落库、book-text 没跟上的）；拉库／读票／落票／推库遇网络超时在单步内重试；多册一起发站一次（ZM 11-19 B 轮时间账四点）。`swap.booktext.do_book` 加 `merge`／`title`／`store_lineage` 参数（缺省行为不变）。
- PATCH：修 `cellvotes write`（`--items` 草稿）落票后从没把条目标已裁：草稿行只有 `id`（`vol04:15:8:20`）没有 `a`，按 `a` 找条目一条都找不到（ZM 收单一直手工 `pending resolve`）。
- PATCH：放行格回库 `lib_backfill.select` 与 `--from-pool` 跳过定字时字形对照判「异」的格（`evidence.verdict == "diff"`，统计项「对照判异」）：史记 11-19 全书 42 册回库报告里这类 11 格看图全是切坏、带框线或邻字的格。不动产物、指纹（L0）。

## [0.4.65] - 2026-11-19

- 发版说明（A31 11-19，PATCH）：#704（QTW variant_compare）11-19 从 dev 分支直接合进 main，把下列 dev 上未发版的改动一并带进了 main；本版在此基础上加 #705，下列条目都随 v0.4.65 发出。
- PATCH：`tools/开书/出v01.py` 调 republish from-pack 透传 `--chapter`／`--text-id`（SJ 11-19：工作区目录名不是 `<书id>-…` 时，史記 `sjws`，plan.json 落成 text_id=sjws、chapter=01，push 写到 proofing/sjws/01.pending.json、雪碧图按 sjws 命名；book-text 章文件成 01.char.json）。text_id 只从 workspace.yaml `id` 取（缺就停）；章号先认新参数 `--chapter`，再按 cv 册配置 volume 推，再退到册号数字，统一三位；收尾提示的 push 命令也带上这两个参数。

- PATCH：放行格回库 `lib_backfill.select` 跳过夹注半格看图放行的格（cv `vis_ruling_half` 写的 `evidence.half`，统计项「半格看图放行」）：半格字块切偏多，没有人裁的不入库、不当可信刻例，有人裁走人裁入库（A23，Sheldon 11-19 同意；口径见 ai-team domain/CV/字形领域/格号后移评估-殿本row_segment与史記半格-2026-11-19.md）。不动产物、指纹（L0）。

- 库文一致（`glyph_lib.text_check`）缺省由只报告改为自动处理（Sheldon 11-18 定，全唐文 d1 实跑验证改标进文本后）：整册跑完能确定的改库标、撤机器例，其余进待审；只想报告写 `text_check: report`。这台机器过不了改库护栏（借库跑批、部分副本、本机库比账本旧）时自动退回只报告并说明。
- PATCH：形近字对归属表加可选字段 `variant: true`（标同字异形的对，如淸清；cv #1700 第 7 步 `pair_form` 只对它自动改字，异字对只记证据进复审，Sheldon 11-18 同意）。

- PATCH：缺页（cv #1696 册 yaml `gaps:`，Sheldon 11-18 定只按图片页号记）：`guji collate` 的 JSON 报告加 `gaps`（落在这批页的缺页），命令行列出「第 N 页之后缺…，整理本在此断档属正常」；cv 还不认 `gaps` 时给空表。文档：`doc/参考/册配置.md` 字段表、`开书全流程.md` S7 加「查缺页」一步与经验 E7-6。

- PATCH：新增形近字对归属表（`guji_manager/pair_attribution.py`，数据目录 `config/groups/pair_attribution.yaml`）：一对字按刻形（缺省）、按文意还是暂归一，写在一张书级表里（Sheldon 11-18 同意的第 5／7 步统一方案第 1 步）。新命令 `guji-manager pair-attr show <两个字>`、`pair-attr check`（与码位表、按对分类器的归文意名单与档位、第 7 步只挂文意的组、暂归一兜底对一遍，只报不改）。还没有任何步骤读这张表，产物不变。文档 `doc/参考/形近字对归属表.md`。

- PATCH：新命令 `guji glyph-db backfill-audit`（`ops/lib_round_audit.py`）回库事后核（Sheldon 11-18 定「回库闸关着，做按轮事后核」）：给前后两轮产物根，逐格比 `seed_admit`／`glyph_match`，新增待审格按后一轮库首位（或新进前 5 名）归到回库字（害），新放行格按放行字或库首位归到回库字（帮），列出只害不帮的回库字；`--apply` 对这些字的全部回库刻例追加 `glyph_audit` 撤库事件、直接处理并导出账本（人裁刻例不动）。史記 r79→r80 全书实测：只害不帮 407 字 967 例，与 SJ 手工 g27 剔除单 403 字重合 396 字。文档 `doc/01-粗校/开书/回库事后核.md`；顺带补上 `放行格回库.md` 里 #679 漏填的实测占位（STEAL_VALIDATION）。

- MINOR：放行格回库规矩重定（Sheldon 11-18：确定了的格都该入库，每字上限 20，不录重复字形，人审与自动区别对待）。原来只收 `rare_ref`、`witness3`、每字补到 3 例，全唐文库 64% 的字头只有 3 例或更少，占放行格 91% 的 `match_ref` 一格不回库。现在：①通道分档，乙档（`match_ref`、`rare_ref`）补到 `cap`（缺省 20），丙档（`witness3`、`ref_lib`、`match_replace`、`match_margin`、`coord_fallback`）只补不足 `thin`（3）例的字，文意通道与库自证通道不进；②`match_ref` 的格放行字领先别的候选字不到 0.003 不进；己已巳、日曰 不进；③挑有区别的例：用 5a 跨书通用底座 `glyph_sim_base_v1` 的向量，与已有例相似度 ≥0.975 算重复不进，每次挑离已有例最远的，每册每字最多 2 例，已有 ≥3 例而都不像（<0.75）的算离群不进；④证据记 `tier`；⑤一次性补历史册分两步，`--pool <目录>` 各册并行出候选、`--from-pool <目录>` 统一挑并入库（`run_pools`）。字体模板核验（首位＝放行字）照旧。`workspace.yaml` `glyph_lib.auto_backfill` 新认 `tier_c`、`thin`、`per_book`、`dup_sim`、`far_sim`、`match_ref_gap`；写死了 `cap: 3` 或 `channels` 的书不会自动换成新缺省。整册跑完的自动回库每册要多取几千格字块（缓存热时约 10 分钟）。依据（各通道入库后改标率、上限与挑例实验）见 `doc/01-粗校/开书/放行格回库.md` 第九节；粗校验收线不再把「3 例」当够了。没做：满额置换、人审入库的图像体检、5a.3 分类器同意。

- PATCH：放行格回库加抢首位核验（可选，缺省关；史記 r80：g26 回库 9,678 例后多出 987 格待审，482 格是常用字格的库首位被回库进来的形近少见字／异体抢走，SJ 事后剔 403 字出 g27）。开了以后，字体模板核验过的候选按册整批模拟进库（cv #1679 `BackfillProbe.steal_check`，A22），用本册已放行格回放：库首位被新字抢走、又没有格被它救回的字整字不进，报告记 `near_common`，同一次跑后面的册不再选。开法：`workspace.yaml` `glyph_lib.auto_backfill: {steal_check: true, steal_cells_max: 8000}`（0＝全部）；手动 `--steal-check`／`--steal-cells-max`。缺省关的理由：史記第 02 册真放行格全册回放（5 万格，40 分钟）只拦下已知害字 17/68，同时拦下已知帮字 8/47；只看形状的门槛（形近常用字进前 3、分差 <0.01）A22 与 A31 各自标定也分不开。cv 没有 `BackfillProbe`（早于 #1679）或核验出错时不挡回库，摘要行带「⚠ 没做抢首位核验」；没开时带「（抢首位核验未开）」。`_cv` 登记 `BackfillProbe`（OCR 半成品漏了这条，闸会永远走「cv 太旧」）。文档 `doc/01-粗校/开书/放行格回库.md` 第三节补「抢首位核验」与实测，建议改按轮事后核（SJ g27 的做法）。

- PATCH：执行方领单前的各册目录清扫（`GUJI_JOBS_SWEEP_GB`，缺省 8 GB）加冷却：扫一遍后 10 分钟内（`GUJI_JOBS_SWEEP_COOLDOWN_S`）不再重扫，清不出东西时只打一行说明。原来剩余空间在 3–8 GB 之间且没有可清的册目录时，空闲执行方每个轮询周期都重扫、重打日志（worker-34 剩 7.9G 的空转）。高于领单门槛（3 GB）一直照常领单。

- 修：字形库体检撤库／改标（`glyph_audit evict`／`relabel`）作废人裁事件的范围收窄（殿本 vol01，11-18）。作废标记按格号记在 `feedback/lists/stale_verdicts.tsv`，会作废该格此刻以前的全部人裁；库例挂着旧格号、或库文一致按文本的人裁改库标时，这格现行的人裁定的是另一个字，被一并作废后下一轮掉回机器字（vol01 `ZM-vol01-libfix-20261118` 26 条里 21 格）。现在只在这格最后一条人裁定的就是被撤／被改的旧字时才作废，否则不动事件、`decisions.jsonl` 记 `kept_human_event`；查不到人裁事件的照旧作废。
- PATCH：执行方整机暂停醒来后不再续跑已被收回的单（11-18 同一单被两台同时报在跑：#5450／5421／5458／5431）：①每个步骤（含存包）开跑前用心跳结果查租约，已被 reap 收回（lost）或有人叫停就不开跑、不存包；②心跳线程先续租查归属，再写 worker 状态和看板（原来先写看板，中心库慢时迟迟发现不了租约已失，还会先报「我在跑这单」）；租约已失就不再写 busy。

- PATCH：执行方自更新（`_refresh_runner`）ff 失败时，若 runner 检出是 detached HEAD 且工作区干净（准备脚本把它切到了单上钉的 cv：tag、rc 头、功能分支提交，HEAD 不在 origin/dev 线上），改为 `checkout --detach origin/dev`，不再「拉不动」自退；有未提交改动仍不动并写日志。

- PATCH：放行格回库数「各字现有刻例」时不再把借来的刻例算进去（`ops/lib_backfill.lib_state` 排除 `borrowed` 表；OCR 研究 Project 11-18，Sheldon：新书快审能否部分自动入库）。借库的新书此前本书没有的字被当成不缺例，一格都不补（脉经本书 570 字头被数成 4,336）。不借库的书行为不变。文档 `doc/01-粗校/开书/放行格回库.md` 加第七节：借库阶段把 `match_ref` 加进回库通道顶替大部分冷启动快审，附脉经第 1 册实测（人审 1,189 格与机器放行字全部一致）。

- PATCH：执行方自更新（`_refresh_runner`）失败时把 merge 的 stderr／超时写进日志，merge 超时 120→300 秒（`GUJI_JOBS_REFRESH_TIMEOUT_S`）。11-18 多台 runner 同时「dev 有更新但拉不动」自退，检出是干净的 detached HEAD、手动 ff 正常，当时看不出原因。
## [0.4.64] - 2026-11-19

- PATCH：`guji swap book-text` 格改 □ 后同步校验字按 A33 11-19 口径补全：matched_multi 的 `targets[].part` 全写且拼起来等于旧文字时按段长切回新文字（F-OV-14）；认不出的字格（unk）照新包落 □ 的也同步；提交说明分列标点 pre_char／专名 text 处数，另列「专名含□待复核」（改后 □ 占一半及以上或首尾成 □）。锚点、span、target 其余字段、无 pre_char 的标题符一律不动。merge_chars 先判 unk 再判 〓→□，报表不再把认不出的字格记成占位。

## [0.4.63] - 2026-11-18

- 发版说明（A31 11-18，PATCH；main v0.4.62 ＋ 下面四个 PR 摘取，**不含** dev 上别的未发版改动）：给殿本换单（ZM）用。
- PATCH：`guji swap book-text` 处理以图代字格（#692，ZM 11-19 殿本 vol20）：带 `fig` 的 □ 格照新包、不留旧 〓／人裁字（V2 HARD）；旧文本占位 〓、新包落 □ 的照新包；挪锚前把这些格在标点 `pre_char`、专名 `text` 里的那一位改成新字（bump punct 不再拦）；拷 fig.json 后 index 补 `fig_file`（F-OV-13）。
- PATCH：新命令 `guji swap doctor`（#687）：换单开跑前自检令牌、`-w` 路径、cv 版本、book-text 稀疏检出、CNN 权重、磁盘；`--fix` 补模型与稀疏检出，`--env` 打印 export 行。`swap` 的 `--books` 对 doctor 可不给。
- 文档：`doc/01-粗校/换线上人审单.md` 加「殿本批量换单（auto_cycle）」一节、页表只换 rev 不算换源（#688、#690）。

## [0.4.62] - 2026-11-18

- 发版说明（A31 11-18，PATCH；按用户 11-05「manager 发版一律 PATCH」，下面记 MINOR 的「库文一致」也按 PATCH 发）：dev 头 84f3084，含 #654、#661、#662、#664、#665、#666、#667（配 cv v0.7.68 的 seg check「cv丢笔」）。

- PATCH：`guji seg check` 新处置「cv丢笔」（全唐文切分线 11-18，R033／R038 复盘）：并入 cv 两条新墨账，`erased`（清界行把字笔当界行抹了，ERASE）、`bbox_drop`（字所在那几行有成块墨落在所有字框外，DROP）。这类格位对、墨被清理步骤丢掉，原来对位、格高、漏切都不报，或报成「需钉子」（覆盖行修不了）。排在需钉子之前，切分不回退闸照结构类算。要 cv ≥ 含 erased／bbox_drop 的版本；旧 cv 没有这两张表，等于不查。
- PATCH：中心库按页读（备份、开分支复制、SqlSource）对 files、imports 起步 20 行，Worker 回包太大回 500 时页减半；备份导出期间有人写时只重导 changes 记到的表，changes、imports 只补新行（D1 没有快照读，原来整库重导追不上写入）；备份逐表打进度。首份 D1 备份因这两处失败。
- PATCH：库文一致按殿本 vol01 反馈再修两处（ZM 11-18）：「文本是人裁」改库标前先过字体模板，库图不像人裁的字就不改标（重切后挂着旧格号的库例，机器来路的撤、人裁来路的只报）；己／已／巳 互异不算不一致。
- PATCH：库文一致按史記首跑反馈修三处（SJ 11-18，75 格全看图）：页的计算时刻认 `seed_admit/_manifest.jsonl` 的 `ts`，不再用文件时刻（取包会刷新，两格该判文本过期的被判成跟人裁改标，`--apply` 会把刚更正的库例改回错字）；新增 `shifted` 类（库标正是同列上下邻格的字＝库图是旧切分字块，机器刻例撤、人裁刻例只报，排在人裁改标之前）；字体模板重新识别改库标要求首位领先次位 ≥0.03，不够的进待审复审；模板首位既不是库标也不是文本字的，改成只进待审复审、不撤库例（史記这类 13 格库图都对）。
- PATCH：叠图底图可选彩图／二值／灰度＋二值体检可疑区（彩图书双层显示，用户 11-17 定）：`render.overlay.overlay(..., bg="color"|"bin"|"gray", qc=False)`，缺省与改前逐像素相同；`bin` 读 cv 整页二值副本，没生成退回原图；`qc` 画 cv `binarized/<书>/<页>.qc.json` 的 color_mark／bin_diff／speckle 框。`_cv`、`console_api` 登记 `binarized_or_none`、`read_qc`、`canon_box_suspect`（要 cv ≥ #1650）。文档：`参考/册配置.md` 加 `ink`，S0 开书体检加「墨层与二值」一步（新书缺省写 `ink: {}`）。
- MINOR：库文一致（Sheldon 11-18「字形库和实际的文本应该要是一致的」，过程要自动）。新 `guji glyph-db text-check --books … [--apply]`（`ops/lib_text_check.py`）：库里每个刻例的字按书级码位归一后对本机 `seed_admit` 产物同一格的字，不一致的分类处理：库例晚于产物的页标失效待 `rerun --stale`；文本是人裁的库例跟着改标；两边都是机器的过字体模板重新识别（认成文本的字则库改标且保持机器来路，认成库标则这一格进待审单复审，都不是则撤库例并回人审）；库是人裁而文本没采信的进待审单复审；格已不在的机器刻例撤掉。`guji pipeline` 整册跑完自动比一遍，缺省只报告，`workspace.yaml` `glyph_lib.text_check: apply` 才处理、`false` 关，`GUJI_LIB_TEXT_CHECK=0` 临时关。`glyph_audit relabel` 认 `payload.provenance: "auto"`（只对机器来路刻例有效）。文档 `doc/01-粗校/开书/库文一致.md`。全唐文 b2 产物 001–045 册首跑：36,044 例里不一致 145（另 13 格在待审）。

## [0.4.61] - 2026-11-17

- PATCH（#653，随 dev 头带入本版）：待审格与人改字不留阙文（用户 11-18「只有真的阙字才显示阙文」）。swap book-text 换完仍是 □ 的待审格按新单 `first_choice` 写首选字、去 lacuna；`overlay_edits` 人改字叠回新包改成真字时去 lacuna／guess_c（殿本 68 格「标了 lacuna 却有字」即此来）。
- PATCH：连中心库的令牌先 GUJI_DATA_TOKEN、再 GUJI_DATA_TOKEN_PROD（实验分支先 _EXP）、_READ，回 401 换下一把（云端会话的 GUJI_DATA_TOKEN 是占位值）；测试一律清掉中心库令牌（之前有测试会真写看板）。
## [0.4.60] - 2026-11-17

- 发版说明（A20 11-18）：dev 头，PATCH。中心库切 D1（用户 11-18「开始切换」），执行方升级后只要 GUJI_DATA_TOKEN。
- PATCH（按用法算接近 MINOR，用户 11-18 定切换时一并发）：中心库从 Neon 迁 Cloudflare D1。`datastore` 全部改走 data.open-guji.com 的 `/v1/sql`（`d1conn`／`d1sql` 垫片翻译老的 Postgres 写法，写入带库版本守卫、整批原子）；执行方只要 `GUJI_DATA_TOKEN`，不再要 `NEON_DATABASE_URL`／psycopg。大文件原文进 R2；`progress.put_*` 改 Python 实现；实验分支＝独立 D1 库，`db branch create -w` 按工作区复制。
- PATCH：任务库隧道线程（`jobs/jobsdb.py`）若死了（事件循环崩），`_tunnel_port` 换端口重建，不再一直连不上；线程退出会在 stderr 留一行（专家 11-18，runner 大批消失排查时发现的小洞，没证据真发生过）。

## [0.4.59] - 2026-11-17

- 发版说明（A31 11-17）：dev 头，PATCH。为带上 #648（cellvotes draft --allow-empty，殿本 21–99 册零票换单）；同带 dev 上已合的任务库磁盘清理两条。

- PATCH：`guji cellvotes draft --allow-empty`（ZM 11-18，殿本 21–99 册旧单没人投，swap run 整批被「读到 0 票」守卫拦下）：确实零票时出空草稿好照常换单。守卫不关：只认 `--from-kv` 当场从网站读全的结果，按单版、按条目两种记法这一章都要 0 条，且没有「条目找不到」被丢的票，否则照旧拒绝；票文件不认。meta.json 记 `empty_confirmed`（两种条数、读取时间）。配合 cv proof_cycle／auto_cycle 零票册自动带它。
- PATCH：执行方成功存包后，除 `cache/<册>`、`products/<册>` 外也清 `data_full/<册>`（`guji source pull` 取的原图，真源在中心库，下一张单 prep 会再 pull）。执行机磁盘总不够：书仓本身很小（殿本约 157 MB），占盘大头是跑单产生的本地数据，原图一直没人清。只改 `jobs/runner.py::_clean_book_artifacts`，`GUJI_JOBS_KEEP_ARTIFACTS=1` 仍可关。
- PATCH：领单前磁盘低于 `GUJI_JOBS_SWEEP_GB`（缺省 8 GB，0＝关）时，扫掉本机各工作区所有册的 `cache/<册>`、`products/<册>`、`data_full/<册>`（册号取自数据目录 books/*.yaml，`cache/_judge` 等非册号目录不动），再才轮到清 uv、guji-data 缓存。成功存包只清了本册，失联、失败的单和更早的册的残留一直在（worker-27 实测：全唐文仓 data_full 3.1G、cache 2.4G，史記仓 cache 3.4G）。`GUJI_JOBS_KEEP_ARTIFACTS=1` 同样关掉它。只改 `jobs/runner.py::_disk_gate`。

## [0.4.58] - 2026-11-17

- 发版说明（A31 11-18）：PATCH。为带上 #640（db pull／sync 增量拉，收单提速）；同带 #641（文档：收单真源）。

- PATCH：`guji db pull`／`db sync` 增量拉（A31 11-18，收单提速）：库里在基准 rev 之后有改动时，按 `changes` 表只取改了的文件，不再读整个工作区的清单和全部文件；逐行大台账（字形库 instances、exemplars、events 等）本机那份还是基准版本时，只按变更主键补改了／新增的行，整文件 sha 对上才用，对不上该文件照旧整取。殿本（6665 个文件）有 4 个文件远端改动的 sync 97 s→20 s；增量 pull 结果与整拉逐字节同（实测 rev 1071330）。整批导入、变更超过 2 万条、文件超过 400 个、旧数据源、`pull --force／--exclude／--repair-gaps`、新机器都照旧整拉；`GUJI_DB_FULL_PULL=1` 强制整拉。输出多 `scan`（incremental／full）、`changed_files`、`patched`。
## [0.4.57] - 2026-11-17

- 发版说明（A31 11-17）：dev 头 a70051d，PATCH。主要为带上 #630（任务库：收尾不改已被收回的单、心跳区分租约已失与有人叫停、跑单每 5 拍顺手收回过期领单、同优先级失联单先领）；同带 #637（swap run／book-text／finish-merged 支持非殿本册名）。

- PATCH：任务库 `finish` 先查这次领单是否已被 `reap` 收回；已收回（整机暂停后醒来的旧会话）只记事件、不改任务状态。以前旧会话心跳拿不到租约当成「有人要求停下」，把已退回排队／在别处重跑的单写成 cancelled（殿本 r12g24d #4991–4995，查不到取消人）。
- PATCH：任务库心跳区分「有人要求停下」（`cancel`）与「租约已被收回」（`lost`），后者日志记「租约已失」；执行方跑单时每 5 拍（`GUJI_JOBS_REAP_EVERY`，0＝关）顺手 `reap` 一次，失联单不再等到有执行方空下来才退回排队（史記 r79 #5107 收尾晚于租约 16 分）。A30 11-17 建议。
- PATCH：领单排序在同优先级里让失联被收回的单先领（`_CLAIM` 加 `outcome='lost'` 一项）。被退回的单 `created_at` 不变，以前排在更早交的整批单后面，史記 r72／r79 重领要等 44–50 分（SJ 11-17 核实，不是同册互斥）。
- PATCH：`guji swap run／book-text／finish-merged` 支持非殿本：`--books` 认纯数字册名与区间（`001-045`、`01-42`），章号、线上单 rev、发布 `only=`、字形库格键前缀、对照表一律按册名推（不再 `int(册名[3:])`）；纯数字册名不给 `--text-id` 就停；book-text 提交说明不再写死「殿本」。
## [0.4.56] - 2026-11-17

- 发版说明（A31 11-18）：PATCH。为带上 #634（swap book-text 1.x／0.x 只差码位归一的格文本留现行字，ZM 报 vol01 26 格改反）。

- PATCH：`swap book-text`（含 1.x `swap/<册>-1x`）只差码位归一的格文本留现行字，同 0.x 出单（ZM 11-18：vol01 26 格 宫→宮、歩→步 等被改反）。两处：①码位表直接读数据目录 `config/codepoints.yaml` < `book_defaults.yaml` < 册 yaml（`charnorm.codepoints_of`），不再靠 cv 找册、找不到静默退成字面比；②有人裁且人裁与现行只差码位时留现行字，不落人裁的原码位。码位表为空时在报告 notes 里提示。
## [0.4.55] - 2026-11-17

- 发版说明（A31 11-18）：PATCH。带 #624 放行格自动回库**对所有书缺省开**（Sheldon 11-18 在卡片上定）和 #628 db sync 增量推。回库只改本机字形库：跑批机不 `db sync` 结果就留在本机；上中心库须在有完整副本的机器上 `guji db pull`（不要 `--no-rebuild`）后 `guji db sync`，推前先 `guji db push --dry-run` 看 glyphs／glyph_instances／glyph_exemplars／glyph_admissions 各表 delete=0。关法：`workspace.yaml` 写 `glyph_lib.auto_backfill: false`，或 `GUJI_AUTO_BACKFILL=0`。

- PATCH：`db sync`／`db push` 增量推（2026-11-18，收单提速）。只改了待审单、人裁事件、册 yaml 这类主键带文件路径的文件时，只扫、只比这几个文件的行（字形库各表照旧全量）；文件清单的 sha 按大小＋修改时间缓存在数据目录 `.central-shacache.json`；`_walk` 改 `os.walk`。殿本一册有本地改动的 sync 从 64 秒降到 8 秒。`GUJI_DB_FULL_SCAN=1` 退回全量、`GUJI_DB_NO_SHA_CACHE=1` 关缓存。
- PATCH（原记 MINOR）：放行格自动回库改为**缺省开**（Sheldon 11-17 定）。`guji pipeline` 整册跑完没有失败页就对该册回库；不要的书在 `workspace.yaml` 写 `glyph_lib.auto_backfill: false`，或设 `GUJI_AUTO_BACKFILL=0` 临时关。回库只改本机字形库，跑完要 `guji db sync`。史記、殿本各两册只报告试跑并抽样看图后定，数字见 `doc/01-粗校/开书/放行格回库.md` 第六节。

## [0.4.54] - 2026-11-17

- 发版说明（A31 11-18）：PATCH。主要为带上 #617 放行格回库（全唐文开 `glyph_lib.auto_backfill` 用；缺省关的新功能按规矩算 PATCH，下面条目里写的 MINOR 以此为准）和 #622 字形库推库补洞（回库前必须有）；同带 #612、#615、#618、#619、#620、#623（`guji job precheck`／`job stats`）与 #590 任务库失联不占重试额度。

- PATCH：`guji job precheck` 交单前逐册核生效的 cv／code／glyph_pin／corpus 钉子；`guji job stats` 按领单记录算排队、运行与多次领单的时间账（#623）。
- PATCH：字形库推库补两个洞（全唐文开放行格回库前查出，2026-11-18）。①`db pull --no-rebuild`（含换单 `GUJI_DB_NO_GLYPH` 的 sync）拉到新字形账本却没重建 glyph.db 时，状态记 `glyph_db_stale`；之后 glyph.db 没被动过的，下一次正常 `db sync` 先按账本重建；被动过（回库、落库写进了旧库）就拒导出，免得旧库盖掉账本、推库删掉别人新加的刻例（少于 5% 缩水闸拦不住）。`GUJI_ALLOW_STALE_GLYPH_EXPORT=1` 放行。②`GUJI_GLYPH_DB` 指着别的书的库时，`db pull/sync` 的字形库钩子与 `glyph-db backfill --apply` 一律拒跑。③放行格回库入库前另核：部分副本（`pull --exclude`）推不上中心库，拒入库。
- PATCH（原记 MINOR）：放行格回库。机器放行（`rare_ref`、`witness3`）而库里不足 3 例的字，取管线字块、按入库后的图过字体模板核验（首位＝放行字）后以 `provenance=auto` 补进本书字形库。`guji glyph-db backfill --books … [--apply]` 手动跑；`workspace.yaml` 写 `glyph_lib.auto_backfill: true` 后 `guji pipeline` 整册跑完自动对该册回库（缺省关，`GUJI_AUTO_BACKFILL=0` 临时关）。回库事件带 `backfill` 标，`glyphdb_admit` 可重放（`db sync` 取中心库字形库后不丢）。不开开关行为不变。文档 `doc/01-粗校/开书/放行格回库.md`。
- PATCH：seg check 钉子集合加上册配置 `row_segment.page_map_overrides` 里带 `cuts`／`slots` 的覆盖行（人核格线／格位；`drop` 不算），这些列有结构旗记「已钉·复核」、不进闸；`reference_profile` 声明 text／none（无逐列参校）的页上只有 pair 的对位串错记 `ALIGN_NOREF`，只当提示「对位串错·无逐列参校」，split／run 照算结构（全唐文 11-17 b1 闸 039:78:1：碑誌 text 页放行少凑够 pair、切分对，覆盖行已钉仍报需钉子）。
- PATCH：R01 `ref_lacuna` 卡片提示、判定说明带上 ▣（以图代字）；文档 `01-粗校/待审原因/ref_lacuna/README.md` 写明〓／▣ 口径（语义相同、只在成因 A2 明细上分开、换含 ▣ 语料先钉认 ▣ 的 cv）。
- PATCH：任务库 `reap` 里失联（租约过期）前 5 次不占重试额度（`GUJI_JOBS_LOST_FREE`，缺省 5，0＝旧行为）。执行机整机暂停是平台行为，长单（史記、全唐文）三次失联就判 failed 太严；超过 5 次失联仍占额度。只改 `jobs/store.py` 的 `reap`，不改表结构、不改领单与租约时长。

## [0.4.53] - 2026-11-16

- 发版说明（ZM 11-16）：dev 头 51787ff，PATCH。主要为带上 #607（整理本占位符区分：`reasons.ref_missing`、`taxonomy`、`causes`、`cards`、`sheet_audit`、`release_gates`、`exit_check`、`close_check`、`review_breakdown` 认 `▣` 以图代字为整理本缺字，成因 A2 `detail="image"`；配 cv ≥0.7.52，殿本换含 `▣` 的整理本新语料用）。同带 #600–#606、#608（swap.booktext 标点迁移、online_lists 落后判定与子进程路径、seg premain INK_BLANK、cellvotes `--no-consume` 补排除名单、粗校 R5 rough 第 12 项、5a 文档）。

## [0.4.52] - 2026-11-16

- 发版说明（A31 11-16）：dev 头 22e49e3，PATCH。为带上 #597（`guji pagekinds` 核半文半表页 `page_kinds.table_cols`、进度看板不把 `table_column` 拒掉的列算坏列；配 cv v0.7.47 史記 patch 线或 dev 含 #1590）。老 cv 读不到 table_cols 参数时为空，行为不变。

- PATCH：`guji pagekinds` 读册生效的 `column_gate.table_cols`，核 column_gate 产物点名列是否都按 `table_column` 拒收，对不上报 ✗，报表多一行「半文半表页」；进度看板 `cols_bad` 不算 `table_column` 列（GUJI-772，#597）。

## [0.4.51] - 2026-11-16

- 发版说明（A31 11-16）：dev 头 253340f，PATCH。主要为带上 #594（`pending_fields` 带 `pending_reason`，SJ v0.1 预检）；同带 #587、#591、#592、#593（seg premain 标 main 前硬检查）。配 cv ≥0.7.46 时 `pack_purity` 不再把只改语料钉判成混版本。

- PATCH：`review.proof_fields.pending_fields` 带上卡上已判好的 `pending_reason`／`pending_reason_detail`（`cards()` 出卡时 `stamp_cards` 判的）。SJ v0.1 预检 11-16：跑批本机拿 `cards()`＋`pending_fields` 离线出的 42 册待审单没有原因码，`pending-stats --from-dir` 全记 unknown。republish 出单随后照旧按 `reasons_for_pending` 重判覆盖，线上单不变。`ops/pack_purity` 补测试：cv ≥0.7.46 的「语料钉变了」不算混版本。

## [0.4.50] - 2026-11-15

- 发版说明（A31 11-15）：dev 头 bdc138a，PATCH。主要为带上 #584（`guji corpus pin --same-output-as`，殿本／全唐文改钉底库 b25 用，要配 cv ≥0.7.40）；另含 #581、#582、#583、#558。rc 上补：测试 `from_cv/test_code_deps_coverage.py` 登记 seed_admit→groups.part_shape（cv #1553 新加，缺省关，同 wu_shape 口径），dev 头 CI 因此红。

- PATCH：`guji corpus pin --same-output-as N`（A22 11-15）：语料等价登记，册的新总号沿用总号 N 的语料指纹（cv `corpus_pin.append_pin(same_output_as=)`，要 cv dev 含该功能；旧 cv 报「先升 cv」）。`--note` 写证据。

## [0.4.49] - 2026-11-14

- PATCH：`guji corpus build` 出书库清单前扫参校本（group=reference、root=ws 的 .txt）里的缅甸文码位 U+1000–U+109F（殆知阁缺字图占位码），有就拒绝出版本，报处数和前 5 处行号（A20 11-14，史記 v2 73 处、殿本 v17 233 处都是导入漏转，#577）。
- PATCH：测试 `from_cv/test_code_deps_coverage.py` 跟 cv dev 同步：border_detect_gate 已不 import pagetype_model，删存量条目；seed_admit→groups.wu_shape（cv#1509，缺省关）登进 NOT_IN_FP 并注明模块代码不进指纹。

- PATCH：seg check 加书级口径「只当提示的旗」：`BOOK_HINT_FLAGS`（按 book-text id）＋workspace.yaml `seg_check.hint_flags`（写了优先，[] 全按结构）；史記写本缺省 BLOCK 字块过高只当提示「书级提示」，殿本不变（A22 11-14：SJ 抽 25 列 0 真错；r59 后人钉 77 列里带 BLOCK 的 14 列都另有结构旗，召回不变）。

- PATCH：seg check 劈字弱档（cv `cut_through` level＝弱，挪不到 1/3 格高）记 `CUT_WEAK`，只当提示「劈字弱·笔画相触」，不进闸（史記 SJ 11-14 看图，A22 量过人钉列不掉召回）。要 cv 含 #1538。

- PATCH：seg check 列清单：cv `align_drift` value 带 `page`（同页报出 ≥3 列）的记 `ALIGN_PAGE`，降成提示「对位串错·整页」，不进闸（史記 R017 SJ 抽看，A22 11-14）。要 cv 含 #1536。

- PATCH：seg check 列清单收 cv `align_drift`（对位串错·疑整列错位，史記台账 R017，A22 11-14），flag `ALIGN`、算结构「需钉子」；不按 A6／A9 排除（劈出的那格整理本本来就没字）。要 cv 含 #1535。

- PATCH：seg check 列清单把 cv `geo_ref_ok`（格高／半格宽离群但参校字证实、不报结构的格）列成处置「格高·参校证实」（类「提示」），不算结构、不进 `seg gate`，写本册可抽看（SJ 11-14：R011 那批里混有真错；A22 用 SJ 新钉 21 列量过，豁免没放过一列）。

- PATCH：`guji seg check` 读 cv 新表 `block_tall`，字块过高 BLOCK（cell_shrink 字块比本格格线高 ≥1.35 倍）计结构分 3、进「需钉子」（ZM 11-13，殿本 vol06 147:3:3：格线对、字块连上长竖线，旧版只有 Lv 判公用清格而漏）。要 cv ≥ #1522 的版本；旧 cv 没这张表时无影响。
- PATCH：seg check 写本误报（史記台账 R011／R012，A22 11-13）：① 同字对照切坏检测认书先读 `workspace.yaml` 的 `id:`，认不出不再静默按殿本口径跑（会把写本长笔伸出格报成 CLIP，史記 15 册殿本口径 clipped 54 列、史記口径 2 列），改为提示；② merged 两团字要墨量小比大 ≥0.20（写本列尾字脚下的句读圈、残笔不算并格）；③ 召回不把 cv `geo_ref_ok` 豁免表算报出。

- PATCH：新命令 `guji seg gate`（标 main 前的切分不回退闸，A22 11-13，Sheldon 定不要求清零）：比候选包与现役 main 两份 `guji seg check` 列清单，候选包新冒出的结构列（回退）或新页级错退出 3；已知未清的列按根因台账（ai-team `domain/CV/A22/切分根因台账.tsv`）挂根因号、没挂的列为「未登记」只提醒；出 `切分未定.tsv` 供下游跳过。文档：切分快筛十二节、四层工作法、轮报告与验收工具一览。

- `cellvotes draft --from-kv` 按单版读到票时，若该册还有按条目记的票，打警告提醒另跑 `--items`，免得漏落（PATCH，ZM 11-13，第五册 005-r13 的 25 票漏落）。

## [0.4.48] - 2026-11-13

- 体检不再对已人审的锚点格报 `anchor_only_in_cells`（PATCH，ZM 11-13）：导出单里 resolved（`review: human`）的锚点类条目留着显示结果，原先被误报（第一册 r20 的 103:5:13、103:9:7）。

## [0.4.47] - 2026-11-13

- 补发 v0.4.46 漏掉的内容（PATCH，ZM 11-13）：v0.4.46 的 tag 打在了不含下面这条的提交上，tag 里没有 `review/sheet_audit.py`（第一册线 r19 出单日志「没有 review.sheet_audit」），发版记录却已写了。这条真正随 v0.4.47 发出：
  待审单体检与锚点格出判字单（PATCH，ZM 11-13，重跑后覆盖逻辑清查）：①新增 `review/sheet_audit.py` 与 `guji pending audit <册> [--sheet 候选单] [--norm 归一表]`：机械查几类「不该进判字单」的格——机器无字被写成「机器改判为 □，推翻人裁」（`overturn_empty`）、旧人裁已失效（unanchored／review／void）却被当成「被机器推翻」（`overturn_untrusted`）、改判前后码位归一后同字（`overturn_same`）、锚点格混在 `cells[]`（`anchor_only_in_cells`）、重复格；有「拦」的类退出码 1（cv `republish.py push` 内置同一道门，`--ack-sheet-audit` 放行）。前 20 册线上单实测：87 个锚点格混在判字单、15 个假「推翻人裁」复审格。②`closeout.anchors.stamp` 把只因标点专名要重挂的新格写进 `anchor_cells[]` 旁表，不再写进 `cells[]`（`purge` 两处都清，老单里混的下次出单清掉；`anchor_cells()`／`closeout stats／list` 两处都读）。③`apply_pending` 不把 `src=closeout_anchor` 的格当待审字：不钉 book-text 现字、不填首选字。总纲 `doc/00-总览/待审单-人裁事件-book-text格子.md` 加第四节「重跑之后怎么覆盖：一个问题一个出口」。
- 另带 dev 上已合的：`seg check` 汇总加 CUT（cv cut_through 格线劈字进需钉子，#554）、char_card 1.6.4（非难认字页卡片多列排布，#553）。

- PATCH：`guji seg check` 汇总认 cv 新表 `cut_through`（F6 格线劈字，切割量＋U-Net 归属裁判，cv #1494）→ 结构类 flag `CUT`（每条 2 分、进「需钉子」），例格写「劈字强｜中 上格|下格 切割量…」。A22 11-13，Sheldon 同意并进；cv 没合 #1494 时没这张表、行为不变。

## [0.4.46] - 2026-11-13

- 出单 reconcile 不再把已有人裁的条目重开（PATCH，A31 11-13，ZM 殿本 vol01 001-r18）：条目已 `resolved`，新单又判待审时，只有「复审格（`recheck`）」或「图块指纹两边都有且不同」才重开；图没变（含机器只是又打了锚点类 A01／A02 标记）保持已裁，reconcile 结果多一项 `保持已裁`。L0。

## [0.4.45] - 2026-11-13

- 新格子类型「无法识别字」（char v0.5 `unk`，PATCH，A31 11-13，Sheldon 定、QTW 全唐文 007:77:9:15）：人裁事件 `confirm v=figure` 带 `unk`（部件描述）→ 排除名单 `unk=` → `figure_cells` 返回 `UnkDesc` → 字框 `unk` → char 格 `{c:□, unk}`，`$schema` 写 v0.5（随包带 schema 副本）；网站精校票 `choice=unrec`；`apply_pending`、`swap.merge_chars` 不回填。cv 不用改。文档 `doc/01-粗校/无法识别字.md`。L0。
## [0.4.44] - 2026-11-12

- 任务单 `run` 收 `seg check`／`seg ruler`（不收 `seg pin`，它写数据目录钉子）；`seg check --job` 把逐列清单排前、计数与结论压最后、退出码恒 0，因任务库只留每条输出末 6000 字（PATCH，QTW 11-12，#535）。
- 审阅页 glyph_quality 1.1.0：加「污渍」一档（数字键 4，看不清改 5），gq-apply 认 stain（A22 11-12，Sheldon 要建污渍尺子）。
- char_grid 1.3.2：提示语去掉「殿本字形库认的字」旧说法（字形线 11-12）。L0。
- `guji seg check` 并进同字对照切坏检测（并格 MERGED／切笔 CLIP 进「需钉子」，带框 FRAME／FRAME_HEAVY、BLEED 进「公用清格」，`--no-defect` 关），并汇总 cv 新表 page_pitch（格高对整页）、half_width（夹注半格宽）（A22 11-12，Sheldon 追问快检覆盖面）。
- `guji code release` 的下一步提示改成先推 main、再打 tag：云端走中转站 `process/tag.py guji-workspace/<书仓> <提交> k<N>`（PATCH，A20 11-09，文档）。
- 新命令 `guji seg check <册…>`：切分核查一条命令，并了 SJ 史記快筛（`tools/seg_check`，留作别名）、cv `seg_screen`、待审原因码。按列给 类／处置（钉子未生效、格号不符、版式不符、需钉子、原因码·看图、已钉·复核、对位（○）、公用清格、点名跳过、卷首页），出列清单、需看图缩略图、报告；退出码 3＝有要看图的列。点名跳过页与卷首页数写工作区 `workspace.yaml` 的 `seg_check:`。要 cv ≥ #1447。
- 新命令 `guji seg ruler`：中心库人修过的列（manual-cells、column-slots、抬头、拖线、solo-notes，含退役的）＋第一次写的时间；`seg check --recall` 只拿产物里错还在的列（manual-cells 看产物有没有用上钉子，其余看修的时间是否晚于产物）量各检查的查全。
- 新命令 `guji seg pin <册:页:列>`：整列写定（manual-cells）。从已有钉子或现行 row_segment 产物起稿，`--split/--merge/--move/--insert-after/--delete/--ys` 改格，出草稿、叠框图、格号对照表（给 `guji swap`），自动跑 cv `check_manual_cells`；`--write --why` 才写本机数据目录（同 id 原地替换、保留 history）。见 cv `doc/切分覆盖.md` 第四节。
- 测试 `test_code_deps_coverage` 登记 glyph_match → clustering.sim_cnn 不进指纹（cv #1394 `sim_model` 开关，缺省关；开着时经 sim_model_sha 进参数指纹）。只改测试（A23，11-10）。
- 单页扫描的页面范围改为**按册两遍定框**（PATCH，A20 11-10，用户要全唐文「每页都有框、框大小基本一致」）：新增 `datastore/framefit.py`——先逐页按线段量框线（不怕斜），再取全册统一框尺寸，逐页对准框线；版心一侧线淡、只剩一条框线、个别页拍大、序页抬头伸出框外都处理；缺页灰图与无框页取整幅（`fit: blank/none`）。`pagemeta.build_pages` 给了页图就缺省走它（`how: framefit`、`fit` 记定法），没装 opencv 或 `guji source pagemeta --no-fit` 退回旧的逐页 `detect_content`；`--save` 存逐页记录出审查图。框线外粗内细取外道、配上的框线略大就撑到包住、粗过 3.5% 的墨团不算线、书名签小框与封面不猜（`fit: unsure`）。全唐文 11,238 页：退整幅 775→0（另 6 页本无框），框宽在中位 ±3% 内 57%→99.6%；北行日錄旧法退整幅的 3 页也框上了。只影响旁车，不动页表、不让产物过期。L0。

## [0.4.43] - 2026-11-10

- 修史記 anchors/04.jsonl 拉不下来（PATCH，A31 11-10，GUJI-750）：根因是 SJ-史記切分 rev 957032–957044 那次 push，04.jsonl 里 4 对行主键重复（第 56–59 行与 61–64 行），旧扫描「后者覆盖」只存了 61 行，source_files 却登记 65 行／整文件 sha，库里谁都还原不出（「还原后 sha 不符」）。①`guji db pull --repair-gaps`：缺行文件按库里现有行还原并列 repaired，本机文件与登记 sha 不同，下一次 db push 把它推回去修好登记；②push 前拒推：要推的文件里有同主键重复行即报错（`GUJI_ALLOW_DUP_KEYS=1` 放行）。L0。

## [0.4.42] - 2026-11-10

- 字形库推库防缩水（PATCH，A31 11-10，史記事故 GUJI-750：`db push` 连带导出本机旧 glyph.db，中心库字形库 6,465→3,554）：①`guji db push` 缺省不再导出 glyph.db、不推字形库账本，要推显式 `--with-glyph`（或 `GUJI_DB_WITH_GLYPH=1`；`store commit`、`db sync` 不变）；②导出缩水闸 0.5→0.95（任一账本缩水超 5% 且少 ≥3 行即还原并停）；③入库删除闸 `emptied_ledger` 门槛一半→5%，并把 glyph_instances／glyph_sources 也纳入。L0。
- review-pages 字体顺序调整（PATCH，人审页线 11-10，Sheldon 要求）：char_card 1.6.2／char_grid 1.3.1：内嵌的全字库子集（Jigmo、I.Ming，非大陆标准字形）排到系统原字体（Noto Serif SC／Songti SC／SimSun）之后，只给系统字体没有的冷僻字兜底。L0。
- review-pages 难认字卡列图瘦身（PATCH，Sheldon 11-12）：`hard-items`／`column_images` 的列图只取本格及上下各 1 格（`--span`，0 取整列），邻列同一高度段；文字上下文缺省前后各 10 字（`--ctx-n`，原 8）。char_card 1.6.4 去掉列图固定 360px 高。L0。
- review-pages 窄屏版式（PATCH，人审页线 11-10，总览要求）：char_card 1.6.3：屏宽 ≤700px 时难认字／形近字卡的候选按钮、前后文、操作按钮排在上面，整列图缩小放到最下面、点一下放大；宽屏不变。L0。

## [0.4.41] - 2026-11-10

- `cellvotes` 三处陷阱（PATCH，A31 11-10，ai-team 审视 §四-1~3）：`draft --from-kv` 按格号读到 0 票自动改读条目票，仍为 0 则报错退出；`--pack` 出单版包缺页时核格位退回主产物；`write` 缺 `--batch`/`--reviewer` 报缺哪项并以退出码 2 退出。L0。
- `swap run` 加 `--ack-unlanded-votes <原因>`，透传 auto_cycle（cv 同步加参数）→ proof_cycle apply（PATCH，审视陷阱 4，ZM 转）。L0。

- 统一「同一个字」判法（PATCH，A31 11-10，ai-team 字的等价与归一审视）：新增 `guji_manager/charnorm.py`（`CharNorm.same/canon`、`load_norm(book)` 读书级 codepoints，读不到按字面比）；`swap/resolve.resolve`、`booktext.merge_chars／protected_cells／ledger_check`、`overlay_edits.overlay`、`apply_pending(current=)`、`web_votes.triage／same_verdict`、`cellvotes draft` 都接受 `same=` 并在 `swap book-text`／`cellvotes draft` 里传入，别／別 这类归一后同字不再算冲突、机器改字、推翻旧裁。不传 `same` 行为与旧版一致。测试 `tests/test_charnorm.py`。L0。

## [0.4.40] - 2026-11-10

- `swap book-text` 修隐患（PATCH，A31 11-10，专家审 v0.4.39）：校验器不认 lineage/ 时退回不带表落文本，原先 `rmtree(lineage)` 会把同版本目录早先已提交的对照表一并删掉；改成只删刚放进去的那张（`drop_stored_table`）。L0。

## [0.4.39] - 2026-11-10

- 新增 `guji swap finish-merged`（R8，PATCH，A31 11-10，ZM 答复）：`swap book-text` 把对照表存进 book-text `lineage/revisions/<册>-<run>.tsv`；合并后收尾出旧格号 redirect 表、对照表里改号格上的无锚人裁 recheck 清单、metrics.jsonl。L0。

- `guji swap book-text`：cord 经 cv `republish.copy_cord_for_site` 换到网站页图坐标再落（与 swap run 自动路径同口径，换过图源的书不再拷原坐标）；R1 闸用换好的 cord 比（PATCH，ZM 11-10）。L0。

## [0.4.38] - 2026-11-10

- `guji swap book-text` R1 前置闸与 R7（PATCH，A31 11-10，coordinator 转 ZM）：`--glyph-db` 给字形库就核「刻例格键须都在新包里」，不在则停 `r1-stop`（改号待核数只报不停）；1.x 推 `swap/<册>-1x` 后自动开草稿 PR（`gh`，`--no-pr` 关）。L0。

- `guji swap book-text` 守卫补齐（PATCH，ZM 11-10；#478、#479）：①人裁账平——有效人裁与 `char-edits` 手改经对照表换到新格、按人裁最高判字，旧格被删或新包与人裁冲突就停（原先就不同的多为异体／归一，只报），1.x 册取不到人裁事件也停；②专名守卫加 `decomposition`／`targets`／`level`／`coarse`／`note`、条数、「被切短」（少的字数超过锚区间里被删格数就拒写，A33 建议）。人裁改走 `_cv` 门面。L0。

## [0.4.37] - 2026-11-10

- `guji swap book-text`（PATCH，ZM 11-10，sheldon 同意；#472）：格号变动（增删格、改号）落 book-text 只走一条路——新旧 cord 框 IoU 出旧格→新格对照表，判字、挪标点专名、守卫都认它；swap run 不再报 need-A33。配套 cv republish（cv#1381）。L0。

- char_card 1.6.0（MINOR，人审页线 11-10，用户 Sheldon 要求）：①**只有难认字页**的格带**整列图**（低把握页不带，Sheldon 11-10 定，照原样一格一卡）（本格红框）、**左右邻列图**（折叠）、**同列 ±8 格上下文**（机器字＋整理本字），items 可带 `col_img`／`nb_imgs`／`ctx`，由新命令 `review-pages hard-items`（`crop.column_images`）从 cell_shrink＋页图＋包 seed_admit／align_ref 生成；②每格加「不入库」勾选框（定字照记人裁，格文档带 `no_glyph_lib: true`，`expand` 输出同字段，事件 payload 照写 `no_glyph_lib`，route／glyphdb_admit 已认）；旧本机暂存键（1.4/1.5）兜底。L0。

- 冷启动高/低把握两张页固化（MINOR，人审页线 11-10，用户要求）：`review_pages/cold_start.py` 与 `review-pages cold-items`／`cold-pages`：按 5b 领先量、cov、库例数把「库缺样本」格分高把握（带「本页其余都对」）与低把握（一格一卡、没点不算对），一条命令出页；char_card 模板不变（1.5.4）。流程见 `doc/01-粗校/开书/冷启动快审入库.md`「高把握／低把握」一节（PR #412）。L0。

- 新增 `guji closeout lib-disagree <产物包目录>`（MINOR 以下按 PATCH 记，ZM 11-10，缺省不跑）：出单前复核，列出「放行字＝整理本字、库首位是另一个字且 cov≥0.97、非人裁、不在已声明字组／异体里」的格，写成 `--recheck` 清单交 `republish.py`。不改 cv、不改产物。L0。

## [0.4.36] - 2026-11-10

- `guji pending --kv`：改条目、导出、`db sync` 后把整张单直接写网站 KV（`/api/pending`，读者约 15 秒内可见；撤下一格、加一格不再等 proofing-sync 发 COS 和清 CDN）；单里图不在 COS、没令牌或写失败时自动退回 `--sync`。需网站 kaiyuanguji-web `/api/pending` 上线（PATCH，A31 11-10，sheldon 定）。L0。

- `cellvotes draft`：网站新人裁直接覆盖旧人裁（不再挂起要求回网站复审；没给字的票不盖旧裁的字）；「无字」票缺省就写（`--no-none` 才挂起）（PATCH，ZM-殿本二册 11-10，sheldon 定）。

## [0.4.35] - 2026-11-10

- 发版（PATCH，A31 11-10）：从 dev 切，含待审条目化 #454、#455、#456（sheldon 11-10 定）与 A34 的 resolve 认「不是字」、A23 的撤库重审事件。配 cv ≥ v0.6.37。

- 待审条目（一格一条，PATCH，A31 11-10，sheldon 定）：`review/pending_items.py` 条目日志 `feedback/lists/pending/<书>/<章>.items.jsonl`（只追加，`guji db sync` 按追加合并）；`guji pending ls/show/withdraw/restore/note/set/add/resolve/import/reconcile/export`；reconcile 先按图块指纹、再按格号认，只动有变化的，人工撤下的不放回，格号对上指纹变了记 `fp_changed`；整张 pending.json 从条目导出（每格带 `id`／`ver`，条目自带的字块图并进 `sprites[]`）；`cellvotes draft --items` 落网站按条目记的票（换成条目现在的格号），write 后条目标已裁。L0。

- `swap/resolve` 认「不是字」：`resolve(new_not_char=True)`（cv#1358 列端框线格 `frame_line`）无人裁→`NOT_CHAR` 删格放行、有人裁→`PROTECTED_CONFLICT`；`detect_flaws(not_char=…)` 不把它们算字丢失。swap release 待建清单记下接线（PATCH，A34 11-10，A31 请）。L1。

- 库内刻例审阅卡撤库要求重审（PATCH，A23 11-09，Sheldon 定）：`review-pages pair-events lib_audit` 出的 evict 事件带 `review: true`、`char_self`，cv seed_admit `evict_review` 闸据此把这一格文本撤下、退回人审；待审原因 doubt `evict_review` 归 seg_defect、细分 evict_review。L0。

## [0.4.34] - 2026-11-10

- 发版（PATCH，A34 11-10，A31 请）：从 dev 切，含 #445；`doc/04-反馈迭代/全流程与覆盖优先级.md` 一·二与 5.3 并入 11-10 新规矩（待审且首选字≠现行字时文本不动，等人裁；撤库重审格同样保持现字）。

- 待审格现行有字则文本不动（PATCH，A31 11-10，sheldon 定）：`apply_pending` 加可选 `current`，单上格（review≠human）现行已是字、导出字不同时写回现行字（计 `held_current`），现行是 □ 才写首选字；`swap/resolve` 待审且首选字≠现行字新增 `PENDING_KEEP`（原按机器改字放行）。L1。

## [0.4.33] - 2026-11-10

- PATCH（A31 11-10，用户定删 book-text 各书 CHANGES.md）`opinions revise／auto prepare／revert` 把 bump_original 打印的「版本记录」行写进提交信息，`auto finish_pr` 不再补 #TBD；`opinions versions` 改从本地 book-text 的 git log 读版本记录并和已存的 text_versions 合并（旧 CHANGES.md 还在时照读）；`tools/开书/出v01.py` 改打印版本记录行。需 book-text 同名 PR 一起上线，必须先于它发版。

## [0.4.32] - 2026-11-10

- 发版（PATCH，A34 11-10，ZM 请）：从 dev 切，含 #436。

- 修：收尾锚点检查（`closeout/anchors.py` 的 `CELL_RE`）丢了双栏格的 a／b 后缀，`88:6:15b` 写成 `88:6:15` 上单，网站找不到格、无图、按邻格推框错位（殿本 vol01 001-r13 有 7 格）。

## [0.4.31] - 2026-11-09

- 发版（PATCH，A34 11-09）：从 dev 切，含 book-text 只录首选字的导出改动（#429）、A31 的 exit-check E3（#432）。

- `exit-check` E3（decision.json 存在）改为恒「不适用」（PATCH，A31 11-09，book-text 只录首选字，不再录 decision.json）。L0。

- `formats/guji_char_cord.apply_pending` 改口径（PATCH，A34 11-09，sheldon 定 book-text 只录首选字）：不再给 char 写 `pending_reason`（已有的一律去掉）；待审单上现字是 □ 的格写首选字（新增 `first_choice`：stale → 参校本 → lib_top → alt → ctx），去 lacuna；`$schema` 按实际写法取最低版（新增 `char_schema_for`，不再写 v0.4）。cv `export_guji_format --pending`、`republish.py` 入库调用不用改参数，打印的「待审原因 N 格」现在是写首选字的格数。L1。
- `swap/resolve` 加待审口径（PATCH，A34 11-09，sheldon 定）：待审格 book-text 显示首选字，首选字与现行一致则文本不动、只多一张待审单；□ 只给真阙文。
- 新增 `guji_manager/swap/resolve.py`（PATCH，A34 11-09）：重切发布批的覆盖优先级纯函数（人裁 > 机器新结果 > 现行机器字；无人裁机器改字默认放行，退回 □ 进复审单）与机器错字检测。尚未接命令。L0。
- `guji code check` 不查书仓 `code/tests/` 的 import（PATCH，A20 11-09）：本书测试要借 cv 仓 `tests/helpers`，不进指纹。L0。

## [0.4.30] - 2026-11-09

- 发版（PATCH，A31 11-09）：从 dev 切，含 GUJI-764 修复（#416）。

- `glyphdb_admit` 人裁同字升级（PATCH，A31 11-09，GUJI-764，QTW 报）：库里同一格已有同字 auto（provenance 非 human）刻例时，人裁 confirm 原先被主键幂等闸挡掉、记 skipped、库里仍是 auto；现在同字也撤旧再进（计 updated），并删掉这次撤旧留的 `evictions` 行（升级不是撤库）。字不同、已是 human 的路径不变。L0。

- 跟 cv 缺省实现改名（PATCH，A20 11-09，cv#1327 起 `books/siku_zongmu` → `impl/keben`）：控制台门面、`_cv` 兜底表改写新名，取不到时退回旧名（新旧 cv 都能用）；搬来的测试经 `tests/from_cv/cv_paths.keben()` 取模块。L0。
- `guji code`（PATCH，A20 11-09，cv v0.7.0 书级代码）：`status／release／verify／check` 管书仓 `code/`（出 `releases/k<N>.json`、比工作副本、查 import 越界）；产物包标签在钉了模型、有书级代码时接 `-m<N>`、`-k<N>`（没钉写 `-k-<摘要>`），manifest `versions` 记 `model`、`code`、`code_digest`、`code_commit`；都没有的册标签不变。需 cv 含 `core.book_code`（cv#1326）。L0。

- 字形库导出缩水闸（PATCH，ZM 11-09，用户要求）：`datastore/workcopy.py::_export_if_changed` 导出 glyph.db 前备份数据目录里的字形账本，导出后任一账本行数归零或不足原来一半就还原并停下（`db sync`／`push` 都经过它）；防止 `db pull --no-rebuild` 之后本机是空库、sync 把中心库字形表清掉。确要缩小设 `GUJI_ALLOW_GLYPH_SHRINK=1`。不动产物、指纹（L0）。

- `guji opinions ingest --channels charfix,span`（PATCH，A34 11-09）：只入指定渠道，其余（如精校票 cellreview，走 cellvotes）留在来源里不动。原先入池命令不分渠道，夜间修订流程一入池就把 300 多条精校票带进来。缺省仍全入。不动产物、指纹（L0）。

## [0.4.29] - 2026-11-09

- 发版（PATCH，A32 11-09）：从 dev 切，含 #407。
- 出卡把「排除名单上没人看过」的格放回待审（PATCH，A32 11-09，A31 要求，#407）：`review/cards.py` 的出卡闸原先挡掉全部排除名单格；现在 reason 不是 `human:*`、也没有人给的字／判残的格（管线 `gate:crop_defect` 等，文本里整格掉字）照常出卡，口径同 `pack_stats.is_pending`。配套 cv `pending_list.py`、`sprite_build.py`（cord 无框的排除格按同列邻格估框并写 `box`／`box_est`）。不动产物、指纹（L0）。

## [0.4.28] - 2026-11-09

- 发版（PATCH，A31 11-09）：从 dev 切，含 #402、#403。
- 包口径人审率对齐线上单（PATCH，A31 11-09，#403）：排除名单上 `human:` 开头的格，以及格上已有人裁事件的格（网站投「切坏」不进排除名单），都不算待审；管线自己排除又没人裁过的格仍算。总目第一册 g21w9 从 19 格降到 5 格（141:1 五格，管线排除、没人看过）。只改看板统计，不动产物、指纹（L0）。
- `closeout.plan.stamp_pending`（PATCH，A32 11-09，方案 8.9）：出单时按新 char＋book-text 里的标点／专名现算 A01／A02 并写进待审单，供 cv `republish.py` 调用；A03 要比对 book-text 里 char 新旧版，出单时算不出，文本推 dev 后用 `guji closeout derive`。不动产物、指纹（L0）。

## [0.4.27] - 2026-11-09

- 发版（PATCH，A31 11-09）：从 dev 切，含 #399。
- 包口径人审率不再把「排除名单上人已定过」的格算待审（PATCH，A31 11-09，用户定，#399）：切坏／裁坏格人已给字（`evidence.human_char`，文本层照出）、人判残／非字／图形的，`pack_stats.is_pending` 判不待审；没人给字的排除格仍算。总目第一册 g20 包 252 → 47 格。只改看板统计，不动产物、指纹（L0）。

## [0.4.26] - 2026-11-08

- 发版（PATCH，A31 11-09）：从 dev 切，含 #393（待审原因 A01–A03）、#395（`guji closeout`，夹注 a／b 格号修补）及下列各条。
- 标 main 后收尾 `guji closeout` 和换单叠改字（MINOR 新增命令，A32 11-09，方案 `ai-team domain/CV/质检/重跑轮次/标main后自动收尾-方案.md` 八节 8.8／8.9）：不另建余项表，对不上的锚点就是待审格，原因 A01 `anchor_miss`／A02 `add_del`／A03 `anchor_drift`（#393，deferred、不算人审率），一格多因主因不变、其余放 `pending_reason_also`、旧新锚放 `pending_reason_detail` 的 `anchor=` 段。新增 `guji_manager/closeout/`：`derive`（按当前 book-text 现算 A01–A03，不写清除事件，重挂后自然消失）、`anchors.stamp`（先清后写，幂等）、`redlines`（人裁丢失>1%、锚点余项>15%、报错／字形库 verify 不过）、`stats`、`writeback`（dev 上机器错位锚点的三条件自动写回，缺省只出计划）、`remap_lib`（调 book-text `remap_anchors.remap_data`）；`swap.py` 改成包 `swap/`（行为不变），新增 `swap/overlay_edits.py`（换单先叠人工改字再核对位，永不原样导出）。不动产物、指纹（L0）。
- `cellvotes draft` 增加票的去向分流（PATCH，A34 11-08，Sheldon 定：所有投票结果写中心库，切分线自己按批次找）：除原有输出外，多出 `route.md`（改文本批／切分类／无字／挂起各几格，切分类按页汇总）和 `structure.tsv`（页、列、格、类、页面显示字、备注，切坏无字、错位、破损、带备注的看不出），交切分线用；不改落票逻辑、不动产物、指纹（L0）。
- 任务库连接数满时退避重试（PATCH，A30 11-08；worker-13 重起报 `too many connections for role jobs_rw` 直接退出）：`jobsdb.connect` 遇到角色连接数满（SQLSTATE 53300）随机退避重试最多 8 次（单次最长约 60 秒，`GUJI_JOBSDB_FULL_RETRIES` 可调），别的连接错误仍短重试 10 次。不动产物、指纹（L0）。
## [0.4.25] - 2026-11-08

- 中心库备份大文件切片上传＋失败重试（PATCH，A31 11-08，Sheldon/协调者定）：`datastore backup` 把整表 gz 一次 PUT 上传，`files` 表压缩后 220 MB 被边缘掐断（`Connection reset`），备份连续失败。现在 `upload` 把超过 64 MB 的文件切成 `<表>.copy.gz.partNNN`，清单该表记 `parts`；单个文件上传失败重试 4 次；`fetch`（含 `restore-check`）按 `parts` 拼回，旧备份（无 `parts`）照读。不动产物、指纹（L0）。

## [0.4.24] - 测试中

- 存包时随包写人审率 `pack_stats`（PATCH，A31 11-08，Sheldon 定：数据随 pipeline 跑完自动更新，网站直接读中心库）：整册存包成功后按 seed_admit 数全册格与待审格，写进 `progress.volume.extra['cv.packs'][<包标签>]`（每册留最近 8 个）；标 main 钩子据此直接收一轮、`progress-sync --fix` 也优先用它；不连库、无 seed_admit、只打几步的包静默跳过，永远不抛。
- 后台看板自动对账 `guji-manager progress-sync`（PATCH，A31 11-08，Sheldon 定：看板必须自动更新到最新，不能靠手动）：对一遍中心库里的事实——线上单 rev ≠ 看板 `pending_rev`（重跑 cv `progress_report`）、`a31.main` ≠ `cv.pack`（取 ★main 包重算写看板）、已标 main 的轮次在「迭代轮次」里还是占位（`auto_round` 汇总）——落后的就补，幂等，可每小时跑；不带 `--fix` 只报告（有落后退出码 1）。同时：标 main 钩子 `push_pack_rate` 缺 ai-team 检出时改为自己浅克隆一份（原来静默跳过，11-08 第 6／7 轮包口径和轮次因此停在「待统计」）；`auto_round` 汇总后把占位的 `verdict=pending`／备注升成 main（原来永远停在待统计）。不动产物、指纹（L0）。
- 执行方成功存包后清本机该册的 `cache/<册>` 和 `products/<册>`（PATCH，A30 11-08，Sheldon 同意）：执行机磁盘被各册缓存和产物副本堆满（殿本工作区 14 GB，cache 7.3 GB、products 4.4 GB），剩余低于 3 GB 就不领单。包已推中心库，这两处可重建；`cache/_judge`、`cache/glyph-derived`、工作区仓、册 yaml、feedback、output 不动，失败单和没存包的单不清。`GUJI_JOBS_KEEP_ARTIFACTS=1` 关闭。不动产物、指纹（L0）。
- `_cv._FALLBACK` 补登记参校本属性三个名字 `RefProfile`、`load_reference_profile`、`ref_profile_lint`（PATCH，cv #1273 manager_api 新导出，test_cv_surface 红；A22 11-08）。
- 「整理本读不到」的页也算本就没参照（PATCH，QTW 11-08：全唐文 002 册里没写 references，208 页备注全是它）：并入 `ref_by_design`，同 #351 不判 S01／S02／R02。
- 本页本就没配参校本不判整页／整列对不上（PATCH，QTW 经 A31 11-08 报；用户 11-06/07 定待审原因改分类直接改）：全唐文 001–003 故意不带参校本，首跑约 1.9 万格被记成 S01。对位层 note 是「未配置整理本／未配置证人」的页，`Cell.ref_by_design`＝真，不判 S01／S02／R02，落 L04 `lib_unrecognized`（细分 `no_ref`，带 `lib_miss` 码的仍 `lib_diff`）。只改分类，不动产物、指纹。
- 新页型 `seg_cut` 1.0.0 人裁切线（PATCH，缺省不影响旧页；SJ 需求）：一格一段列图叠两套格网，点图画切线或标不切/看不出，结果带列图与页图坐标；CLI `build seg_cut`、`segcut-apply`。
- 带框重的字块不进字形库（PATCH，Sheldon 11-08 定；只在 `SELFCHECK_BOOKS` 开了 frame 的书，即殿本）：`glyphdb_admit` 人裁进库前按库里同字刻例比「端区比字身宽多少」（`seg_defect.lib_frame_heavy`），带框重的计入 `no_lib`／`frame_heavy`，格键与特征记进 `frame_heavy_keys` 反馈切分；库里同字不到 5 个照收。
## [0.4.22] - 2026-11-07

- `guji corpus pin` 崩溃（PATCH，A31 11-07 报）：`cmd_corpus` 读 `args.shift_book_ver`，parser 只有 `--book-ver`，一跑就 AttributeError；`guji recheck` 同病（读 `args.shift_book`，应为位置参数 `book`）。都是 #145 给 rekey-cells 加 `--shift-book` 时整词替换带坏的。改回后新增守卫 `tests/test_cli_args_guard.py`：每条子命令处理函数读的 `args.X` 都要是真 parser 定义过的参数。不动产物、指纹（L0）。

## [0.4.21] - 2026-11-07

- 第 7 轮冻结版（PATCH）：含 #297 S04 碎片格、#302 标 main 钩子找 guji、#304 #310 Z 类重分、#316 R01 图片格提示、#319 #321 字库类重分与私用码落 R01 等，均只改分类/工具，不改放行。

- 待审原因 Z 类「同字异形」折叠收窄（PATCH，A24 Z03 深挖；Sheldon 11-06 定改分类可直接做，合后经收件箱告知 A31）：折叠解法给字改用新增的 `Context.same_writing`（cv 暂归一表 `PROVISIONAL.forms` 并集＋宫宮），不再用宽异体表 `are_variants`（大／太、傳／傅、玉／王、戊／戌 都有边）；这些文意与字形路各执一字的格由 Z03 改落 Z02（三书 ★main 现算 Z03 247→236，Z02 +11，全唐文 Z03 11→2）。没给 `same_writing` 时退回 `are_variants`。只改分类、不放行。
- 待审原因 Z 类按「解法给出了什么」重分（MINOR，A24 Z 类梳理；Sheldon 11-07 同意，已经协调者通知 A31–A34）：新增 Z07 `group_unconfirmed`「形近字·差一路确认」（一个字、why=weak 或联合判共字组没表态，原落 Z01／Z02）；Z06 `group_form_open` 改名 `variant_form_open`、码 V02、归异体类（yaml renamed，旧名照读）；ref／coord_dissent 而参校字是〓的落 R01；复核 `group_flow_ref_dissent` 归 Z04、复核两字归 Z02、复核没字归 Z01；字组已定字（含解法全弃权的 keep）不归 Z；Z 类 detail 改写「组:lift|joint|review」。只改分类、不放行。网站、控制台 pendingReasons 副本要按 `--json` 同步。

## [0.4.20] - 2026-11-06

- 待审原因 Z02 `group_conflict` 分类（PATCH，A24；Sheldon 11-07 授权先改后通知）：`reasons._group_kind` 解法只差写法（`are_variants` 判同字异形：象／𧰼、寇／㓂、會／㑹）不再算 Z02，落 Z03（降审）或 Z01（Z05 已停用）；只改分类、不放行；没给 `are_variants` 时行为不变。
## [0.4.19] - 2026-11-06

- 待审原因 Z05 `group_weak` 停用（PATCH，A24 #285；Sheldon 11-06 定）：字组已定字（admit/keep/provisional）仍待审的格不归字组、按后面的原因落（L05、L04…）；why=ref_missing／solo_weak 落 R 类；其余并入 Z01。枚举与 yaml 保留，旧数据读得出，不再产出。只改分类，不放行。另含 Z06、R03 深挖文档（#292）。

## [0.4.18] - 2026-11-06

- 待审原因 L01–L03 边界（PATCH，A23 #287；Sheldon 11-06 同意）：刻例只算本书版本（`lib_own_counts`）；参校字本书库 0 例一律归 L01，1～2 例按机器字是否＝参校字分 L03／L02；leverage 里 L03 也按参校字并卡。P02 说明改写（#284）。只改归类，不放行。

- 待审原因 L05 `garble_gate` 要有整理本字（A24，Sheldon 11-06 同意）：`reasons.py` 无对位的糊格（框线碎片、并格、圈点）不再判 L05，落 R02 `ref_gap`；殿本约 −29、史記 −13、全唐文 0（★main 现算）。只改原因，不改放行。

- 待审原因 L05 `garble_gate` 深挖（PATCH，A24；Sheldon 11-06）：新增 `tools/l05_profile.py`（体检＋按 `rare_ref_coord_min_cov`／`rare_ref_coord_group_top` 离线回放，分 A1／A2／A3／B／C 五类）；`doc/01-粗校/待审原因/garble_gate/` 重写 README（判定条件、现状、五类配图）、流程与参数、benchmark。不改原因码、不改分类逻辑；对应 cv #1204（seed_admit 1.45，缺省关）。

## [0.4.17] - 2026-11-06

- 待审原因 L04 `lib_unrecognized` 理流程（PATCH，A23；Sheldon 11-06「理清整个流程、定 benchmark、下一本书能快速做」）：`pending_reason_detail` 改写成 `<细分>:<参校字>`，细分按 `ref_lib_coord` 逐关看哪一关没过（`lib_other`／`human_unbound`／`doubt_blocked`／`low_cov`／`near_rival`／`clear`，`reasons.lib_unrecognized_kind`）；yaml detect 文案改成与代码一致（兜底，不看刻例数与库认不认）；`pending-stats` 的 cells.tsv 末尾加 `detail` 列；新增 `review/vis_review.py`（看图裁定导出对照图与窗口、答案写成 vis-o1 裁定）。只改分类细节与统计，不放行、不改原因取值。说明见 `doc/01-粗校/待审原因/lib_unrecognized/`。

## [0.4.16] - 2026-11-06

- 待审原因 V01 `variant_pair` 收窄（PATCH，A31；A24 V01 深挖 11-06，#261）：只看整理本字与库首位或机器字的异体边，不再看前五里其它候选；边分型（cv `variants.edge_tier`）只认 T1／T2，T3（通假、形近、简繁）不算。只改分类，不放行；V01 预计 388→约 172，其余落 P01／P02／N01／L04。
- 人审页 `char_card` 1.5.4（PATCH 修 bug，A24；Sheldon 11-06 报「后台存档失败」）：逐格文档 id `c_<格号>` 里的 `#`、`:`、`+` 被后台库拒收（只认 ASCII 字母数字和 `_`），格号带 `#`（私用码页 `daizhige:U+EAC0#20-31-148`）时每一格都存档失败、只落在浏览器本地。改成 `c_`＋`safeId(格号)`；读回按文档里的 `id` 字段，不依赖文档名；已在本地点的结果加载后自动补存。普通格号（`vol01:5:2:10`）的文档名跟着变，老文档读回时不受影响（读的是 `id` 字段），但会补存一份新名的。

- review-pages 新页型 `ref_check`（整理本真错复核，A32 11-06，A31 定）：`ref-check-items`（待审格 → 带邻格条与裁图的 items，按 `ref_suspect` 排序 ref 最前）、`ref-check-apply`（结果 → 改字 tsv）；cell_pick 模板核对模式加「改作 库首位」按钮（`cell_pick` 1.2.0）。只读，不放行。
- 待审单加只读标记 `ref_suspect`（PATCH，A31；A32 D01 深挖 11-06 提）：出单时在本册整理本里比库首位字与整理本字放进这一格上下文（前一字＋X、X＋后一字）的相邻二字次数（整理本这一格自己不算），库首位明显更通顺写 `ref`（疑整理本错，人审页置顶），整理本更通顺写 `lib`（疑库错），分不出不写；出单统计记 `ref_suspect_ref`／`ref_suspect_lib`。只排序用，不放行、不改字、不改原因。

- 待审原因 N01 `near_form_guard` 收窄（PATCH，A31；A24 N01 深挖 11-06）：只留库护栏 conflict／never_match，或参校字与机器字／库候选前三构成 cv 手工形近表 `NEVER_MATCH_FAMILIES` 里一对的格；仅疑问码 near_form（家族字碰巧在候选前三）的格改落 lib_sparse_dissent／ref_ocr_diff／ref_final_diff 等后续原因。只改分类，不放行；殿本 N01 预计约 273→24，L02、P01、P02 相应增加。

- `guji swap run` 开跑前和每批之间核数据目录有待收字登记表 `config/pua/glyph_pending_codes.json` 和语料 `corpus/daizhige/`（PATCH，A32，A31 11-06 要求）：缺了 R03 待收字会被统计成 R01、出单报告 `glyph_pending_registry_missing`＝1，缺就停下提示 `guji db pull`。

- 新增 `guji swap run`／`guji swap audit`：换单 driver（MINOR，A32，用户 11-05「讲一下换单…做得自动」）。每批 N 册（缺省 6）：`auto_cycle --no-publish` → `sync_workspace(no_glyph)` → 对这批 `proofing-sync only=` 发布并等跑完 → 逐册取线上 `NNN.pending.json` 核版本 → 核过的清掉本地产物包；开跑前、每批之间核字形库账本不空且不比基准少一成、磁盘 ≥3GB；全程 `GUJI_DB_NO_GLYPH=1`；状态写 `<工作区>/reports/_swap/state.json`，同一条命令断点续跑；need-A33／blocked 的册只记入状态并最后列出。
- 换单报告固定附「机器改字抽检表」（`machine_audit.py`，A32，A31 11-06 要求）：换单时机器无票改字（新字≠book-text 现文）按新字≠整理本字分 A（己已巳、日曰折叠组）／B（形近误读）／C（其它不同字，多为异体表漏）／D（整理本无字）四档，新字＝整理本与异体只计数；人裁定的格不算。每册在发布前（产物包清掉前）出数据，全批跑完写 `reports/_swap/机器改字抽检表-<时间>.md` 与同名 tsv；单独出用 `guji swap audit --books … -w … --book-text …`。

- 待审原因 P01、P02 改英文名（PATCH，QTW；Sheldon 11-06 嫌旧名看不出区别）：P01 `ref_replaced`→`ref_ocr_diff`（识别字与参校本不同：Step6 对位时识别字就≠参校字），P02 `ref_mismatch`→`ref_final_diff`（定字与参校本不同：对位相同、最后定字≠参校字），中文名、hint、说明文件夹跟着改。码不变；yaml 新增 `renamed`，`parse()` 和 `--json` 导出带旧名映射，旧单、旧事件照认。网站／控制台 `pendingReasons.ts` 副本要重新导出同步。

- 人审页 `char_card` 1.5.3（PATCH，A24；Sheldon 11-06 反馈）：样本没有本书切图（`img` 为空）时不再渲染空图，改显灰框「本书无切图（没对上 v2）」，其余（维基图、上下文、输入框）照常；存档键只看前两段，已点的不丢。

- 人审页 `char_card` 1.5.2（PATCH，A24；Sheldon 11-06）：难认字页每格「这格是什么字」和「认不出：部件／IDS」两个输入框常显，认不出的字可直接输入；输入即存，规则同前（填字＝改字，填部件＝认不出＋部件）。

- 人审页 `char_card` 1.5.1（PATCH 外观，A24；Sheldon 11-06 反馈）：①`--font`／`--font-dir`（cv 的 fonts/）把本页用到的字按 I.Ming→Jigmo 三档子集化成 woff2 内嵌，排在 `--font-glyph` 最前，不依赖外网；字体都没有的字页上改显码位（U+XXXXX），不留空白；没装 fonttools 时不嵌字体。②难认字页（`--no-rest-ok`）卡片改网格排（列宽 ≥250px，宽屏 5 列），卡头压成一行，上下文／说明字号再小一档，`per_page` 缺省 24（原 8）；存档键只看 tpl_version 前两段，已点的不丢。

- 新命令 `guji cellvotes rebase`（PATCH，A20）：页号格号不变的换图源（殿本四庫總目换文淵閣本）后，人裁事件锚里的框按页表 `from_rev.H` 换到新页、`source_rev` 改新 rev，出 `~r` 事件、待办清单和报告（只读，不写库）；旧页图 sha 与新页表 `from_rev.sha256` 对不上的不迁。逻辑 `feedback/source_rebase.py`，说明见 `doc/案例/殿本四库总目.md`。
- 人审页 `char_card` 1.5.0（MINOR 外观，A24，私用码映射第一步）：items 可带 `ref_img`（标准字形图，如维基 SKQS 僻字图）和 `ref_label`，格上与本书切图并排显示、各带小字；不带的格不变。

## [0.4.15] - 2026-11-05

- 人审页 `closeout` 1.2.0（MINOR 外观，QTW 替 A31 做；Sheldon 11-06 定收口口径）：去向只留三个——放行／留人审／算法再处理，缺省预选「算法再处理」；还有任何一格是「算法再处理」时页顶提示不能出 v0.1；选项说明、registry options 同步改；旧选项名（人审底／留后／精校待办／再处理）不再出现。同步改 S3、S4、人审页模板文档与 round_report 收口归宿文字。

## [0.4.14] - 2026-11-05

- 人审页 `closeout` 1.1.0（PATCH，QTW 替 A31 做；Sheldon 看收口单说「看不到图、不知道怎么选」）：`examples` 元素可带字块图 `{id, img, note?}`（按 cell_shrink 字框裁，用共用 glyphBox，下方标格号）；每个去向下面加白话说明（人审底／留后／精校待办／再处理，`opt_help` 可覆盖）。老格式（examples 为格号字串）不变。

## [0.4.13] - 2026-11-05

- 出单自检带框一侧提查全、分轻重（PATCH，A22；Sheldon 11-05 定「只接切坏，带框先调」）：`seg_defect.same_char_frame` 加「端区碎线」（端区里和字身分开的细碎截占宽 ≥0.15）；旗表加末列 `程度`（带框格墨宽比同字 ≥ `FRAME_HEAVY_W`=1.20 记「重」，其余「轻」，别的类空），meta 加 `frame_heavy`。殿本尺子带框中 27→48/86、误标 5→11；殿本 10 册看图单 150 块：端区碎线查准 0.58，宽比 ≥1.20 的 0.70，Sheldon 点名严重的 4 格全在「重」档。10 册带框 151→577（重 193）。带框仍只记旗不送审，清框／不进字库以后只管「重」。读旗表用 DictReader 的不受影响。
- 补回 `guji cache build-rare-index` 的命令测试（只动测试，A31）：cv #1053 搬命令时测试留在 cv，装了 torch 就红；搬到 `tests/from_cv/test_cli_build_rare_index.py`，桩改打在 `_cv` 门面上。

## [0.4.12] - 2026-11-05

- 待审原因、成因读产物认史記 `alt_cut` 备选列（PATCH，A22）：seed_admit `alt_cols` 里的列（读不到退回 align_ref 的）格号是备选切法的，`book_cells`／`book_causes` 原先照主切法的 align_ref `chars`／`coord` 按格号挂参校字，整列错位（如 02:106 第 6 列，备选多一个 -1 格，参校字全错一位）。新 `align_for_seed`：这些列丢掉现役对位字、改读 `alt_draft.coord`。史記 01–10 r12 main 包：参校字变 27 格（03:10 第 2 列 9、06:93 第 6 列 7、04:119 第 1 列 6、02:106 第 6 列 3 等），原因变 24 格。殿本没有备选列，不变。不动 Step、不改指纹。
- 终审 `is_ideograph` 补 Unicode 17 Ext J（U+323B0–3347F，殿本 r5 有真 Ext J 字），区段对齐 cv #1135 的 `vis_ruling`；部首区与表意描述符不算汉字（PATCH，A23；A31 要）。

## [0.4.11] - 2026-11-05

- 整页对不上 S01 的「弱证据格」一支要本列大多对不上（PATCH，A22；A31／SJ／A20 11-05 报史記 02:106、03:10 半色调页误归）：有参校字、机器字不同的格，只在本列一致率（本列含已放行格、有参校字的格里机器字＝参校字的比例）<0.5 时才算弱证据，同页这样的格 ≥10 才判 S01。`Cell` 加 `col_agree`，`book_cells` 按产物算；单上补的格没有列一致率，照旧。史記 01–10＋殿本 6 册现行 main 包模拟：S01 384→306 格，变的 78 格在 02:106、03:10、02:50、02:66（列一致率 0.6–1，对位对、只是认不准）和 vol86:152 第 2 列 1 格，改落 ref_replaced 35、lib_missing 21、ref_mismatch 11、garble_gate 7、near_form_guard 4；vol86:152 第 1 列（1/16 一致）仍是 S01。不动 Step、不改指纹；已出的单用 backfill_pending_reason.py。

## [0.4.10] - 2026-11-05

- 终审放行门槛加「选中的字必须是汉字」（PATCH，A23；史記 3 格放行了整理本缺字占位 ခ）：`core.gate_ex` 判 `is_ideograph`：ခ／〓／换行一律 `not_ideograph`；本书造字（私用区码如史記 U+EF6E、○）只在库里已有 >2 个样本（需 `--glyph-db`）且图一致证人成立时才放行，不再因「与参校本同字」放行。

## [0.4.9] - 2026-11-05

- 任务库去重认中心库 rev（PATCH，A31；11-05 史記 #831/#833 撞上，A30 查明）：spec 新字段 `db_rev`（进指纹），`guji job submit` 提交时自动填中心库当前 rev（连不上就不填并提示加 --again）。册 yaml 改了、spec 没变的单不再被判成重复。不给 db_rev 的老任务指纹不变。
- 待收字出单接线（PATCH，A24；承接 #192，A31 同意「窗口回查」方案）：`book_cells` 给整理本缺字格算前后各 20 字的整理本窗口；`reasons_for_pending` 加 `glyph_pending`（登记表，缺省读数据目录 `config/pua/glyph_pending_codes.json`（A31 定，不放语料版本以免动 corpus 指纹；读不到＝空表＝全走 `ref_lacuna`，和改前一样））与 `pua_resolve`（缺省用 cv `utils.pua_lookup.resolve_pua_code` 按窗口回查殆知阁源文件里的原码位 `daizhige:U+XXXX`；旧 cv 没有这个模块或源文件读不到则不回查），回查到的码在登记表里才记 `glyph_pending`，回查不到／没登记仍 `ref_lacuna`。不动 Step、不改指纹；登记表文件由 A31 推中心库。控制台待审卡（`stamp_cards`）暂不接。回查索引按语料目录缓存（同一目录只读一遍源文件）。**眼下只有殆知阁码（`daizhige:U+Exxx`）能经窗口回查落到格上，登记表里 114 个 `siku-qiefen-v2:U+F1xxx` 的图源码暂不起作用**（没有对应的回查途径）。风险：判成 `glyph_pending` 的格不派人审，回查错了会把格悄悄藏起来；`reasons_for_pending(stats=Counter())` 记 `glyph_pending_by_window`（按窗口回查判成待收字的格数），出单报告要单列，第一次上线抽 20 格看图。

## [0.4.8] - 2026-11-05

- 待审原因新增 `glyph_pending`「待收字」R03（PATCH，缺省关的新功能，A24；sheldon 11-05 定、A20 审）：整理本这位是私用码、且码位在私用码表里登记为「已判定待收」（没收进 Unicode、暂找不到合适异体）。登记表缺省空＝都不算，所以不登记就没有任何变化。待收字格**仍上单**（book-text 靠单写 `pending_reason`，网站凭它显示字图）；不派人审、不进大模型，靠下游按 `reviewer: none`、`route: deferred` 跳过，随 web／console 副本同步做（现在只有 iterate／leverage 认 route，出单、pending_route 都不看）。priority 49（先于 ref_lacuna）。`Cell` 加 `pua_code`（单上同名字段、产物 evidence.pua_code 都读），`build_context`／`reasons_for_pending`／`stamp_cards` 加 `glyph_pending` 登记表参数；登记表从哪读、产物里的 pua_code 由 cv fix_pua 那边接。detail 只写永久编号「来源:码位」（`daizhige:U+E123`、`siku-qiefen-v2:U+F1001`，两套码不一一对应，必须带来源）。占位码（以图代字，U+1001 等）属真图，不进待收字。`--json` 导出后 web、console、book-text 三份副本要同步，已出的单用 backfill_pending_reason.py。

## [0.4.7] - 2026-11-05

- 标 main 后先在后台看板「迭代轮次」占上这一轮（PATCH，A31）：包口径统计在标 main 的机器上跑不成（缺 ai-team 检出等）时，也写一条 `verdict=pending`、人审率待统计的记录，不再静默漏轮；统计跑成后 `auto-round` 照旧补全。与 `GUJI_AUTO_ONLINE_LISTS` 无关。
- `pending-stats` 按单上 `src` 单独计数（PATCH，A31）：`summary.json` 加 `by_src`，报告在原因表后列「同字对照自检（seg_selfcheck）N」（格已含在 seg_defect 里），单上没 src 的按 detail 前缀「同字对照自检：」认。待收字改走新取值 glyph_pending（A20 11-05），按原因计数。
## [0.4.6] - 2026-11-05

- 终审 `final-review finalize` 接册 yaml 的 `params.seed_admit.ruling_glyph_min_score/margin` 与 `ruling_ref_lead_min_unseen/oov`（PATCH，A24；A31 要，依赖 cv #1110）：图一致证人改判「首位、分 ≥ t、领先次优异字 ≥ margin」（折叠组 己已巳／日曰内不当竞争者；`cells.json` 新增 `glyph_cands` 前五按名次；没写 yaml 键＝旧口径，命令行 `--min-score`）。ref_lead 证人：选中字＝整理本字、且在 unseen（需 `--glyph-db`，库样本 ≤2）或 oov（需 `--cnn-classes`）层时，整理本字须首位且领先 ≥ 该层阈值，并与图一致证人同时成立才放行，否则 `ref_lead_fail`；不单独放行；逐格结果多「证据」列（`ref_lead:层:领先量`），裁定 payload 带 `via`、`ref_lead`。
- 连中心库（Neon）时带 `application_name=guji/<谁>/<命令>`（PATCH，11-05 查「Neon 一直不休眠」用）：`pg_stat_activity` 里直接看出是哪个执行方／会话在连，不改任何行为。

## [0.4.5] - 2026-11-05

- 借库 `scope: human+auto`（PATCH，缺省关的新选项，A23；全唐文线提议）：人裁加看图确认过的自动刻例。依赖 cv 同名 PR（`BORROW_SCOPES`）。实测见 `doc/01-开新书/借库写法.md`。

## [0.4.4] - 2026-11-05

- 借库新写法 `glyph_lib.borrow: [{from, scope: human, pin: N}]`（PATCH，缺省关的新功能，A23；借库参照方案缺口 1、2）：`scope: human` 只借被借库人裁；`pin` 钉被借库字形库快照 g<N>（`pinned_lender_copy`，一次拼好不再连网），`borrow_fingerprint` 带记号，快照清单记 `borrow_how`。旧写法与缺省借法逐位不变。依赖 cv #1095（`borrowed_store`）。说明见 `doc/01-开新书/借库写法.md`。
- 局部改号表第二版（cv #1081）：认「新sub」列（夹注 a/b 可改）；多个旧格对上同一新格（多对一）表里放行，库里真有两个实例落到同一新 id 才拒（PATCH）。

- 评测注册表守卫登记 cv 新脚本 `eval_font_family`（PATCH，只动测试，A23；cv #1093）。

- 人审页 `char_card` 1.4.0 难认字页（PATCH，QTW，sheldon 11-05 反馈、A31 同意）：`--no-rest-ok` 时一格一卡、不合卡、去掉卡头改字（免得一改改整卡）；格上直接给「页上字对／切分有问题／不是字／看不清／认不出」按钮，认不出可填能看出的部件，存 `unknown:<部件>`，`expand` 出 status=unknown＋parts、notchar；items 可带 `seg_hint`（疑似切分）、`recut`（按新切分重裁）标在格上；页顶显示已标格数。本机暂存键兼容 1.3。

- `review-pages build char_card --no-rest-ok`（PATCH，QTW 提 #158）：难认字页没有「本页其余都对」，没点的格不算对，只存点过、改过的格；char_card 升 1.3.1。

## [0.4.3] - 2026-11-05

- 人审页 `near_pair` 1.0.1、`lib_audit` 1.0.1：字块图改用共用定框放大件 `glyphBox`（PATCH，A23；A22 #163 共用件）。

- 人审页新增两个页型（PATCH，A23，A31 11-05 同意；sheldon 11-05 定按 PATCH 发）：`near_pair` 1.0.0 形近字对比卡（两字各摆库里人裁刻例、待审格居中、A/B/都不是/看不清/切分有问题、可带 near_shape 差异区图）与 `lib_audit` 1.0.0 库内刻例审阅卡（按字头列刻例，改成/撤库/形近没错），都用 `_store.js` 逐项存档；`review-pages pair-events` 把结果转成 `glyph_audit` relabel／evict／near_form 与 `confirm` 事件（缺省只写说明文件，`--apply --batch` 才追加本机事件日志）。`build --exclude` 对这两个页型按组内的格/刻例撤。

- `review/seg_defect` 出单同字对照自检（PATCH，A22 长期计划 B1③，A20／A31 11-05 定方案）：加整册入口 `book_flags()`、CLI `--gate`（只出同字对照命中的 clipped／frame_residue，写 `<工作区>/reports/<册>/seg_selfcheck.tsv`＋`.meta.json`，meta 记参数与各页 seed_admit／cell_shrink 产物指纹，`meta_fresh()` 判过期）；补「偏高／墨宽＝带框」一侧 `same_char_frame`（归 frame_residue）；书级小表 `SELFCHECK_BOOKS`（按 book-text 条目 id，殿本、史記两项，缺省都不开，`review_kinds` 缺省只送 clipped）。`review/reasons.py`：单上 `src="seg_selfcheck"` 的格归 seg_defect，detail 写「同字对照自检：<seg_kind>」。不进任何 Step 的 code_deps。
- 修：`_cv` 里 RulingLog 等六个名字（feedback.rulings）误登记进了 `_LOCAL`（本包模块表），实际在 cv，导致 final-review 报「需要装 open-guji-cv」（PATCH，A31）；`test_cv_surface` 加守卫：`_LOCAL` 的名字必须有对应本包模块。

- 评测注册表守卫（tests/from_cv/test_eval_v2.py）登记 cv 的 `eval_fold`（折叠表辅助模块）与 `eval_ref_verify`（5b 验证整理本字，A23），修 dev CI 自 #157 起因这两个脚本没登记而红（PATCH，只动测试）。
- 人审页：字组抽样与私用码字形图（MINOR，A24，sheldon 11-05）：`pair_whitelist` 1.2.0——新增 `pair.py` 与命令 `pair-items`（每组按格号哈希稳定抽 30 格，带前后文、整理本字标【】）、`pair-apply`（结果→每组同字率＋可入白名单的组，门槛默认 30 格全同字）；模板逐格点同字/不同字/看不清、每组页尾显示同字率，结果文档加 marks/same/diff/unclear/judged/rate。`codepoint` 2.2.0——字体缺字（私用码）时候选可带字形图（组 `glyphs` 或 `rows[字].img`），标题、行首、「统一作 X」按钮都显示图；`cp-items` 认 groups.json 的 `glyphs`。

- 人审页补齐必备功能（PATCH，A31，sheldon 11-05；原记 MINOR，sheldon 定按 PATCH 发）：逐项存档通用件 `_store.js`（点一下就存、读回、how=click/page_ok、未确认项标出），`gold_sample` 1.1.0（切分错/看不清/库里无此字、整理本字入上下文、邻格条、按 kind 筛选、核对模式）、`codepoint` 2.1.0、`pair_whitelist` 1.1.0、`seg_cause` 1.1.0、`char_grid` 1.2.0 改点即存；新增 `closeout` 1.0.0 收口单；`expand` 带 kind；新增 `unconfirmed`、`closeout-sum`，`cp-apply --items`；下游（cp-apply、ledger、char pull）只认已确认。
- 人审页模板库新页型 `glyph_quality` 1.0.0（PATCH，新增页型与命令，A22，A31 11-05 转）：字块质量看图，单块或同格新旧两版同倍放大并排，点干净/带框/切笔/看不清，存档用 `_store.js`（项 id＝格号|sha，点即存、读回、how=click/page_ok）；`build glyph_quality` 直接吃 dataset 金标信封（`--root`、`--all-crops`、`--box`），新命令 `gq-apply` 出标签 jsonl 或回写信封；`--exclude` 认带 sha 的行（按块撤）。`_common` 加共用放大组件 `glyphBox`/`glyphPair`（固定框放大、多块同倍并排）。

- 后台「迭代轮次」（PATCH，A31，sheldon 11-05）：`iterate push-rounds`（回填）、`round-report --push-progress`（验收后写一轮）、`iterate auto-round`（从各册★main 包口径汇总一轮）；标 main 的钩子在包口径写完后自动接 `auto-round`，每标一册更新一次该轮（包标签无 `-rN` 段的不自动收）。人审页 `char_card` 1.3.0：每格多路候选＋来源；`_common.js` saveDoc 把文档 id 编成 ASCII。

- `guji db push`／`guji db sync` 加 `--no-glyph`（或环境变量 `GUJI_DB_NO_GLYPH=1`）（PATCH，A32，用户 11-05 同意）：这次不碰字形库——不导出 glyph.db、`output/glyph_store/` 下的文件不推、基准里的记录原样留、sync 也不落库。换单、批量发布这类只改待审单的流程用它，字形库账本就绝不会被它写到（11-04 字形账本被清空事故的根治，配合导入侧「账本被清空」拒推）。`workcopy.push`／`sync` 新增 `skip_prefixes`。

- `guji rekey-cells glyph-db` 认 A22 局部改号表（`册 页 列 旧格 sub 新格`，只列动了的格；加 `--shift-book <册>`，可选 `--rekey-note`）：表里没列的格不动，`?` 的停放，改键批次名与换图源那次分开判幂等。用于殿本抬头漏认（cv #1076）改格号（PATCH，新增可选项，旧用法不变）。

## [0.4.2] - 2026-11-05

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
