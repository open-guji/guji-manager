# V01 `variant_pair`：整条流程、判断标准与参数、benchmark（A24，2026-11-06）

> [总述](README.md) · [字符级深挖](深挖-2026-11-06.md)（三书现状与配图）。本篇回答 sheldon 11-06 的三个问题：什么样的字会进 V01、判断标准和参数在哪、怎么定 benchmark；并整理一套下一本书能照做的流程。

## 一、一个格怎么走到 V01（全流程）

V01 不是「判出来的」，是**前面所有放行通道都没放、也没被更靠前的原因认走之后剩下的**。分两段：

### 段 1：放行通道（cv `seed_admit`，决定格有没有放）

待审格（库没把握）按下面的顺序碰运气，谁先放谁赢；每条通道的条件都是**同一套**：库首位在「整理本字—另一形」这一对里、cov 够、领先对外候选够、没有硬护栏。

| 顺序 | 通道 | 谁来认「这是一对」 | 开关（缺省） | 备注 |
|---|---|---|---|---|
| 1 | `group_flow`（字组流程） | 字组注册表 `groups/registry.py` 的组员 | 全开 | 两字都在某个组里，组自己判；入口条件见下 |
| 2 | `follow_ref`／`follow_ref_seen` | 书级登记的 `a=b` 对（`book_defaults.yaml`）；`follow_ref_seen` 是看图证实「整理本总对」的对 | 按书登记 | 殿本 `follow_ref` 只有 9 对；全唐文有 `follow_ref` 和 `follow_ref_seen` |
| 3 | `follow_ref_variants` | 异体表里与首位同义异体的整理本字 | **只有史記开**（`books/*.yaml`） | 四库系、整理本可信的书 |
| 4 | `edge_pair`（cv#813） | 异体表自动对：`edge_tier==T1`、≥2 个 BRIDGE 来源、**两字都不在字组里**、不在排除表 | 缺省开 | 放两形里已放行频次高的一形（暂归一） |

**组入口**（`groups/flow.py entry`，通道 1）：库首位 cov≥`min_cov`(0.85)，且分差 `delta`(0.03) 以内的候选**全是组员**（或该组的陪衬字 `tol`），整理本字也是组员，才进组。
**通道 2–4 共用的判据**（`seed_admit.follow_ref_decide`／`edge_pair_pass`）：库没判 diff、没有遮挡／乱码／`near_form`／`护栏:` 等硬疑问、库首位 cov≥0.92（`follow_ref_cov`／`edge_pair_cov`）、领先「这一对以外最好候选」≥0.005（`follow_ref_gap`／`edge_pair_gap`）、有 `ctx_guard_ref` 类疑问时文意字必须在这一对里。

### 段 2：原因判定（guji-manager `review/reasons.py`，决定没放的格叫什么）

按 `pending_reasons.yaml` 的 priority 从小到大，第一个命中的就是主原因。V01 是 55，前面依次是：X01–X04（裁定冲突／机器改了字／复审）、S/D（切分、遮挡）、H01（己已巳日曰）、Z01–Z06（字组）、R03/R01、L01、L05、R02。**所以进 V01 的格已经排除了：有遮挡、切坏、整页对不上、在字组里弃权、整理本缺字、库里没有这个字。**

V01 的判法（`_variant_with_ref`，**2026-11-06 起按 manager#265 收窄**）：

```
带 ref_lib_variant / variant_indirect / replace_form / channel_off 任一码
或：有整理本字 且 库首选≠整理本字 且 x∈{库首选, 机器字}（x≠整理本字）满足
    are_variants(整理本字, x) 且 edge_tier(整理本字, x) ∈ {T1, T2}
```

（收窄前是「库前 5 名里任一字有边」，且含 T3 通假形近；下文「现在的混乱」与深挖报告里的 388／205 格数字都是**收窄前**口径。旧 cv 没有 `edge_tier` 时退回只看有没有边。）

`are_variants` 是异体表的「任一来源收录」，**含 `unihan:kSpoofingVariant`（形近易混）和 `hydzd-borrowed`（通假）**——而 `variants.py` 自己写明这两个「永不当异体」（`NEVER_SOURCES`）。

V01 之后的原因：N01（形近护栏）56、L03/L02（刻例少）、P01（识别字≠整理本）、L04、P02。

## 二、判断标准与参数一览（散在三处，现在列在一起）

| 层 | 参数 | 值 | 在哪 | 谁管 |
|---|---|---|---|---|
| 异体表 | 边的来源、`BRIDGE_SOURCES`、`NEVER_SOURCES`、`T2_SOURCES`、`WEAK_ALONE_SOURCES` | 见 `variants.py` | cv `variants.py`、`config/variants/variants.json` | A24 |
| 边分档 | `edge_tier` T1 纯异体／T2 互通·一对多／T3 通假·形近·简繁 | | `VariantGraph.edge_tier` | A24 |
| 自动对 | `MIN_SOURCES`=2、`FREQ_MIN`=20、排除表 `config/variants/edge_pair_exclude.tsv`、频次表 `form_freq.tsv` | | `groups/edge_pairs.py` | A24（排除表按书补） |
| 放行 | `follow_ref_cov` 0.92、`follow_ref_gap` 0.005、`edge_pair_cov` 0.92、`edge_pair_gap` 0.005、`edge_pair`（开）、`follow_ref_variants`（史記开）、`follow_ref`／`follow_ref_seen`（按书） | | `seed_admit.SeedAdmitParams`、册 yaml、`book_defaults.yaml` | 书项目 |
| 组入口 | `min_cov` 0.85、`delta` 0.03、`ref_enter`／`ref_top_enter`、`FLOW_GROUPS` | | `groups/flow.py`、`groups/registry.py` | A24 |
| 原因 | priority 55、前五候选、`are_variants` 任一来源 | | manager `reasons.py`、`pending_reasons.yaml` | A24（改分法先通知 A31–A34） |

