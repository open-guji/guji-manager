# 待审原因（pending_reason）

> 粗校 S3 [决策层漏斗](../迭代框架/S3-决策层漏斗.md) 按它分流；每个原因一个子文件夹，写怎么处理。

## 是什么

每个还要人看（或还没放行）的格，都标一个**主原因** `pending_reason`，回答「这一格为什么还在待审」。它是一个 enum（英文名，如 `group_abstain`），配一个分类码（如 Z01）。

- 一格只有一个主原因：按 `priority` 从小到大逐条试，第一条命中的就是。原始疑问码照旧放 `why[]` 当证据。
- 它**不是判定依据**，只说为什么停在这里；判定依据是 `why[]`、`evidence`。
- 判不出的一律写 `unknown`（X99），出现就要补规则。
- 所有数据（待审单、人裁事件、裁定库、网站票、book-text）字段名一律 `pending_reason`，值只写英文名，不写中文、不写码（sheldon 11-03 定）。
- 改名走弃用流程：yaml `renamed` 记旧名→新名，`parse()` 照认旧名；码永不复用。2026-11-06 P01 `ref_replaced`→`ref_ocr_diff`、P02 `ref_mismatch`→`ref_final_diff`。

每个原因带这些配置：大类、去向 `route`（human 一定人审／llm 大模型统一过一遍／algo 先改算法／deferred 留后）、负责人 `owner`、最终谁看 `reviewer`、网页卡片形态 `ui`、卡片说明 `hint`、判定依据 `detect`。

## 真源

| 什么 | 在哪 |
|---|---|
| enum 与全部配置 | guji-manager `guji_manager/review/pending_reasons.yaml`（唯一真源） |
| 读取接口 | `guji_manager/review/pending_reason.py`（`PendingReason`、`specs()`） |
| 判定代码 | `guji_manager/review/reasons.py`（`book_cells` → `classify` → `reasons_for_pending`） |
| 设计原文 | cv `doc/design/待审原因PendingReason.md`；ai-team `domain/CV/质检/待审原因码/` |

## 在哪里产生

1. **出单**：cv `scripts/zhengli/republish.py`／`pending_list.py` 出待审单时，对每格调 `reasons_for_pending`，写 `pending_reason`、`pending_reason_detail`（读该版产物包的 seed_admit、align_ref、glyph_match）。
2. **复审格**：换单 `proof_cycle` 里机器推翻人裁的格进复审（X03）；其余 `--recheck` 格是 X04。
3. **补单**：同字对照自检（`seg_defect --gate`）补上的格带 `src: seg_selfcheck`，原因 S04。
4. **回填**：老单、老事件用 cv `scripts/zhengli/backfill_pending_reason.py`、`backfill_event_reason.py` 补。
5. **控制台卡片**：`review/cards.py` `stamp_cards`。

## 在哪里用到

- **统计**：`guji-manager pending-stats`（线上单口径）、`iterate round-report`（每轮报告）、ai-team `domain/CV/质检/三书待审原因统计/`（三套书 ★main 包口径）。
- **分流**：`route`／`reviewer` 决定进大模型统一审（`llm_queue`）、算法、人审页还是留后；`iterate leverage` 按它排杠杆。
- **人审页与网站**：网站卡片按 `ui`、`hint` 出形态和说明（kaiyuanguji-web、guji-console 的 `pendingReasons.ts` 是副本，改 yaml 后要用 `--json` 导出同步）。
- **book-text**：待审格的 `char.json` 带 `pending_reason`，网站凭它显示字图。
- **收口单**（S4）：每类剩余格定去向（放行／留人审／算法再处理）。

## 原因一览

现状列是 2026-11-06 各册 ★main 包现算的正文页格数（四库总目 99 册、史记 10 册、全唐文 11 册）。

