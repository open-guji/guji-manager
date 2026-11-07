# Z03 `group_demoted`：形近字·复核推翻（字符级深挖，A24，2026-11-06）

> **11-07 新定义（manager#304，[Z类梳理](../Z类梳理.md)）**：Z03 只收「复核，解法只给一个字、与放行字不同」；复核时解法没字归 Z01、≥2 字归 Z02、整理本是组里另一形（`group_flow_ref_dissent`）归 Z04。detail 写 `组:review`。三书新口径 殿本 203、史記 34、全唐文 11。下文是 11-06 旧口径的分析。

> [待审原因总览](../README.md) · 原因码一句话：复核给了与放行字不同的字

派单见 ai-team `domain/CV/质检/待审原因深挖/派单-2026-11-06.md`（第 3 批）。按 sheldon 11-06 定的格式：先说什么情况判成这个原因、现在什么情况，配图看哪些字会归进来，再谈怎么提高；并把整条流程、参数、benchmark 写清，方便下一本书直接用。底稿、逐格表、脚本在 ai-team `domain/CV/质检/待审原因深挖/`（`Z03-复核推翻.md`、`Z03-逐格-三书184格.tsv`、`Z03-bench-seed.tsv`、`Z03-scripts/`）。**本文只给结论，没改任何代码**（要改的见第七节，改原因码分类要先经协调者通知 A31–A34）。

一句话：**机器已经放行的格，复核时有一路解法（多数是文意）给了另一个字，而且只给了这一个字**，于是撤销放行送人审。它不是「不会判」，是「复核不同意」。三书合计 184 格（殿本 153、史記 29、全唐文 2），在待审里很小（殿本占 3.2%），它和 Z02、Z04 一样，是我们自己的复核降审制造出来的待审，所以值得弄清楚复核对不对。

## 一、什么情况判成 Z03

分两段：cv 的 `group_flow` 先降审，manager 的 `reasons.py` 再起名。

### 1.1 cv：已放行的格怎么被「降」（`open_guji_cv/groups/flow.py`，复核模式 `mode=review`）

1. **前提**：册 yaml 的 `seed_admit.group_flow` 点名了这个字组；格已被别的通道放行（殿本 Z03 里 `match_ref` 142、`match_solo` 12、`context` 9、`note_lexicon` 8、`match_replace` 7、`ref_lib` 5、`iron` 1）；放行字或整理本字属于该组。
2. **复核解法**：组声明了 `review_methods` 就跑它，否则跑补放用的 `methods`（文意 `ctx`、字形 `ids`、看图 `vis`、`yr_bars`、`rr_img`、`form:canon` 等）。结果写进 `evidence.group.solvers`。
3. **比较**：解法给的字（`pick`）与放行字不是同一字（按组归一后比），且不满足任何「可以改字」条件 → 记 `group_flow_disagree`。
4. **豁免（任一成立就不降）**：`review_weak`（弱票单独反对）、`abstain_ref_ok`、`shape_ref_ok`（只有 ids 反对且放行字＝整理本字）、`vis` 看图 L4 高置信同字、`provisional` 暂归一、`fix`（`review_fix`／`review_fix_strong`／`review_fix_margin`／`review_fix_ref_rule`：改字而不降审）。
5. **降审**：`decision=demote`，`admit=False`，`doubts += group_flow_disagree`，`evidence.demoted_from={channel, by}` 记原通道。

### 1.2 manager：怎么起名叫 Z03（`review/reasons.py` `_group_kind`，priority 42）

格带 `group` 证据，且依次排除：`form_open`→Z（形态待开）；解法一个字都没给→Z01；`why` 是 `ref_dissent／coord_dissent／ref_dissent_follow`→Z04；解法给了 ≥2 个不同字或 `why` 是 `conflict／joint`→Z02；**最后 `decision=="demote"` → Z03**（否则 Z05 证据弱）。H01（己已巳日曰极难形近）、D／S／X 等更靠前的原因先判。

所以 Z03 的精确含义：**只有一个字被解法给出、与放行字不同、复核没找到豁免**。去向现为 `route=llm`（大模型统一过一遍，只收 high，其余回人），负责 A24。

## 二、现在什么情况（★main 包现算，正文页，2026-11-06）

