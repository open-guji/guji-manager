# 全唐文（995ejelvk0）开书脚本

全唐文册 04、05 开书时用的本机脚本（2026-10-29～31）。做法与经验见 [开书全流程](../../../doc/01-开新书/开书全流程.md) 第 S7–S11 步、[全唐文开书经验](../../../doc/01-开新书/开书经验/全唐文.md)、[案例：全唐文](../../../doc/案例/全唐文.md)。

**都是一次性工具，没进 cv、也没测试**。能抽成通用的（目录页配篇题、格位表、缩略图重绑）以后并入 cv `books/<套书>/` 或 `scripts/`（见开书全流程「缺口清单」）。

## 约定

- 选册：环境变量 `VOL`（如 `05`）。各册的目录页、正文页（按卷）和人定的目录列写在 `volcfg.py`，**新册先在这里加一项**。
- 路径：`WS`＝工作区仓（默认 `/home/user/995ejelvk0-quan-tang-wen`），产物在 `$WS/products/<册>`；中心库数据目录 `~/.guji-data/main/995ejelvk0/corpus`；`CV`＝cv 仓（默认 `/home/user/open-guji/open-guji-cv`）。
- 环境：先 `source` 一个设好 cv `.venv`、`WS`、`GUJI_WORKSPACE`、`GUJI_DATA_TOKEN`（读令牌）的 env 脚本；令牌不进仓。

## 一册的顺序（以册 05 为例）

| 步 | 做什么 | 脚本／命令 |
|---|---|---|
| 0 | 拉中心库（500 时分页小批） | `PAGE=100 python pull_small.py $WS` |
| 1 | 借殿本整库、重建 glyph.db；在 **cv 仓根目录**导入字体域 `font:jigmo`、`font:iming` | `python borrow.py $WS`；`guji glyph-db import-font --edition …` |
| 2 | 参照语料（只做一次，全书共用） | `make_grid_corpus.py <book-text Work d59f2nqla48x/default> qtw_kanripo_grid.txt` |
| 3 | 取图、写册 yaml（照册 04：`period_prior: 205`、`frame_bar_strategy: border_line`） | `guji source pull --book-id 995ejelvk0 --vol 05` |
| 4 | 首跑 Step1–4 | `guji pipeline keben_body_v2 05 --pages all --to cell_shrink --no-pack` |
| 5 | 正文页钉位：按**叶号**算（页＝卷首页＋2×(叶−1)＋b），卷首页由墨量＋看图定；Kanripo 缺的半叶不钉，卷尾 `NFKB_QTW_-…` 头要单独钉 | 手算后追加 `corpus/page_pins.jsonl`（册 05 的结果在中心库里） |
| 6 | 目录页：先对目录页跑 glyph_match，再配篇题、生成目录页参照 | `guji cache warm --pages <目录页>`；`… --from glyph_match --to glyph_match`；`VOL=05 toc_match.py`；看输出把配错的列写进 `volcfg.py` 的 `MANUAL`；`VOL=05 toc_build.py toc.txt tocpins.jsonl` → 分别追加进语料和钉位表 |
| 7 | 格位表 | `VOL=05 make_qtw_layout.py layout05.jsonl` → 追加进 `corpus/qtw_layout.jsonl`；册 yaml 加 `params.row_segment.layout_prior`、`params.align_ref.page_pins` |
| 8 | 从切分重跑到放行 | 交任务库（`base`=首跑包，`steps.from=row_segment`）；`run_vol.sh 05` 只是本机试跑时用的 |
| 9 | 核对 | `VOL=05 metrics.py`（放行率）、`cmp_kanripo.py`（列字数 vs 参照）、`draw_page.py out.png 7,54`（画框看）、`sheet.py <旗> out.png`、`sheet_ids.py ids.json out.png` |
| 批量（册06 起） | 首跑交任务库 → 取包 → 5–7 步一条命令做完 → 推库 → 交第二轮 | `VOL` 由参数给：`stageB.py 06`（自动钉位 `auto_pins.py` 出各卷目录页／正文页／卷首页写 `cfg_06.json`，`volcfg.py` 没有手配的册就读它） |
| 10 | 改切分后旧人裁失锚 | 先把快审 HTML 里嵌的字块解到 `/tmp/claude/fakegs`，再 `VOL=04 thumb_rebind.py out.json` |

## 文件

| 文件 | 用途 |
|---|---|
| `volcfg.py` | 各册目录页／正文页范围、人定目录列；读钉位表（按册过滤）和语料 |
| `make_grid_corpus.py` | Kanripo → 带半叶头 `#@` 的逐列语料 |
| `toc_match.py`、`toc_build.py` | 目录页：每列识别串配本卷篇题 → 目录页参照段＋钉位行 |
| `make_qtw_layout.py` | 逐列格位表：去版框横线、印章、空列等假字，列与参照行 DP 对齐 |
| `auto_pins.py` | 自动钉位：识别串配 Kanripo 半叶、每卷多数票定卷首页、按叶号推；顺带判目录页 |
| `stageB.py` | 一册首跑包上：自动钉位 → 目录页参照 → 格位表 → 改册 yaml（路径写死在本机，搬用先改头几行） |
| `run_vol.sh` | 一册从切分重跑到放行（本机试跑用；正式跑交任务库） |
| `metrics.py`、`cmp_kanripo.py`、`draw_page.py`、`sheet.py`、`sheet_ids.py` | 核对与看图 |
| `thumb_rebind.py` | 用快审页里的缩略字块把旧人裁重绑到新切分的格 |
| `borrow.py`、`pull_small.py` | 借库重建 glyph.db；分页拉中心库 |

册 04 时试过但没用上的两个脚本（降低整列顺移门槛、用快审缩略图走 backfill_anchors）没收进来，记录在开书经验 S11。
