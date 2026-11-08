# X01 `ruling_conflict`：整条流程、判断标准与参数、benchmark（A24 接手，2026-11-06）

> [总览](README.md) · 深挖报告（A31）ai-team `domain/CV/质检/待审原因深挖/X01-裁定冲突.md`。X01 的规则后续由 A24 改。

## 一、X01 是什么、哪些字会进

殿本换图源（siku-qiefen-v2）后，文本层在缺字位给私用码 U+F1xxx，同码＝同字。**码表**（cv `config/pua/siku_qiefen_v2_codes.json` ＋ 数据目录 `config/pua/pua_table.jsonl`）把码定到字（只收人裁一致或 sheldon 点选的码）。X01＝「格有私用码、码表定了字，但放行的是另一个字，而且机器不能直接改」，只剩两种：

1. **一码多字的码**（`families`，如 F1001/F1055＝乖垂埀；pua_table 里 `verdict=multi` 的码，同一族）：放行字落到**族外**。
2. 关着 `pua_code_table`（书级开关）时旧的窗口降审（src-1 `code_conflict`）。

人裁格与码表冲突不算 X01（机器不能降），只计入每页 `n_code_mismatch`，由人看图改。史記、全唐文没有码表，0 格。

## 二、流程（cv `seed_admit`，版本 ≥1.37）

1. 离线：`research/a24/pua_src/build_cell_codes.py` 把新图源文本层与产物页对位，出「格号→码＋当时整理本对位字」（裁定库 `src-2`，按**格号**取，不靠前后文窗口）。重切后格号变要重算。
2. 运行：`pua_code_table`（殿本开）在 vis_rulings 之前跑 `_pua_code_pass`，对每个已放行格：
   - 对位字≠记录的 `ref` → 不认（格号可能挪了）。
   - 放行字＝码表字，或在族内 → 不动。
   - 人裁格 → 不动，计 `n_code_mismatch`。
   - 单字码、放行字≠码表字（非人裁，任何通道）→ **改放码表字**，通道 `code_table`，`evidence.code_table` 记原字与原通道。
   - 族码、放行字在族外 → 降审 `src_code_conflict`（X01）。
3. 原因判定（manager `reasons.py`）：doubt `src_code_conflict` → X01，priority 5，一定人审。

## 三、参数

| 参数 | 缺省 | 含义 |
|---|---|---|
| `pua_code_table` | 关（殿本开） | 总开关 |
| `pua_code_keep_channels` | 空 | 逗号分隔的通道，这些通道放行的字不按码改（书想保留 `group_flow` 异体时用），只计 `n_code_mismatch` |
| `pua_code_family_demote` | 开 | 族外字是否降审；关＝只计数 |
| 码表 `codes` / `families` | 见 json | 码→字；族＝一码多字的族内字 |
| pua_table `verdict=multi` + `family`（或 `chars`） | | 私用码线程登记的多字码（含 daizhige 码经 `same_as` 指到的 F 码） |
| 离线 `--min-anch` / `--min-match` | 3 / 0.85 | 码→格对位的锚点数与整页相似度 |

书级策略：码表取的是**最相近的异体字**（不是原字），所以异体对（囊/𧅺、𢑴/𢑱）按码表走，不逐格再看。

## 四、benchmark

金标 `X01-benchmark-gold.tsv`（11 格：A31 看图 7 格，异体对 4 格按码表，一码多字 1 格）。脚本 cv `research/a24/pua_src/bench_code_table.py <replay.tsv>`，replay 由 `replay_code_table.py` 在 ★main 包上产出。

| 指标 | 定义 | 红线 |
|---|---|---|
| 错放 | 金标格回放后字≠金标字（族内不算） | 0 |
| 漏改 | 原放行字错、回放没改也没降审 | 0 |
| 误改 | 原放行字对、回放却改了 | 0 |
| 同码异处理 | 同一个单字码下已放行的非人裁格回放后字不一致（vol50 与 vol64 那类） | 0 |
| 仍不一致 | 全表放行字≠码表字的格 | 越小越好，交人 |

2026-11-06 殿本 r5 回放：705 格有码，改字 10（玄旁字 pua_rule 5＋异体对 4＋vol19），金标 11 格错放/漏改/误改均 0；vol69 乖（F1001 族内）正确保留。
**F1001 全书分布（回放可见 21 格）**：垂 12（pua_rule 10、human 1、match_solo 1）、埀 7（match_solo 4、human 2、iron 1）、乖 2（context）；F1055：乖 2。族内全认，没有族外字。
人裁与码表冲突 5 格（F1004 敕／勅、F1007 瓠／𤬄×2、F1015 點／㸃×2；F1001 人裁垂在族内不算）不改，计入 `n_code_mismatch`，等 A31 把 sheldon 11-05 点选结果写入人裁事件后下一轮重放消掉；回放里「原通道 None」的格是未放行格，不在指标内。

## 五、新书怎么做

1. 出码表（私用码线程）；多字码标 `multi`＋族。
2. `build_cell_codes.py` 出 `src-2`，A31 推库。
3. 册 yaml 开 `pua_code_table`；先 `replay_code_table.py` 回放，再跑 benchmark：错放／漏改／误改 0 才开。
4. 看 `pending-stats` 里 X01 与每页 `n_code_mismatch`，后者是需要人改的人裁。

## 六、第7轮的新情况：99 格全是 human_unbound（A24，2026-11-08）

**X01 现在主要不是码表冲突，而是人裁没绑上格**（doubt `human_unbound`：人裁字≠放行字、人裁又绑丢了，闸退回待审）。第7轮殿本 99 格全是这种，且 99 格里机器字都＝整理本字、人裁字却是邻格字。

**成因**：10-27 新字确认页（`H-newchar-1027-2`，151 条）按**旧页号**（页表 rev 2）落键，没有 source_rev。第7轮 A30 rebase 只补 source_rev、键不动，现格上就是别的字。另有 4 条 10-25/26 的 `~q` 迁移事件键错一格（slot ±1，官/狼/琉/喀）。锚里存着当时左右各两字 `ctx`，一核就知道键对不对。
**修法**（已做，中心库 rev 886754 起）：用 `scripts/ctx_check.py` 在 ★main 包里按 ctx＋字找到唯一位置，换键并用 `cell_anchor(新键)` 造新锚，替换 A30 rebase 文件里对应行（id 不变）。共换 141 条（99 格 X01＋42 格同样错键、没被 X01 抓到的）；复核 586 条带 ctx 的事件，键对 545，找不到 40（人裁字与包里异体不同写法，ctx 通配也对不上，没动），多处 1。
**效果**：99 格换键后 88 格现格机器字＝人裁字、4 格是异体取舍（人裁 㓂 宼 稾 間，机器 寇 寇 槀 閒，按人裁），1 格 官／宫（机器与整理本都错，人裁对）。要第8轮重跑才见 X01 99→约 0。
**以后换图源／rebase 的人裁事件**：先跑 `ctx_check.py`，`moved`＝键对不上，不能只补 rev；`none` 的人看。
