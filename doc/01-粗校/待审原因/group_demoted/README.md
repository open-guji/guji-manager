# Z03 `group_demoted`：形近字·复核推翻（字符级深挖，A24，2026-11-06 初稿，2026-11-07 按新码重算）

> [待审原因总览](../README.md)

派单见 ai-team `待审原因深挖/派单-2026-11-06.md`（第 3 批）。格式按 sheldon 11-06 定：先说什么情况判成这个原因、现状，配图看哪些格会归进来，再谈怎么提高；并把整条流程、参数、benchmark 写清，方便下一本书直接用。底稿、逐格表、脚本在 ai-team `domain/CV/质检/待审原因深挖/`（`Z03-复核推翻.md`、`Z03-逐格-三书247格.tsv`、`Z03-bench-seed.tsv`、`Z03-scripts/`）。**本文只给结论，没改代码**；要改的见第七节（改原因码分类先经协调者通知 A31–A34）。

> **11-07 更新**：manager#304 把 Z 类按「解法给出什么」重分（Z03 现在＝复核、解法只给一个字、与放行字不同，见 [Z类梳理](../Z类梳理.md)），cv dev 也合了新的 ★main 包。本文按新定义、现行 dev 判法重新取数，**旧稿的 184 格、分类和「文意＋字形多路 86」作废**（那次把「文意弃权」也数成了一路，见第四节第 1 条）。

一句话：**机器已经放行的格，复核时有一路解法给了另一个字，而且只给了这一个字**，于是撤销放行送人审。它不是「不会判」，是「复核不同意」。

## 一、什么情况判成 Z03

分两段：cv 的 `group_flow` 先降审，manager 的 `reasons.py` 再起名。

### 1.1 cv：已放行的格怎么被「降」（`open_guji_cv/groups/flow.py`，复核模式 `mode=review`）

1. **前提**：册 yaml 的 `seed_admit.group_flow` 点名了这个字组；格已被别的通道放行（现 Z03 里 `match_ref` 175、`match_solo` 24、`ref_lib` 17、`match_replace` 13、`note_lexicon` 7、`context` 7、`iron` 3）；放行字或整理本字属于该组。
2. **复核解法**：组声明了 `review_methods` 就跑它，否则跑补放用的 `methods`（文意 `ctx`、字形 `ids`、看图 `vis`、`yr_bars`、`rr_img`、`form:*` 等），结果写进 `evidence.group.solvers`。
3. **比较**：解法给的字（`pick`）与放行字不同字，且不满足任何「可以改字」条件 → `group_flow_disagree`。
4. **豁免（任一成立就不降）**：`review_weak`、`abstain_ref_ok`、`shape_ref_ok`、`vis` 看图 L4 同字、`provisional` 暂归一、`fix`（`review_fix`／`review_fix_strong`／`review_fix_margin`／`review_fix_ref_rule` 改字而不降审）。
5. **降审**：`decision=demote`，`admit=False`，`doubts += group_flow_disagree`，`evidence.demoted_from={channel, by}`。

### 1.2 manager：怎么起名叫 Z03（`review/reasons.py` `_group_kind`，manager#304 后）

按顺序：字组已定字（admit／keep／provisional）、写法待定、整理本缺位 → 不是 Z；唯一反证是参校本〓 → R01；解法给了一个字且参校本是另一个真字（含复核的 `group_flow_ref_dissent`）→ Z04；解法给了 ≥2 个不同字（同字异形折叠后）→ Z02；**`decision=="demote"`（复核），解法折叠后只有一个字 → Z03**；`why` 是 weak／joint → Z07；一个字都没给 → Z01。

去向现为 `route=llm`（大模型统一过一遍，只收 high），负责 A24。

## 二、现在什么情况（★main 包现算，现行 dev 判法，正文页，2026-11-07）

| 书 | Z03 格 | 占该书待审 | 较 11-06 稿 |
|---|---:|---:|---|
| 四库总目（殿本，99 册） | 202 | 5,299 的 3.8% | 153 → 202 |
| 史記（有包 10 册） | 34 | 815 的 4.2% | 29 → 34 |
| 全唐文（有包 11 册） | 11 | 208 的 5.3% | 2 → 11 |
| 合计 | 247 | | 184 → 247 |

（梳理稿记 248 格，差 1 格是我按 `reasons_for_pending` 取、它按另一遍统计，不影响结论。）