| 书 | Z03 格 | 占该书待审 | 该书复核 demote 总数 | 复核 keep／fix |
|---|---:|---:|---:|---|
| 四库总目（殿本，99 册） | 153 | 4,715 的 3.2% | 504 | 314,511／3,003（另 provisional 178） |
| 史記（有包 10 册） | 29 | 845 的 3.4% | 186 | 24,611／42 |
| 全唐文（有包 11 册） | 2 | 125 的 1.6% | 24 | 27,132／815（另 provisional 119） |

派单与总览里的 146／214 是线上单口径，比包旧；逐格明细按包现算的 184 格走：`Z03-逐格-三书184格.tsv`。复核每查 1,000 格约降 1.6 格，降下来的 504 格里 153 格落 Z03，其余按解法数落 Z02／Z04／Z01 等。

按字组（殿本）：官宫（`guan`）31、于千子干（`zy`）22、日目（`rm`）10、一二（`yr`）10、問間（`wj`）9、論諭（`ly`）7、大太（`dt`）7、戊戌戍（`wxs`）7、廣賔賓（`guang`）6、兩雨（`liang`）6、木本（`mb`）5、其余零散。史記以木本（7）、入人八（4）、大太、戊戌戍为主。

## 三、什么样的格会归进来

按「放行字、整理本字、库首位、复核给的字」的关系和有几路解法反对，分五类（三书合计）：

| 类 | 说明 | 殿本 | 史記 | 全唐文 | 合计 |
|---|---|---:|---:|---:|---:|
| A 同义异体 | 放行字与复核字互为同义异体（宮宫、賔賓、敎教、絶絕、厯歴、敘叙、逄逢、彝彛彞），放行字＝整理本字 | 13 | 5 | 0 | 18 |
| B 仅文意单路推翻 | 放行字＝整理本字（含坐标对位），只有 `ctx` 一路给了另一个字；其中 50 格库首位也＝放行字且 cov≥0.97 | 50 | 10 | 0 | 60 |
| C 仅字形路单路推翻 | 同上，但反对的只有 `ids` 字形路（廣實→賔 4 格） | 4 | 0 | 0 | 4 |
| D 文意＋字形多路推翻 | 放行字＝整理本字，`ctx` 加 `ids`／`vis`／`yr_bars`／`rr_img` 至少两路给同一个字 | 70 | 14 | 2 | 86 |
| E 放行字≠整理本字 | 放行字与整理本字（多是只有坐标对位）不同，复核给的字与整理本字同（10）或不同（6） | 16 | 0 | 0 | 16 |

几条事实先说：

- **184 格里 166 格库首位就是放行字**（142 格 cov≥0.97）。也就是整理本、库、放行字三方一致，被复核的一路或几路推翻。
- **142 格是 `match_ref` 放行的**，即「整理本字＝库首位＝本格字」互证过的格。
- 单路反对 64 格（B＋C），其中文意 `ctx_l1`（L1 规则）44、`ctx_llm` high 12（缓存里的大模型答案）、L3／L2 4，`ids` 4。**有 12 格文意是 strong（≥2 条规则同字，兩雨、戊戌、大太、卜十），但这几组没开 `review_fix_strong`，所以只降审不改字。**
- 多路反对（D）的 86 格，反对的几路里文意几乎都在（`ctx_llm` high 38、L1 31），字形路是陪衬，不是独立证据（见第四节）。

### 看图（目视核对）

图在 `图/`：每格左边是本书这一格（带框），右边「放」放行字、「参」整理本字、「复」复核给的字，下面是前后文。**每个（字组、放行字→复核字）对抽 ≤2 格，共 95 格看图；其中能读定的 30 格存成 `Z03-bench-seed.tsv`（Claude 目视，待 sheldon 复核）：放行字对 14、复核字对 4、同义异体 12，其余 65 格我读不定（笔画太糙、半边残、官宮这类刻本本身混刻），没有强行判。**

**A 同义异体**：[图1](图/1-同义异体.png)。宮／宫、賔／賓、敎／教、絶／絕、厯／歴、敘／叙、逄／逢、彝／彞，两形同义、整理本与放行字同形，复核另一个异体形（`ids` 或 `form:canon`）反对。按「同义异体暂归一只限同义」这些本不该送人，字取整理本形即可（书级 `reference_trust: high` 起把 `guang yh fc em weiw lv qik lih jue jiao weim zh` 列为「只有 ids 反对就不降」，`xu feng yi_560 guan` 不在表里；这 18 格的册没有靠它豁免）。

