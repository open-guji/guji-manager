# Changelog

版本号规矩见 `doc/版本号规矩.md`（2026-11-03 起，同 open-guji-cv）。本文件记录**全部**版本（含 PATCH）；动代码的 PR 投 `dev`，在 `## [未发版]` 下加一行、写明档位；切 rc 时改成 `## [X.Y.Z] - 测试中`，发版时改成日期。

## [未发版]

## [0.4.44] - 2026-11-12

- 任务单 `run` 收 `seg check`／`seg ruler`（不收 `seg pin`，它写数据目录钉子）；`seg check --job` 把逐列清单排前、计数与结论压最后、退出码恒 0，因任务库只留每条输出末 6000 字（PATCH，QTW 11-12，#535）。
- 审阅页 glyph_quality 1.1.0：加「污渍」一档（数字键 4，看不清改 5），gq-apply 认 stain（A22 11-12，Sheldon 要建污渍尺子）。
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
