# 点校先于精校：段输入、校验、回填、转线脚本（全唐文册04试跑，2026-11-08）

流程见 `wiki/文意与知识/点校先于精校.md`；试跑数据与结论见 ai-team 或 A31 项目文件 `点校先于精校/全唐文册04试跑/`。

| 脚本 | 作用 |
|---|---|
| `build_segments_v2.py` | 按册出段（≤约1,800字，段前后各2列只读上下文 ◁▷，疑问格写成 `〔n:候选|…〕`，不带机器字；列缩进、列未满 ⏎ 作版面线索）；产 `.txt/.base.txt/.cells.json/.idx.json` |
| `prompt_A.md`／`prompt_B.md` | A 路（判字＋标点分段分卷＋专名，正序）／B 路（只判字，倒序）提示词，`{SEG}` `{OUT}` 为占位 |
| `check_out.py` | 校验 A 路输出：汉字流＝机器字＋所判字，字在候选内，标签成对（`OUTDIR=… check_out.py SEGDIR 名 A`） |
| `repair.py` | 汉字流不符时只做单字替换的确定性修复，日志写进 `*.A.fixed.json` |
| `to_answers.py` | A/B 两路 high 同字 → `llm_queue import` 用答案行（放行子集；写库前须金标 0 错） |
| `to_punct.py` | A 路 text → punct.json／entity.json 草稿（`pre_char`、实体 text 取现行文本字，不取所判字；专名全 new_candidate） |

已知：模型会无声归一写法（絕/絶、茲/兹）、偶尔多/少一字，所以必须过 `check_out.py` 与 `repair.py`；段首接上一页句中时须带上下文，否则会凭空添字。

## 待收（ZM 11-23 建议，GM3 评估通过）
- 异体闸：variants 表（`config/variants/variants.json`＋`dicts/variants.tsv` 建对称表）＋「AI 字须等于机器首选或参校字」两道硬闸，规则见 wiki「文意判字标点专名合并判定」8.2 第 3a 条；脚本请 ZM 入库（`variant_gate.py`）。
- 写裁定脚本（`write_go.py`／`write_ctx_ruling_by_cell.py`）：RulingLog 须传 feedback 根（不是 feedback/rulings）；`key_windows` 第一个参数是含各册目录的产物根。

## write_go.py、vpairs.json（ZM 殿本 11-23，GM3 收入）
- `write_go.py`：把文意判放行的格按管线键窗口写成 ctx 裁定。内含硬编码路径（产物根、feedback 根、`go_keep.tsv`），**是示例，用前要改路径**；改成传 feedback 根后没再跑过，首次先不加 `--apply`。两个坑见文件头：`RulingLog` 传 feedback 根、`key_windows` 传含各册目录的产物根。
- `vpairs.json`：异体对对称表（来自 guji-runner `config/variants/variants.json` 的 `directed` 与 `config/dicts/variants.tsv`，对称化、不传递，约 83k 对），供异体闸第②条用；生僻字（如 𲍠／鵓）表里没有。全唐文 11-23 复核另发现缺 䕶↔護、蹖↔踳、巿↔市，已转 CV4 评估补表。闸规则见 Wiki「文意判字标点专名合并判定」8.2 第 3a 条。

> 更正（CV4 11-23，open-guji-cv#1811）：`vpairs.json` 是快照，不含 `variants.pairkind.tsv` 的 V 行；新用法优先 `open_guji_cv.variants.are_variants`。䕶→護、蹖→踳（chǔn 义）已进 cv 异体表；巿／市 是形近不同义（C），不进异体表，靠闸①与看图。

## confuse_guard.py（易混字守卫，11-24）
AI 判出的字属易混对（十千、于干、七十、未末、己已巳、日曰、戊戌戍等，表可扩），且候选含另一方 → 不放行，交 B 路／看图。与异体闸并列用，三书通用。来源：史记册29–38 单路放行 53 格看图出 1 真错（37:27:5:16a 十/千）。

## 11-25 起按字格永久编号 u（CV0 切换完成，不双写）
- `write_go.py`：裁定 payload 带 `u`（`cell_ref(格号)`；没启用 u 的册不写）；cv 书级开关 `seed_admit.ruling_by_u` 已开（殿本、史記、全唐文），按（组，册，u）查裁定。
- `to_punct.py`：新增第 6 个参数 `UMAP.json`（`{格位key: u}`，从该册 char.json 每格的 `a`、`u` 取）；给了就写 punct/entity **v0.4**：punct 条带 `u`、不写 `char_offset`；entity 带 `u_start`／`u_end`、不写 `span`；UMAP 里找不到的格位直接退出。不给才按旧格式（只有旧册用）。
- `migrate_v03.py`：v0.3 一行一条的迁移已由 CV0 在 dev 完成；脚本留作参考，不再用于新迁移。
- 改字：用 book-text 的改字工具（会发 `u＝u_max+1`），不要手改 char 的格数。


## write_notes.py（GM3 11-26）
AI 分析摘要（浅层、深搜、放行与不确定都写）TSV → `feedback/notes/<册>.jsonl`，按（册，u）挂；出单时 `dian_attach` 挂到待审单。格式与用法见脚本头与 wiki「文意判字标点专名合并判定」第十二节。
