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
