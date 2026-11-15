# collation_review：参校本对比查漏的审阅页工具

流程与口径见 `doc/02-精校/参校本对比查漏.md`。每册记录 TSV 与三方对照脚本（run.mjs、fixmove.mjs、tri.py、act.py、update.py）在 ai-team `domain/文本/参校审阅/`。

- `classify.py`：把三方对照记录分成 异体／繁简／凡例编号／改字／增删 等（判法同 book-text-util `variants --mode collate`）；脚本头部的 edges.tsv、glyph-variants.json、记录目录路径按本机改。
- `sheet_groups.py <rows.json> <outdir>`：大批量分组审阅页（`index.html`＋`data/vol<册>.json`），Artifact 发布并声明 db 能力，结果在 `decisions` 集合。
- `sheet.py <items.json> <out.html>`：少量条目、带建议与口径卡的单页版。
- `crop.py`／`zoom.py`：取书影（网站 IIIF，缓存在当前目录 `img/`）裁本列、本格；`BOOK_DEFAULT_DIR` 指向 book-text 该书的 default 目录（读 `<册>.cord.json`）。
