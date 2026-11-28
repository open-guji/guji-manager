# 设计：manager 各处改挂字格永久编号 u（T2）

> 字格永久编号 u 工作包 T2（CV0 牵头，2026-11-24 Sheldon 定「同意用 u」）。
> 总方案：https://claude.ai/artifact/NksDge9ZxaEyebAgnS8s8Q ；设计：https://claude.ai/artifact/FdKWkGBkNVyQbVFPugFMtJ ；
> 格式规范 guji-format PR #34（char v0.6、punct／entity v0.4、norm v0.3）。
> 依赖 T1「字格身份账」（`guji_manager/uid/`，`cell_ref()` 改查账）。本文是 T2 的摸底与改动清单。

## 一、口径（和 T1、T3 对齐过）

- **u**：册内唯一正整数，发了不改不复用。账在 `<feedback>/uid/<册>.jsonl`（T1）。
- **`cell_ref(cell_id)`**（T1 定签名）：册**有账**→ 返回 `int` u，查不到报 `UidMissing`（不回退格号）；册**没账**→ 恒等返回格号字符串。
  `cell_of(ref, book)`：int → 当前格号。`is_uid(ref)`。批量用 `uid.ledger.Ledger.load(book)`。
- **格号照写、身份以 u 为准**（原「只加不改」双写期 11-24～11-25 已结束）：格号（`cell`、`target.key`、`a`）照写方便人读；册有账的写入一律带 u，写不出整批报错（`u_stamp`，#932 起）；读的时候册有账而没带 u 的旧记录不再按格号作数（`current_cell` 返回 None，11-25 收口）。没账的册行为与以前逐字节相同。
- **裁定**：`payload.u`（int）。cv `RulingStore` 按 (group, 册, payload.u) 建索引（T3），册取 `payload.cell` 冒号前缀。
- **裁定事件**：`target.anchor.u`（int）。`EventTarget` 是 cv 的 pydantic 模型，多余字段会被丢，故放进自由字典 `anchor`，不改 cv。
- **待审条目**：条目加 `u`；单上每格（`pending.json` 的 `cells[]`）多带 `u`。
- **book-text**：char 每格 `u`，顶层 `u_max`、`u_retired`；norm 条目加 `u`。

## 二、改动清单

### 1. 统一盖 u（新模块 `guji_manager/u_stamp.py`）

| 函数 | 做什么 |
|---|---|
| `stamp_rulings(evs)` | `kind=ctx_ruling` 且 `payload.cell` 是完整格号的事件，册有账就写 `payload.u`；同一批按册缓存 Ledger |
| `stamp_human(evs)` | `unit=cell` 的裁定事件，册有账就写 `target.anchor["u"]` |
| `u_map(book)` | `{格号(去册前缀): u}`，没账返回 `None`；给待审单、导出、票批量用 |

有账但查不到格 → 报错并提示「先 `guji uid advance <册>`」，不写半截（设计「入账漏了」一条）。

挂点（都在 append 之前）：

| 写入路径 | 文件 | 改法 |
|---|---|---|
| 文意裁定按格写 | `ctx_ruling.py` `append_or_exit` | 先 `stamp_rulings` |
| 裁定换键 rekey | `ruling_hits.py` `rekey_vis` | 走 `append_or_exit`，已覆盖 |
| 看图审 | `review/vis_review.py` | 走 `ruling_write.append_rulings`，在它里面盖 |
| 锚点回填 | `ruling_anchor.py` | 同上 |
| swap 同迁裁定 | `swap/rulings_migrate.py` | 同上；迁移事件的 u 取**新格**的 u（继承了就等于旧 u） |
| 终审 | `final_review/__main__.py` | 直接 `log.append` → 改走 `append_rulings` |
| collect 改版重键 | `collect.py` `write_rekeys` | 经 cv `RulingStore.put`，等 T3 给 `put` 加 `u=` 关键字；没有就 manager 自己拼事件 |
| 人裁（控制台、cellvotes write） | `review/event_write.py` `write_events` | `enrich_events` 之后 `stamp_human` |
| 补锚回填 | `ops/lib_backfill.py` | `enrich_events` 之后 `stamp_human` |

### 2. 核对按 u（`rulings-hits`）

`ruling_hits._rulings_by_cell*`：裁定带 `u` 且册有账时，用 `cell_of(u)` 得到**当前**格号再对产物；没 u 的照旧按 `cell`。
报告加一列「挂法」（u／格号），便于看迁移进度。