247 格里 157 格是旧稿已有的，90 格是新增（殿本 72：yr 26、dt 11、guan 11、guang 6、xz 6…，史記 9，全唐文 9）；旧稿 27 格这次不在 Z03（新包重放或按新定义改落别码，未逐格核）。复核本身：殿本 513／史記 187／全唐文 31 格降审，复核 keep 31 万＋、fix 约 3 千，降审率约 0.16%。

按字组（殿本）：官宫 `guan` 38、一二 `yr` 35、于千子干 `zy` 22、問間 `wj` 11、大太 `dt` 10、木本 `mb` 9、十卜 `sb` 8、戊戌戍 `wxs` 8、廣賔賓 `guang` 7、象彖 `xz` 7、遺還 `yh` 6、論諭 `ly` 6、兩雨 `liang` 6、入人八 `rr` 6。史記：木本 7、入人八 4、大太、戊戌戍。全唐文：大太 9（见 F 类）。

## 三、什么样的格会归进来

按「放行字、整理本字、给字的是哪几路」分六类（只数**真给了字**的解法；文意弃权、`form:*`（组内选写法，不算独立证人）不算一路）：

| 类 | 说明 | 殿本 | 史記 | 全唐文 | 合计 |
|---|---|---:|---:|---:|---:|
| A 同义异体 | 放行字与复核字互为同义异体（宮宫、賓賔、敎教、敘叙、逄逢、絶絕、彝彞…），或两路只差写法 | 12 | 9 | 0 | 21 |
| B 仅文意单路 | 放行字＝整理本字，只有文意（`ctx`）一路给了另一个字 | 105 | 19 | 1 | 125 |
| C 仅字形路 | 放行字＝整理本字，只有字形路（`ids`／`yr_bars`／`rr_img`）给了另一个字，文意没给 | 46 | 5 | 1 | 52 |
| D 文意＋字形 | 放行字＝整理本字，文意加一路字形给了同一个另字 | 10 | 0 | 0 | 10 |
| E 放行字≠整理本字 | 放行字与整理本字（多是只有坐标对位）不同；其中复核字＝整理本字 23 格 | 28 | 1 | 0 | 29 |
| F 两路各执一字 | 文意给一个字、字形路给放行字，被 `are_variants` 当「同字异形」折成一个字，落了 Z03（本应是 Z02） | 1 | 0 | 9 | 10 |

几条事实：

- **247 格里 201 格库首位就是放行字（cov≥0.97），175 格是 `match_ref` 放行**：整理本、库、本格字三方互证过，被复核推翻。
- **多路反对其实很少**：真正文意＋字形两路同给另字的只有 10 格（D）；125 格只有文意一路（B），52 格只有字形路（C）。旧稿「多路 86」是把弃权的文意数成了一路。
- B 类的文意来源：L1 规则 67（其中 10 格 strong）、大模型缓存 high 45、L3 3。**C＋E 里有 39 格文意写的是 `abstain:llm_pending`，即大模型还没问到**，这批的文意是空的，不是反对。
- B 类 125 格里 108 格库首位也是放行字且 cov≥0.97，其中 102 格不是 strong。

### 看图

图在 `图/`：每格左边是本书这一格，右边「放」放行字、「参」整理本字、「复」复核字的刻例，下面是前后文。11-06 抽样 95 格看图；11-07 补看新增格里的 yr 和 dt。能读定的格存进 `Z03-bench-seed.tsv`（54 格，Claude 目视，**待 sheldon 复核**）：复核字对 28、放行字对 14、同义异体 12，其余读不定的没有硬判。

**A 同义异体**：[图1](图/1-同义异体.png)。宮／宫、賓／賔、敎／教、絶／絕、敘／叙，同义，放行字与整理本同形，复核另一个异体形反对。字取整理本形即可，不该送人。

**B 仅文意单路**：[图2](图/2-文意单路推翻-图上放行字是对的.png)。大／太（图上点的有无清清楚楚，是刻本的太抵、太僕，文意按通行词推成「大」）、自／目。B 类读得定的 8 格全是复核错；跨类读得定的非同义异体里，复核字错 14、对 4（旧稿口径，yr 补进来后见下）。

**官宮混刻**：[图3](图/3-文意加字形多路.png)（图名沿用旧稿）。「立於學[宮]」图上是宮、文意要「學官」；「釋宮」图上像官、文意要宮。刻本里官宮本身混刻，这类才是真正的「刻形与文意打架」，要人看。

