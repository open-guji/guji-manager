# -*- coding: utf-8 -*-
"""``guji start new``：新书仓一次出齐初始文件（2026-11-27，GM1，MBJ／WYG 开书经验）。

    guji start new <书id> --title <书名（版本）> [-w <书仓目录>] [--work-id <Work ID>] [--ws-repo guji-workspace/<仓名>]
                         [--project <所属项目>] [--force] [--dry-run]

之前开新书是照上一本（全唐文、史記）手抄 `workspace.yaml`、`.gitignore`、README、`开书进度.yaml`，两本书抄出来的文件集合都不一样。
本命令把这些骨架一次写进书仓目录（缺省当前目录）：

    workspace.yaml        id＝book ID（2026-10-30 规矩），glyph_lib 注释位
    .gitignore            可再生的不进 git（含 _packs/、reports/、perf/）
    README.md             书目信息表、目录、新会话怎么起
    开书进度.yaml         开书流程当前状态（1a／1b／1c 各步 pending），会话换了读这份续上
    开书经验.md           随做随记
    layout_profile.yaml   版式档案骨架（只写事实）
    实验记录/README.md    实验记录索引
    日志.md               逐日日志
    tools/                书仓自带小工具放这里

已有的文件不覆盖（`--force` 才覆盖）。不建仓（建仓走 ai-team `process/repo_create.py`），不提交、不推，
不写中心库（册 yaml 与 `guji db init` 见 wiki 新书启动）。
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

BOOK_ID_RE = re.compile(r"^[0-9a-z]{10}$")

GITIGNORE = """\
# 可再生的不进 git；人产出的在中心库（guji db），原图在 R2（guji source pull）。
# 路径相对本书目录。gitignore 不认行尾注释，注释只能单独成行。

# 原图：R2 页表 <书id>/<册>，`guji source pull <册> -w <本目录>` 取
data_full/
# 产物、缓存、派生库
output/
products/
products_snap/
products_r*/
cache/
binarized/
_packs/
__pycache__/
*.pyc
# 出单、导出等报告（可由产物包重出；要留的拷进 实验记录/）
reports/
# 本机耗时记录
perf/
"""

WORKSPACE = """\
# 控制台 URL 上露出来的工作区 id（`/<ws>/<book>/step/...`）。工作区 id＝book ID（2026-10-30 规矩）。
id: {book_id}

# 字形库借用（新书字库为空时先猜同族；实测等 1c 首批人审后再做，见 wiki 借库写法）。
# glyph_lib:
#   borrow:
#     - {{from: <借库书 id>, scope: human+auto}}
"""

PROGRESS = """\
# 开书进度：本书开书流程的唯一当前状态（格式见 guji-manager 开书全流程）。会话换了读这份续上。
book_id: {book_id}
work_id: {work_id}
title: {title}
ws_repo: {ws_repo}
project: {project}
goal: v0.1
vols: {{total: null, registered: "", pages: null}}
source:
  root: commons            # commons | ia | 其他；云会话连 Commons 429 时见 wiki 新书启动-常见坑
  files: []
  pages: []
  chosen_by:
  chosen_on:
  note: ""
reference: {{source: "", file: "", line_is_column: null, reference_trust: null, accuracy: "", decided_by: null, on: null}}
steps:
  1a:
    book_index: {{status: pending}}
    ws_repo: {{status: done, on: {today}, note: "guji start new 生成初始文件"}}
    commons_sha1: {{status: pending}}
    source_register: {{status: pending}}
    cos_tier: {{status: pending, note: "guji start source cos-tier；cos-check IoU≥0.9"}}
    reference: {{status: pending}}
    db_init: {{status: pending, note: "要先有 books/<册>.yaml；db init 时写好 glyph_store/meta.jsonl 的 book_edition"}}
  1b:
    layout: {{status: pending, file: layout_profile.yaml}}
    page_kinds: {{status: pending}}
    row_layout: {{status: pending, note: "按页行款：expected_cols_pages 与每列字数（chars_per_line_pages）都核，列数字数各抽页叠图看"}}
    dev_set: {{status: pending}}
    checkup: {{status: pending, note: "合格标准见 wiki 开书体检；用户定目标人审率"}}
  1c:
    first_run: {{status: pending}}
    glyph_review: {{status: pending}}
    book_text_entry: {{status: pending, note: "首次出包前建 book-text 条目骨架（Book/<id 末三位>/<id>/manifest.json、default/index.json），再 u_migrate、uid init；见 wiki 新书启动-常见坑"}}
"""

README = """\
# {book_id} {title}