### 3. 待审单（`review/pending_items.py`）

- 条目加 `u`（开条目时写；reconcile 时补缺）。
- `reconcile(..., us=None)`：调用方给 `{格号: u}`（`u_map`）。认条目的次序改为 **u → 指纹 → 格号**；
  按 u 认上而格号变了，照旧记 `move`。
- `export_sheet`：每格多带 `u`（网站 T5 读）。
- 调用方（出单 `pending_list`、`land`、swap 收尾）传 `us=u_map(book)`。

### 4. 网站票（`cli_cellvotes.py`、`feedback/web_votes.py`、`feedback/web_inbox.py`）

- 票带 `u`（T5 网站写进 D1 的可空列）：`latest_votes`／`triage` 分组键改为 **u 优先**，没 u 用 `a`。
- 有 u 的票：用 `cell_of(u)` 得当前格号，**不再**做 cord 框比对（u 本身就是身份）；u 在 `u_retired` 里 → 挂起，`kind=moved`，理由「格已并掉／删掉」。
- 没 u 的旧票（含旧 rev 票）：照旧 cord 框比对（`check_cell`），过了再 `cell_ref` 得 u 写进事件。
- `latest_human` 增加按 u 的索引（裁定事件 `anchor.u`），旧事件没 u 的按格号。

### 5. swap 与换图源工具读账

- 新函数 `uid` 侧（T1 的 ledger）出「旧切分→新切分」行，格式与 `swap/booktext.cell_table` 相同（`old new oc nc kind iou`）。
  `swap/booktext.remap_in_repo`：册有账且新旧两版 char 都带 u 时，**按 u 对应**出表，不再跑 IoU；否则照旧。
- `feedback/cell_migrate.py`、`ops/cell_rekey.py`：先跑 `guji uid table <册> -o 表.tsv`（`u_table.py`，按账上每页「上一份→当前一份」切分、
  同 u 即同格），出同格式的格级对照表（`旧格 新格 旧字 新字 类别 IoU 说明`），再照旧交给这两个工具，下游逻辑不动。
- `swap/booktext.cell_table`：新旧两版 char 都带 u 时按 u 对（`cell_table_by_u`），不跑框配对。
- 标点专名：char 带 u 后，`remap_anchors` 由 T4（book-text）改成按 u 挂；swap 这边只保证新 char 里 u 对。

### 6. book-text 导出（`formats/guji_char_cord.py`、`output/guji_format_export.py`）

- `from_pages_json(..., uids=None)`：`uids` 是 `{(页, cv 格号): u}` 加 `u_max`、`u_retired`。给了就每格写 `u`（插图块占掉的格不写），
  顶层写 `u_max`、`u_retired`，`$schema` 升 char v0.6；任一格没 u 报错。没给＝现在的输出逐字节相同。
- norm 条目按 `a` 查 u 加 `u`。
- `guji_format_export` 加 `--uid`（或册有账自动带）。
- 本仓抄一份 `formats/guji_char_v0.6.schema.json`（从 guji-format PR #34）。

### 7. 存量迁移脚本（只出提案和清单，不写中心库）

`guji uid migrate-plan <册> --out <目录>`：

| 输出 | 内容 |
|---|---|
| `rulings.jsonl` | 要追加的裁定事件草稿（原 payload ＋ `u` ＋ `migrated_to_u`）。裁定已回填 cells_sha 且＝账上该页 cells_sha 的直接迁；其余走宽松证明（前后 2 字一侧同＋字在候选），证明不了的进清单 |
| `human.jsonl` | 裁定事件补 `anchor.u` 的草稿（不改原行，新事件 `~u` 后缀，后到覆盖） |
| `pending.jsonl` | 待审条目补 `u` 的新版本行 |
| `votes.tsv` | 票 → u 对照（给 T5 回填 D1 可空列用） |
| `清单.tsv` | 没迁的：每行 类别、键、理由 |
| `守恒.json` | 迁前、迁出、没迁三数，`迁前 = 迁出 + 没迁` 对不上就抛错 |

真写（追加事件、推库）放在试点那一步，由主导线程问过 Sheldon 再做。

## 二½、落地记录