**E 放行字与整理本不一**：[图4](图/4-放行字与参校不一.png)。主体是切窄的「十」被认成「卜」（宽 27–52，全表中位数 78）和一二的横画数不对。这时整理本（多半只有坐标对位）与复核同字，放行字才是错的，复核对。

**一二（`yr`）是这次最大的一块，复核几乎全对**：yr 在新 Z03 里 35 格（C 22＋E 13）。给字的是 `yr_bars`（数横画）加 `ids`，文意多半没问到。
- [图6](图/6-yr二变一-图上单横.png)：放行字「二」、整理本「二」（只有坐标对位）、复核「一」的 17 格，图上都是一横，前后文是「一卷」「[ ]卷」；我读得定的 16 格全是复核对（放行字和坐标对位的二是错的，另 1 格上半有碎点读不定）。
- [图7](图/7-yr一变二-图上两横.png)：放行字「一」、复核「二」的格，图上两横，复核对（我读定的 8 格全对）。
这 24 格已进种子，标复核字对。它们不该降审，应当直接改字。

**复核字对的其他例子**：[图5](图/5-复核对的例.png)（图上是面、放行字和整理本是而；切窄的十；釋宮）。

## 四、深挖：为什么会这样

1. **旧稿的「文意＋字形多路」是误数**：`solvers` 里文意弃权（`why=abstain:llm_pending`）也在列表里，我当时按名字数了。扣掉弃权之后，真正多路的只有 10 格。
2. **复核是「任何一路反对就降」**：只有 `rm mb mz rr` 开了 `review_fix_strong`，其余组 `review=True` 就是一票降审，没有「放行字有三方互证时要几票才能推翻」的概念。
3. **文意不是独立证人**：`ctx_l1` 是词表规则（太僕、釋宮、學官），`ctx_llm` 是通行写法，回答「这里该是什么字」，不是「图上刻的是什么字」。放行字已与整理本一致，说明整理本是照刻本录的；文意反过来推翻的恰是刻本里的异写。B 类读得定的 8 格全错。
4. **`yr_bars` 是好证人，却只能降审**：它数横画，图上一横两横一目了然；放行字（常是 `match_solo`／`match_ref` 靠坐标对位的整理本字）一旦错了，复核说得对，但 `yr` 没开 `review_fix`，只能降审，35 格白送人。
5. **F 类是 manager 折叠过宽**：manager#296 把「同字异形」折成一个字，用的 `are_variants` 把大／太、傳／傅、玉／王 也算同形（cv 的异体表是宽的）。这 10 格实际是文意与字形路各执一字（字形路站放行字一边），本应 Z02；全唐文 11 格里占了 9 格。
6. **同义异体的豁免有名单**：`REFERENCE_TRUST_SHAPE_GROUPS` 只列了 `guang yh fc em weiw lv qik lih jue jiao weim zh`；`xu`、`feng`、`yi_560`、`guan` 的宮宫不在内。
7. **`route=llm` 对 B 类是自指**：B 类的反对方本来就是文意，再交大模型读文意在候选里选，基本复现同一个答案。
8. **E 类含切分问题**：切窄的十、只剩一两横的一二，库首位 cov 照样 0.96–0.998，放行通道放了；复核反而对。

## 五、整条流程（供下一本书直接用）

```
seed_admit 各通道放行（match_ref／match_solo／context／…）
   │  格带 evidence.group（字组 id、放行字所在）
   ▼
group_flow 复核（mode=review，册 yaml seed_admit.group_flow 点名的组）
   │  跑 review_methods（缺省＝methods）→ trail：[{solver, char, why, via, strong, margin…}]
   ▼
pick 与放行字不同字？ ──否──► keep
   │是
   ├─ 可改字（review_fix / strong / margin / ref_rule / vis L4 改字）──► fix（改字，仍放行）
   ├─ 豁免（review_weak / abstain_ref_ok / shape_ref_ok / vis 同字 / provisional）──► keep 或 provisional
   └─ 否则 ──► demote：admit=False，doubts+=group_flow_disagree，evidence.demoted_from
   ▼
manager reasons._group_kind：复核、解法折叠后只有 1 个字、不是 ref_dissent ──► Z03（manager#304 后）
```

**参数表**（缺省值与说明；「书」＝每本书自己试、「组」＝在 `groups/registry.py` 的 `FlowSpec` 里按组定、「算法」＝通用代码）：