## 三、现在的混乱在哪（清理清单）

1. **同一个「是不是异体」有三套口径**：`reasons.py` 用 `are_variants`（任一来源，含通假形近）；`seed_admit` 用 `edge_tier==T1 且 ≥2 来源`；`follow_ref_variants` 用 `vmap`（异体表同义异体）。放行用严口径、归因用宽口径，结果 388 格里 205 格归因不对。→ **统一成一个函数** `variant_edge(a,b) -> {tier, n_sources, never_only}`，三处都调它。
2. **归因看前五、放行看首位**：放行只管库首位与整理本这一对，原因判定却在前五里找任一异体，两头对不上。→ **已做**（manager#265，A31 按本报告实现）：V01 只认首选或机器字与整理本字的边，边分型只认 T1／T2。
3. **字组成员对被夹在中间**（30 格）：`edge_pair` 说「字组自己判」，组入口又因分差内有组外字不接。→ 二选一补洞（见深挖报告第四节第 3 条）。
4. **文档不一致**：`README.md` 的判定依据和 yaml `detect` 一句话写「不在字组里」，代码并没查字组；方法论 4.5 写「T1＋≥2 来源」是放行条件，不是 V01 条件；`pending_reasons.yaml` 的 `route: human` 注释「待定」。→ README 重写定义、改成「放行通道没放的、首选/机器字与整理本互为异体边的格」；detect 与代码对齐。
5. **异体表脏边**：twedu 收古文、`hydzd` 收通假、`yitizi` 单家不可溯源，造成 兩雨、大太、晝畫、傳傅 等被当边。→ 与「放行 X03 三者一致格并补异体表」线程对接：补边只加同词异体，已确认不是异体的字对进排除表。
6. **没有基线数字**：`pending-stats` 只给 V01 总数，不分真异体与误归。→ 见下 benchmark。

以上 1、2、4 是代码／文档清理，**不改放行结果**；改 reasons.py 分法属改原因码分法，先 `send.py` 通知 A31–A34。我先不动，等 sheldon 点头。

## 四、benchmark（建议）

目标：不只是把这几个字对录对，而是下一本书拿到 ★main 包，一条命令就能出「V01 体检表」，知道该调哪个旋钮。

### 4.1 金标

`V01-pairs-benchmark-seed.tsv`：三书 A/B/E 类里 144 种「整理本字>库首选」字对，列有格数、边档、书、**初判（我凭印象标的，不能当真值）**、「sheldon 定」列留空。流程：用 review_pages 的 `pair_whitelist` 页型，每对抽 ≤10 格带上下文看图，sheldon 点「同词异体／不同字／看不清」，写回「sheldon 定」列，**这才是金标**。

金标分三层，按书独立（不继承）：
- 字对层：同词异体（Y）／不同字（N）／两可。
- 形层：同词异体里，本书刻的是哪一形（殿本按刻形，四库系按整理本）。
- 格层：每对抽的格的人裁结果（已有人裁事件即可复用）。

### 4.2 指标（每本书、每轮出一张表）

| 指标 | 定义 | 目标 |
|---|---|---|
| V01 纯度 | V01 格里「首选与整理本是金标 Y 对」的比例 | ≥90%（现约 27%） |
| 误归率 | 金标 N 对的格被归 V01 的比例 | →0 |
| 放行错放 | `edge_pair`／`follow_ref_variants` 放出的格里，放的字与金标不符的数 | **0**（红线） |
| 放行覆盖 | 金标 Y 对的待审格里已放行的比例 | 逐轮升 |
| 残留 | 金标 Y 对没放行的格，按挡路原因分（T2、组缝、gap、cov、单来源、护栏、旧包） | 每类有负责手段 |
| 表脏度 | 异体表边落在金标 N 的比例（按来源分） | 指导补表 |

出表脚本：`分析脚本/extract.py`（逐册取 ★main 包算 V01 格及边的来源、挡路原因）＋ `pics.py`（拼图）；下一步我把「挡路原因」那段（深挖里 `blk`）收进 `guji-manager pending-stats`，让它按书直接出 6 项指标。

### 4.3 新书快速做的流程

1. 跑一遍 `pending-stats`（带 V01 细分）和 `extract.py`，得 V01 体检：纯度、各挡路原因格数。
2. 看书的参照策略：整理本可信（四库系）→ 开 `follow_ref_variants`，关暂归一；不可信（殿本）→ 靠 `edge_pair` 暂归一。
3. 异体表脏边：对该书 V01 里的 N 对补 `edge_pair_exclude.tsv`；真异体对但 T2 的，进该书白名单页逐对定。
4. 字组缝：看「在字组里但没接手」的格，补组入口或 `ref_top_enter`。
5. 放行红线：改任何参数都先在留出册回放，**错放 0** 才开。
6. 剩余少数真异体人审，一对定一次，写进码位表。

## 五、下一步

0. 已落地：清理清单 2（V01 收窄，manager#265）、yaml `detect` 已改；README 同步更新。下一轮 `pending-stats` 重出后，V01 应从 388 降到约 172（需核对：用本篇 4.2 的指标表跑一次）。
1. 仍待做：清理清单 1（统一 `variant_edge`，放行与归因共用一个函数）、4 中 README 定义重写（本 PR 已改）。
2. 做 pair_whitelist 页，144 对逐对看图出金标。
3. 把挡路原因与 6 项指标收进 `pending-stats`。