- 第一批 #921（11-24）：§二.1、.3、.6 的 `from_pages_json(uids=…)`。
- 第二批（11-25，T1 #923 合后）：`u_stamp` 改用账批量查、`export_uids`、`current_cell`；导出命令有账自动带 u（`--no-uid` 关）；
  collect 重键经 cv `RulingStore.put(u=…)`（cv #1848 起，旧 cv 不带）；rulings-hits 等按 u 跟到现格（`_follow_u`，作废的 u 不再作数）；
  网页票 `latest_votes`／`triage`／`latest_human` 按 u（带 u 的旧 rev 票也收，按 u 认的不再对框）；`guji uid table`；swap 按 u 出表；
  `guji uid migrate-plan`（`u_migrate.py`）。与 §二.7 的出入：宽松证明 manager 拿不到候选，改为「两侧 2 字都同」（页首页尾只比有字的一侧）；
  人裁按框 IoU≥0.5（没框只在该页没重切过时按格号）；票不在这里迁（网站 D1 的 u 列由 T5 按 `guji uid table`／现行账回填）。
- 试点调口径（11-25，#925）：窗口按本书归一表比，「两侧同」或「一侧同且裁定字＝账上字」；没记窗口的进清单；
  人裁改为「人裁字＝账上字」（`anchor.bbox` 是右上原点、图源换过，不比框）；加 `--write` 只追加（`~u` 抄件，ts、seq 不变）。

- 收口（11-25，主导线程「u 彻底收尾」）：`guji uid migrate-plan --close`（`u_migrate.rescue_human`／`close_out`／`write_close`）。
  清单上的人裁再救：⑤ 异体同（cv `variant_group` 高置信异体，如 愼／慎）、⑥ 列内近邻同字（同页同列前后 3 格内唯一同字，切分挪过一两格、九月旧格号都靠这条）；
  其余：裁定一律作废（窗口变了，要时文意重跑重判；旧提示词版本 seed_admit 本来不认）、没字且重切过的人裁作废、格号不在账且近邻无同字的人裁作废、
  字不同的人裁这格已有带 u 人裁就作废否则转待审条目（`pending_reason=recheck`、`src=script:u-closeout`）、格号不在账的待审条目撤下。
  作废**不删原事件**，记进 `feedback/lists/u_void/<册>.jsonl`（每行 `kind=u_void`，转待审的记 `kind=u_review`；重跑按 (stream, id, key) 去重）。
  读路径同时收紧：`current_cell` 对有账册里没 u 的记录返回 None（`latest_human`、`rulings-hits` 不再按格号认它们）；各写入点由「盖得上就盖」改为 `stamp_strict`（盖不上整批报错）。

- 之后（11-25–26，PATCH）：0.6.17 部分副本 `--only` 推账；0.6.18 `~u` 抄件补锚档（`guji uid anchor-fill`）；0.6.19 同包重标 main 记「已对过」、`check-u-report` 定时只报；
  0.6.20／0.6.21 导出器配老 cv、`u_retired` 的 into 目标不在本章降 gone；0.6.22 swap R1 闸放过已作废格刻例；
  0.6.23 导出保 u 连续（对照 book-text 现行 char，旧版有、本次没导出的 u 记 gone）；0.6.24 入账时有字旧格不配给空格（空格＝字块无墨）。
  全部用法与报错对照见 [字格身份账](../参考/字格身份账.md) 第七、九、十一节。

## 三、测试（先写，T1 合前用假账跑）

- `tests/test_u_stamp.py`：有账盖 u、没账不动、有账缺格报错；人裁 `anchor.u`；同批多册。
- `tests/test_pending_items_u.py`：reconcile 按 u 认（格号挪了、指纹也变了仍认上）；没 `us` 时与现在一致。
- `tests/test_web_votes_u.py`：票按 u 分组；u 退役挂起；旧票照走框比对。
- `tests/test_char_export_u.py`：`uids` 给了每格带 u、`u_max`；不给逐字节同；缺 u 报错；过 v0.6 schema。
- `tests/test_uid_migrate_plan.py`：守恒、直接迁／宽松迁／清单三类。
- 回归：全量 `pytest tests`（没账的册行为不变）。

## 四、影响与分级

- 不改 cv 产物、不改 code_hash、不改指纹；没账的册行为不变 → L0。
- 有账的册（试点 vol31、vol28 起）：裁定、裁定事件、待审条目多一个字段；cv 侧要开 `ruling_by_u`（T3）才用到。
- book-text：有账的册导出升 char v0.6（u、u_max、u_retired），体积约 +20%（殿本实测）。