| 层 | 参数 | 缺省 | 作用 |
|---|---|---|---|
| 组 | `review` | 看组 | 开复核；不开就不降审 |
| 组 | `review_methods` | 空＝同 `methods` | 复核只跑这几路（异体组只看刻形 `ids`） |
| 组 | `review_fix`／`review_fix_strong`／`review_fix_margin`／`review_fix_ref_rule` | 关／关／0／关 | 给了别的字时**改字不降审**的条件（总是／文意 strong／方法 margin 够／L1 规则字＝整理本字） |
| 组 | `strong_over_ref`、`rule_strong` | 关、— | L1 规则 ≥N 条同字算 strong |
| 组 | `review_weak` | 空 | 这几路只算弱票（`rr_img`） |
| 组 | `review_abstain`、`review_ref_agree` | 关 | 解法全弃权也降（己已巳）；放行字≠整理本字也降（隸𨽾） |
| 书 | `reference_trust` | `none`（`high`／`very_high`） | 一键「按参校本走」：`high` 起 `shape_ref_ok` 名单（廣賔 還遺 …）、`abstain_ref_ok`（己已巳 曾會㑹）、`lift_shape_ref`（日曰）、异体取整理本形 |
| 书 | `group_flow_abstain_ref_ok`／`group_flow_lift_shape_ref`／`follow_ref_variants` | 空／空／关 | 上面三项的分开关，取并集，按书微调 |
| 书 | `group_flow_provisional`、`group_flow_provisional_to` | 开、空 | 同义异体暂归一兜底 |
| 书 | `group_flow_lift_ref_guard`、`group_flow_coord_outside_skip` | 开、开 | 补放与整理本互证；坐标对位字是组外字不入组 |
| 算法 | `vis_model`／`ruling_glyph_min_score`／`ruling_glyph_margin` | 空／见册 | 复核时看图 L4（只读裁定库，不调 API）；殿本 0.98／0.02，史記全唐文 0.95／0.02 |
| 算法 | `ctx_llm` 缓存 `llm_conf`／`panel`／`strong` | 只读 | 文意答案 high／mid／low；二审小组同字记 strong |

按字组的复核配置（cv dev 现行 `registry.py`）：`rm mb mz` 开 `review_fix_strong`（`mb` 另开 `review_fix_ref_rule`）；`rr` 开 `review_fix_strong`＋`review_weak=(rr_img,)`；`jiao jue xu lih yi_560` 等异体组 `review_methods=(ids,)`（`yi_560` 另 `review_fix_margin=0.3`）；`zy` `review_methods=(ctx,)`；`yr wj ly dt sb yh yt em fc wyu zh wxs xz` 只开 `review=True`；`guan liang guang feng` 为文意／形近对、`review=True`，无改字。

## 六、benchmark 怎么定义

**对象**：复核模式下「有路给了与放行字不同的字」的格（总体）；Z03 是其中最终被降的那部分。三书这次总体：被降 247 格；**有异议但被豁免放过去的 769 格**（`dis_kept`：殿本 keep 235、provisional 59、fix 4；史記 keep 236、fix 21；全唐文 keep 96、provisional 118；字组 xz 127、rr 107、zh 109、guang 34、jue 20…）。后者才能量「误保留」，取数脚本 `Z03-scripts/extract.py` 已一并输出。**金标**：每格的真字，人看图加文意定（`guji-manager review-pages build gold_sample`，每组每书各抽 30 格；三书各自留出，不继承殿本）。

**指标**（按册留出，门槛先定在「误保留 0」）：

| 指标 | 含义 | 目标 |
|---|---|---|
| 误保留 | 放行字是错的，复核却放过去 | 0 |
| 误降审率 | 放行字是对的，复核降审（送人白看） | 越低越好，记录基线 |
| 改字准确率 | `fix` 后字是对的比例 | 100% |
| Z03 格数 | 三书合计，要降的数 | 基线 247 |

**种子**：`Z03-bench-seed.tsv` 54 格（Claude 目视，待 sheldon 复核）：复核字对 28（yr 24、其余 4）、放行字对 14、同义异体 12。**当前复核在种子上的表现**：放行字对的 14 格全被降审，同义异体 12 格全被降（不该降）；复核字对的 28 格降对了，但其中 24 格（yr）本可直接改字。样本小，只说明方向。

## 七、怎么提高（sheldon 11-07「都按你的建议来」：①②⑤ 已做，③④⑥⑧ 要先过金标再开）