| | |
|---|---|
| book-index 条目 | [`{book_id}`](https://www.kaiyuanguji.com/book-index?id={book_id}) |
| 作品 Work | `{work_id}` |
| 底本 | （待填：馆藏、扫描来源、册数页数、sha1 见 book-index 条目） |
| 册 | （待填：册号与源件对应关系） |
| 工作区 id | `{book_id}`（`workspace.yaml`，同 book ID） |
| 所属项目 | {project} |

{today} 开档（`guji start new`）。
仓根即工作区，`guji … -w <本仓克隆目录>`。册配置、语料、人裁等数据在中心库，不进本仓。
开书步骤见 guji-manager `doc/1-新书启动`。

## 新会话怎么起

1. 读 `开书进度.yaml`（当前状态）、`开书经验.md`（踩过的坑）、`日志.md` 末尾。
2. 环境装配与令牌见 guji-manager `doc/00-总览/环境与令牌.md`；云会话取源件连不上 Commons 时见 wiki 新书启动-常见坑。
3. 从 `开书进度.yaml` 里第一个 `pending` 的步骤接着做，做完改状态再推。

## 目录

| 路径 | 内容 | git |
|---|---|---|
| `data_full/<册>/` | 原图 `<页>.png`，R2 取 | 不进 |
| `products/`、`output/`、`cache/`、`_packs/` | 产物、派生库 | 不进 |
| `reports/`、`perf/` | 报告、耗时（可重出） | 不进 |
| `开书进度.yaml` | 开书流程当前状态 | 进 |
| `开书经验.md` | 随做随记，成熟后并进 guji-manager `doc/案例/开书经验/` | 进 |
| `layout_profile.yaml` | 版式档案 | 进 |
| `实验记录/` | 每步实验一份记录 | 进 |
| `日志.md` | 逐日日志 | 进 |
| `tools/` | 本书自带小工具（参校本清理、拆页等） | 进 |
"""

EXPERIENCE = """\
# {title} 开书经验（随做随记）

> 按 guji-manager `doc/1-新书启动` 走。每条：日期 · 步骤 · 经验 · 对后续书的建议。整理成熟后并进 guji-manager `doc/案例/开书经验/`。

## 1a 元数据与资源

## 1b 页面分析与参数

## 1c 选页试运行
"""

LAYOUT = """\
# {title}（{book_id}）版式档案：这本书「长什么样」，只写事实不写开关。试跑叠图后再改。
layout_profile:
  script:                       # 刻本 | 写本 | 抄本 | 石印 …
  image:                        # 一图一半叶 | 合扫对开 …
  grid:                         # fixed（有界行格）| free
  slots_per_col:                # 每列字数；变动写 null 并在下面说明
  cols_per_page:
  frame:                        # 四周單邊 | 左右雙邊 …
  banxin:
  jiazhu:                       # 有无双行小注、占比
  big_char_pages:               # 序文等大字页：页范围、列数、每列字数（按页行款要核列数与字数）
  toc:
  page_kinds: [cover, body]
  reference:                    # 参校本来源、是否 OCR 稿
  seg_set:
"""

EXP_README = """\
# 实验记录

开书与整理过程中每一步的记录：做了什么、参数、数字、结论、谁定的。按日期命名，一步一份。

| 日期 | 记录 |
|---|---|
"""

LOG = """\
# {title} 整理日志

> 按日期倒序。格式：做了什么／命令与版本／数字／卡点与解法。通用经验另写进 `开书经验.md`。

## {today}
- `guji start new` 生成初始文件。
"""


def files_for(book_id: str, title: str, work_id: str, ws_repo: str, project: str, today: str) -> dict[str, str]:
    kw = dict(book_id=book_id, title=title, work_id=work_id or "（待填）", ws_repo=ws_repo or "（待填）",
              project=project or "（待填）", today=today)
    return {
        "workspace.yaml": WORKSPACE.format(**kw),
        ".gitignore": GITIGNORE,
        "README.md": README.format(**kw),
        "开书进度.yaml": PROGRESS.format(**kw),
        "开书经验.md": EXPERIENCE.format(**kw),
        "layout_profile.yaml": LAYOUT.format(**kw),
        "实验记录/README.md": EXP_README,
        "日志.md": LOG.format(**kw),
        "tools/.gitkeep": "",
    }


def cmd_new(args) -> int:
    book_id = args.book_id
    if not BOOK_ID_RE.match(book_id):
        print(f"✗ 书 ID {book_id!r} 不像 book ID（10 位小写字母数字）", file=sys.stderr)
        return 2
    ws = Path(args.workspace or ".").expanduser().resolve()
    ws.mkdir(parents=True, exist_ok=True)
    out = files_for(book_id, args.title, args.work_id or "", args.ws_repo or "", args.project or "",
                    date.today().isoformat())
    wrote, skipped = [], []
    for rel, text in out.items():
        p = ws / rel
        if p.exists() and not args.force:
            skipped.append(rel)
            continue
        wrote.append(rel)
        if args.dry_run:
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    tag = "（dry-run，未写）" if args.dry_run else ""
    print(f"书仓 {ws}{tag}")
    for r in wrote:
        print(f"  + {r}")
    for r in skipped:
        print(f"  = {r}（已有，未覆盖；--force 覆盖）")
    print("下一步：补 README 底本与册表、开书进度.yaml 的 source；"
          "git add -A && git commit && git push；然后 guji start source … 登记原图，"
          "写 books/<册>.yaml 后 guji db init。书级代码 code/ 与 k1 见 guji code release。")
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("new", help="[v2] 新书仓一次出齐初始文件（workspace.yaml、.gitignore、README、开书进度.yaml…）")
    p.add_argument("book_id", help="book ID（10 位）")
    p.add_argument("--title", required=True, help="书名（版本），如 朱楓林集（明萬曆四十四年歙邑朱氏刻本）")
    p.add_argument("-w", "--workspace", default=None, help="书仓目录（缺省当前目录）")
    p.add_argument("--work-id", default="", help="Work ID")
    p.add_argument("--ws-repo", default="", help="如 guji-workspace/<书id>-<拼音>")
    p.add_argument("--project", default="", help="所属项目")
    p.add_argument("--force", action="store_true", help="覆盖已有文件")
    p.add_argument("--dry-run", action="store_true", help="只列要写的文件")


def _cmd(args) -> None:
    sys.exit(cmd_new(args))


COMMANDS = {"new": (add_parser, _cmd)}