**B 仅文意单路推翻**：[图2](图/2-文意单路推翻-图上放行字是对的.png)。大／太（图上点有无清清楚楚，是刻本写的 太抵、太僕，文意按通行词推成「大」）、自／目、本字。**B 类里我读得定的 8 格（大太 6、自目 2），复核字全错**；跨类读得定的非同义 18 格里复核错 14、对 4（错的还有傳／傅、實／賔、廣／賔、卜卦、而）。LLM 或规则读的是通行写法，不看刻形；而项目规矩是「异体看刻形，形近不同义看文意」，这批里刻形与整理本、库都一致，文意单路并不构成够强的反证。

**D 文意＋字形多路**：[图3](图/3-文意加字形多路.png)。官／宫（刻本官宮混刻，如「立於學[宮]」图上是宮、文意要「學官」；「釋宮」图上像官、文意要宮）、問／間、論／諭、人／入、千／干／于／子，多数我读不定，这类才是真正「刻形与文意打架」，要人看。

**E 放行字与整理本不一**：[图4](图/4-放行字与参校不一.png)。主体是**切窄的「十」被认成「卜」**（多数格宽 27–52，全表中位数 78，横画被切掉）、**只剩一两横的「二」认成「一」**。这时整理本（多半只有坐标对位）与复核同字，放行字才是错的——**复核对**，应该直接改字而不是降审（现有 `review_fix_ref_rule` 只对木本开）。

**复核对的例子**：[图5](图/5-复核对的例.png)（面／而：图上是面，放行字和整理本都是而，库首位面 0.9948；十／卜：切窄的十；釋宮：宮被放成官）。读定的 4 格，说明复核**不是全错**，不能一刀砍掉。

## 四、深挖：为什么会这样

1. **复核是「任何一路反对就降」**：`flow.py` 复核分支里，只有 `rm mb mz rr` 开了 `review_fix_strong`，其余组 `review=True` 就是一票降审，没有「放行字有三方互证时要几票才能推翻」的概念。
2. **文意不是独立证人**：在 `ctx_l1` 里是词表规则（兩淮、太僕、釋宮、學官），`ctx_llm` 是通行写法，二者回答的是「这里该是什么字」，而不是「图上刻的是什么字」。放行字本来已经与整理本一致，说明整理本就是照刻本录的；文意反过来推翻的恰是**刻本里的异写或整理本如实照录的写法**。这一路给出的字对 B 类读得定的 8 格全错。
3. **D 类的多路不是多个独立证据**：`ids`、`vis`、`rr_img` 都是看同一块图，且 `ids` 是 HOG 一对多，对糊图常给陪衬字（廣→賔：图上清清楚楚是廣，`ids` 给賔，margin 0.38–0.5）；只有文意是另一类证据。所以「≥2 路」的 86 格里有多少真的是两路独立，需要金标才能说。
4. **`route=llm` 在这里是自指的**：Z03 的反对方本来就是文意（`ctx_llm` high／L1 规则），再交「大模型统一过一遍」读文意在候选里选，几乎必然复现同一个答案。B／D 两类 146 格走这条路等于没走。
5. **E 类是切分问题伪装成形近字**：切窄、切成单横的格，库首位 cov 照样 0.96–0.998（卜 0.998），所以放行通道（`match_solo`、`context`）放了；复核反而是对的。
6. **同义异体的豁免有名单**：`REFERENCE_TRUST_SHAPE_GROUPS` 只列了 `guang yh fc em weiw lv qik lih jue jiao weim zh`；`xu`（叙敘）、`feng`（逄逢）、`yi_560`、`guan` 的宮宫不在内；殿本不开 `reference_trust`。这些格不该送人。
7. **覆盖面**：这 184 格只是复核最终的「降」，复核中 `keep`/`fix` 的 340k 格里有多少是「文意反对但被豁免放过去」的，要用 `evidence.group.solvers` 里 `char≠放行字` 的格另算（第六节 benchmark 的总体）。

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
manager reasons._group_kind：解法给 1 个字、why 非 ref_dissent/conflict/joint ──► Z03（priority 42）
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

