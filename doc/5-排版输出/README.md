# 第五步　排版输出（output）

把产物（★main 包或本地 `products/`）导出成排版文本和对勘报告。全部只读产物，不改产物、不进指纹。
cv 原 Step9 移来：2026-11-22 定归本步，11-23 代码整个搬进本包 `guji_manager/output/`（cv v0.9.0 起删掉）。
怎么做见 Wiki [第五步-排版输出](../../wiki/第五步-排版输出.md)。

| 命令 | 输入 | 输出 | 模块 |
|---|---|---|---|
| `guji output export md <册>` | 有 seed_admit 产物的页 | `reports/<册>/<册>.md` 逐列文本 | `output/markdown.py` |
| `guji output export format <册>` | 同上；meta、拆页表 | `lines.md`、`pages.json`、`norm.json`（加 `--format char-cord` 出 char 格式） | `output/guji_format_export.py` |
| `guji output export wikisource <书> -w <工作区>` | 产物，或 `--md` 手改稿 | `reports/<书>/wikisource/` 逐页 wikitext | `output/wikisource_export.py` |
| `guji output export reflow <md> --out …` | 分行 md | 段落 md（可加 LLM 标点） | `output/reflow.py` |
| `guji output collation-report --book <册>` | 产物、整理本 | `reports/book/collation_<册>.html` | `output/collation_report.py` |

缺省口径：

- 页范围 `--pages all`，没有 seed_admit 产物的页跳过并提示。
- `format` 的章号按册号推（推不出给 `--chapter`）；meta 缺省 cv 仓 `doc/formats/samples/guji_format_v0.1/meta_<册>.json`，拆页表缺省四庫 `split_table_siku.json`。格式规格在 cv `doc/formats/`。
- 其余参数写在册 id 之后，原样交给模块；`python -m guji_manager.output.<模块> -h` 看全部参数。

其他模块：`output/collate.py`（逐页对勘）、`collation_grade.py`（对勘分级）、`same_char.py`、`absent.py`、`tiers.py`（异体分层）、`strips.py`（差异条图）、`guji_page_export.py`、`char_cord_report.py`。
留在 cv 的：`report/slots.py`、`report/witness.py`（管线的对位与放行要用）。