| 码 | 原因 | 名 | 去向 | 负责 | 四库总目 | 史记 | 全唐文 |
|---|---|---|---|---|---:|---:|---:|
| D01 | [`occluded_with_ref`](occluded_with_ref/README.md) | 有遮挡 | 先改算法，改完剩下的并入 llm | A32 | 108 | 4 | 0 |
| D02 | [`occluded_no_ref`](occluded_no_ref/README.md) | 有遮挡且参校本缺 | 一定人审 | A32 | 137 | 0 | 1 |
| H01 | [`hard_pair`](hard_pair/README.md) | 极难形近 | 留到标点、专名阶段 | A24 | 432 | 117 | 21 |
| L01 | [`lib_missing`](lib_missing/README.md) | 少见的字 | 一定人审 | A24 | 354 | 112 | 5 |
| L02 | [`lib_sparse_dissent`](lib_sparse_dissent/README.md) | 刻例太少·不一致 | 大模型统一过一遍 | A23 | 84\* | 10\* | 0\* |
| L03 | [`lib_sparse_agree`](lib_sparse_agree/README.md) | 刻例太少 | 一定人审 | A23 | 105† | 1† | 1† |
| L04 | [`lib_unrecognized`](lib_unrecognized/README.md) | 库认不出 | 先改算法，改完剩下的并入 llm | A23 | 392 | 9 | 3 |
| L05 | [`garble_gate`](garble_gate/README.md) | 像框线或墨点 | 先改算法，改完剩下的并入 llm | A24 | 184 | 52 | 2 |
| N01 | [`near_form_guard`](near_form_guard/README.md) | 形近字 | 大模型统一过一遍 | A24 | 273 | 40 | 6 |
| P01 | [`ref_ocr_diff`](ref_ocr_diff/README.md) | 识别字与参校本不同 | 大模型统一过一遍 | A24 | 174 | 77 | 30 |
| P02 | [`ref_final_diff`](ref_final_diff/README.md) | 定字与参校本不同 | 大模型统一过一遍 | A24 | 374 | 68 | 0 |
| R01 | [`ref_lacuna`](ref_lacuna/README.md) | 参校本缺字 | 先改算法，改完剩下的并入 llm | A24 | 287 | 12 | 2 |
| R02 | [`ref_gap`](ref_gap/README.md) | 参校本这里没字 | 大模型统一过一遍 | A24 | 145 | 76 | 9 |
| R03 | [`glyph_pending`](glyph_pending/README.md) | 待收字 | 留到标点、专名阶段 | A24 | 0 | 0 | 0 |
| S01 | [`seg_page_unaligned`](seg_page_unaligned/README.md) | 整页对不上 | 先改算法，改完剩下的并入 llm | A22 | 341 | 0 | 0 |
| S02 | [`seg_col_unaligned`](seg_col_unaligned/README.md) | 整列对不上 | 先改算法，改完剩下的并入 llm | A22 | 43 | 14 | 0 |
| S03 | [`col_width_out_of_band`](col_width_out_of_band/README.md) | 列宽异常 | 先改算法，改完剩下的并入 llm | A22 | 0 | 0 | 0 |
| S04 | [`seg_defect`](seg_defect/README.md) | 切坏格 | 一定人审 | A22 | 0 | 20 | 0 |
| V01 | [`variant_pair`](variant_pair/README.md) | 异体字 | 一定人审 | A24 | 260 | 122 | 2 |
| X01 | [`ruling_conflict`](ruling_conflict/README.md) | 裁定有冲突 | 一定人审 | A31 | 6 | 0 | 0 |
| X02 | [`vision_flagged`](vision_flagged/README.md) | 看图觉得不对 | 一定人审 | A31 | 0 | 0 | 0 |
| X03 | [`machine_changed`](machine_changed/README.md) | 机器改了字 | 一定人审 | A32 | 0 | 0 | 0 |
| X04 | [`recheck`](recheck/README.md) | 复审 | 一定人审 | A32 | 0 | 0 | 0 |
| X99 | [`unknown`](unknown/README.md) | 原因不明 | 一定人审 | A31 | 0 | 0 | 0 |
| Z01 | [`group_abstain`](group_abstain/README.md) | 形近字·没把握 | 大模型统一过一遍 | A24 | 525 | 103 | 11 |
| Z02 | [`group_conflict`](group_conflict/README.md) | 形近字·判法打架 | 大模型统一过一遍 | A24 | 149 | 16 | 23 |
| Z03 | [`group_demoted`](group_demoted/README.md) | 形近字·复核推翻 | 大模型统一过一遍 | A24 | 153 | 29 | 2 |
| Z04 | [`group_ref_dissent`](group_ref_dissent/README.md) | 形近字·与参校本不同 | 大模型统一过一遍 | A24 | 277 | 10 | 5 |
| Z05 | [`group_weak`](group_weak/README.md) | 形近字·证据弱（**已停用 11-06**，并入 Z01／R 类） | — | A24 | 35 | 5 | 3 |
| Z06 | [`group_form_open`](group_form_open/README.md) | 写法待定 | 先改算法，改完剩下的并入 llm | A24 | 5 | 0 | 0 |

\* L02、L03 两行接了字形库重算（L02 用四库总目 g19、史记 g6、全唐文中心库最新；L03 用三书中心库 11-06 最新 glyph.db；史记的刻例数都含借来的全唐文刻例），其余行没接字形库，所以这些格在其余行（多半是 P01、P02、L04）里也各算了一次，合计不能直接相加。L02 是 11-06 manager #258 之后的口径：参校字库里 0 例的格改判 L01（四库总目 277、史记 32、全唐文 1 格，是同一批包上 L02 改判前后之差，库用四库总目 g19、史记 g6；A24 用三书中心库最新 glyph.db 算 L01 的增量是 366、36、1，见 `tools/l01_profile.py`），这部分没加进 L01 那一行（L01 行没接字形库）（A23 11-06，见 [L02 页](lib_sparse_dissent/README.md)、[L03 页](lib_sparse_agree/README.md)）。

† L01–L03 边界 11-06 再调整（Sheldon 同意）：刻例数只算本书版本，参校字本书库 0 例的格一律归 L01。L03 行是调整后接三书中心库 11-06 glyph.db 现算的数；同一批包上 L01 再增 殿本 197、史记 22、全唐文 0，L02 史记 13→19、其余不变，L04 不动（见 [L03 页](lib_sparse_agree/README.md)）。

- 形近字组 Z01–Z06 之间怎么分、哪里重叠、新分法建议：见 [Z类梳理](Z类梳理.md)（A24 11-07）。

## 维护

- 新增或改原因：先改 `pending_reasons.yaml` 和 `reasons.py`，再在这里加或改对应子文件夹；网站、控制台副本同步。
- 每个子文件夹写：定义与判定、常见成因、怎么处理、回流与防再犯、不要做、现状。处理办法变了就改这里，不另起文档。