**对象**：复核模式下「文意或字形有路给了与放行字不同的字」的格（总体）；Z03 是其中最终被降的那部分。**金标**：每格的真字，由人看图加文意定（用 `guji-manager review-pages build gold_sample` 现成模板，每组、每书各抽 30 格；三书各自留出，不继承殿本）。

**指标**（按册留出，门槛先定在「误保留 0」）：

| 指标 | 含义 | 目标 |
|---|---|---|
| 误保留 | 放行字是错的，复核却放过去 | 0 |
| 误降审率 | 放行字是对的，复核降审（送人白看） | 越低越好，记录基线 |
| 改字准确率 | `fix` 后字是对的比例 | 100% |
| Z03 格数 | 三书合计，要降的数 | 基线 184 |

**种子**：`Z03-bench-seed.tsv` 30 格（Claude 目视：放行字对 14、复核字对 4、同义异体 12，待 sheldon 复核）。**当前复核在种子上的表现**：放行字对的 14 格全被降审（误降审 14/18＝78%，不含同义异体）；复核字对的 4 格降对；同义异体 12 格全被降（不该降）。样本很小，只说明方向，不能当门槛。取总体的办法：重跑取数脚本时多收 `evidence.group.solvers` 里 `char≠放行字` 但 `decision=keep/fix` 的格（脚本 `Z03-scripts/extract.py`，加一行即可），这批才能量「误保留」。

## 七、怎么提高（都待 sheldon 讨论；未动代码）

| # | 办法 | 预计影响 | 前提 |
|---|---|---|---|
| ① | **同义异体不降审**：把 `xu feng yi_560 guan（宮宫）` 并入「只有字形路反对也不降」，或新增书级开关「同义异体且放行字＝整理本字 → 不降」；殿本若不信任整理本，则同义异体直接按整理本形暂归一 | A 类 18 格→0（殿本 13、史記 5） | 无需金标（同义）；`guan` 的 `form:canon` 为什么没把宮宫判成同字，需先查 |
| ② | **复核字＝整理本字（含坐标对位）≠放行字 → 改字放行**（现 `review_fix_ref_rule` 只对木本开），先在 `sb yr zy mb` 试 | E 类约 13 格（主要是切窄的十／卜、切成单横的二／一） | 先过金标；这批同时是切分问题，转 A22 看切窄格 |
| ③ | **三方互证时，文意单路不够推翻**：放行字＝整理本字＝库首位（cov≥0.97），且只有一路文意（非 strong）反对 → 不降审、记 `review_weak` 一类留痕 | B 类约 44 格（50 格三方一致里去掉 strong 的）；**这条风险最大**，种子里「放行字对」14 格都在 B 类，但复核对的格（如 面／而）也有库首位反对的 | 必须先做金标，门槛误保留 0 |
| ④ | 12 格文意 strong（兩雨 戊戌 大太 卜十）：评估给 `liang wxs dt sb` 开 `review_fix_strong`——但种子里兩雨图上像雨、文意要兩，要 sheldon 定「按刻形还是按文意」 | ≤12 格改字 | sheldon 定口径 |
| ⑤ | 路由改：`route=llm` 对 B／D 类自指，改成 `human`，或另做「看图只读、不给文意」的复核（`vis` 独立证人） | 不减格数，减无效 LLM 往返 | 要通知 A31（原因码去向） |
| ⑥ | D 类 86 格先不动：多路文意＋字形，官宫、問間、論諭 刻本本身混刻，靠人 | — | — |

叠加预期（上限）：①＋②＋③ 最多 18＋13＋44＝75 格（约 41%）离开人审，其中只有 ① 有把握；②③ 必须先过金标，**不要在没有金标时开**。

## 八、材料

`Z03-逐格-三书184格.tsv`（逐格：类、放行字、整理本字、复核字、库首位、解法、文意来源）、`Z03-bench-seed.tsv`、`图/`、`Z03-scripts/`（`extract.py` 取数、`crops.py` 裁格图、`sheet.py`／`bigsheet.py`／`mont.py` 拼图）。云端取数装法同 Z01：假工作区（`workspace.yaml`＋`.central.json`）、`GUJI_DATA_HOME`、`guji db pull`、`guji products pack fetch`、`guji source pull`。注意 ★main 包各册生成的 cv 版本不一（有的是 cv0.5.26 老包），三书口径是「各册 ★main 现有产物」，不是同一次重跑。