| # | 办法 | 预计影响 | 前提 |
|---|---|---|---|
| ① | ✅**已做**（cv#1229，seed_admit 1.59 `group_flow_same_writing_keep`，缺省 xu feng yi_560 guan guang jiao jue；旨㫖 等按刻形复核的组不在内，会误放真次形）**同义异体不降审**：把 `xu feng yi_560 guan（宮宫）` 并入「只有字形路反对也不降」，或新增书级开关「同义异体且放行字＝整理本字 → 不降」 | A 类 21 格（殿本 12、史記 9）→0 | 无需金标；`guan` 的 `form:canon` 为何没把宮宫判成同字需先查 |
| ② | ✅**已做**（cv#1229，`group_flow_review_fix_agree` 缺省 `[yr]`，条件＝≥2 路不同图像解法 yr_bars＋ids 同给别字且无人反对）**一二（`yr`）复核按 `yr_bars`（加 `ids`）改字**，不降审：`yr` 声明 `review_fix`（或 `review_fix_margin`），要求 bars 与 ids 同字 | yr 35 格（C 22＋E 13），目视 24 格全对 | 先 sheldon 复核种子里的 24 格，再按册留出验证；条件要写死「bars 与 ids 同字」 |
| ③ | **复核字＝整理本字（含坐标对位）≠放行字 → 改字**（现 `review_fix_ref_rule` 只对木本开），试 `sb zy guan` | E 类除 yr 外约 10 格（卜→十 7 等） | 先过金标；这批同时是切分问题（切窄的十），转 A22 |
| ④ | **三方互证时，文意单路不够推翻**：放行字＝整理本字＝库首位（cov≥0.97）、只有一路文意（非 strong）反对 → 不降审 | B 类约 102 格；**风险最大**，种子里「放行字对」14 格都在 B 类，但复核对的格（面／而）也有库首位反对 | 必须先做金标，误保留 0 |
| ⑤ | **F 类 10 格**：manager 折叠只折真同义异体，大／太、傳／傅、玉／王 不折；它们落 Z02（文意与字形路各执一字） | Z03 −10，Z02 +10，全唐文 Z03 11→2 | 改 manager 分类，先通知 A31–A34 |
| ⑥ | 39 格文意 `llm_pending`：先把文意缓存问完再判（现在这批的文意是空的） | 不确定，可能一部分变成同字放行 | 按「不调 API」，开干净会话审后写裁定缓存 |
| ⑦ | **路由**：`route=llm` 对 B 类自指，改 `human`，或另做不看文意的看图复核 | 不减格数，减无效往返 | 通知 A31 |
| ⑧ | 10 格文意 strong（兩雨 戊戌 大太 卜十）：评估给 `liang wxs dt sb` 开 `review_fix_strong`；种子里兩雨图上像雨、文意要兩，要 sheldon 定「按刻形还是按文意」 | ≤10 格 | sheldon 定口径 |

叠加预期（上限）：①②③④⑤ 合计约 21＋35＋10＋102＋10＝178 格（72%）离开 Z03；其中只有 ①②（有目视依据）和 ⑤（分类修正）把握较高，③④ 必须先过金标，**没有金标时不要开**。

## 八、给「分流统计脚本同步了没有」的答复

- **代码侧已同步**：`pending-stats`、`diagnose.py`（`GROUP` 已含 `group_unconfirmed`）、`final_review/core.py`（`CLASS_OF`）都按 `reasons.py` 的码出数，manager#304 合入后现算自动是新码；本文取数 `Z03-scripts/extract.py` 直接调 `reasons_for_pending`，口径与之一致。
- **文档侧没同步**：ai-team `三书待审原因统计/`、`分流设计/` 里的旧表和分流稿仍是旧码口径（没有 Z07、Z03 范围老）；各会话要按各自的码用同一方式重新统计，不要引用这两处旧数。我这个码的新数就是第二节。

## 九、材料

ai-team `待审原因深挖/Z03-逐格-三书247格.tsv`（逐格：类、放行字、整理本字、复核字、库首位、给字的解法、是否新增）、`Z03-bench-seed.tsv`、`图/`、`Z03-scripts/`（`extract.py` 取数并输出 `dis_kept`、`crops.py` 裁格图、`sheet.py`／`bigsheet.py`／`mont.py` 拼图）。云端取数装法同 Z01：假工作区（`workspace.yaml`＋`.central.json`）、`GUJI_DATA_HOME`、`guji db pull --no-rebuild`、`guji products pack fetch`、`guji source pull`。★main 包各册生成的 cv 版本不一（殿本 80 册是 0.6.16，其余旧包），口径是「各册 ★main 现有产物」。
