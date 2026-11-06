# Changelog

版本号规矩见 `doc/版本号规矩.md`（2026-11-03 起，同 open-guji-cv）。本文件记录**全部**版本（含 PATCH）；动代码的 PR 投 `dev`，在 `## [未发版]` 下加一行、写明档位；切 rc 时改成 `## [X.Y.Z] - 测试中`，发版时改成日期。

## [未发版]

- 待审原因 P01、P02 改英文名（PATCH，QTW；Sheldon 11-06 嫌旧名看不出区别）：P01 `ref_replaced`→`ref_ocr_diff`（识别字与参校本不同：Step6 对位时识别字就≠参校字），P02 `ref_mismatch`→`ref_final_diff`（定字与参校本不同：对位相同、最后定字≠参校字），中文名、hint、说明文件夹跟着改。码不变；yaml 新增 `renamed`，`parse()` 和 `--json` 导出带旧名映射，旧单、旧事件照认。网站／控制台 `pendingReasons.ts` 副本要重新导出同步。

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
