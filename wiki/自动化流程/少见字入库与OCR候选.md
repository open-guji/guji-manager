# 2c 少见字入库、OCR 候选

> 属于 [第二步 自动化流程](第二步-自动化流程)。

库里缺例、样本少的字头补上本书刻例，让库自己能放；认不出的字由 OCR、5b 笔画证据出候选供人认。

**输入**：待审里 L 类（`lib_missing`、`lib_sparse_*`、`lib_unrecognized` 等）的格；整册跑完后放行格回库的候选。
**输出**：新的字形库快照 `g<N>` 并钉住；少见字四层人审页的结果；回库与库文一致报告。
**命令**：`guji pipeline review-pages build char_grid`、`tools/开书/字形快速入库_自动.py scan／ocr／crop／sample／gate／admit`、`guji pipeline events route`、`guji pipeline glyph-db snapshot／snapshot-upload／pin-verify／selfcheck`、`guji pipeline recheck`、`guji pipeline triage`、`guji feedback audit alt`、`guji start corpus`。

做法以 [迭代流程 第 2 层](迭代流程#第-2-层少见字入库) 与 [字形快速入库](字形快速入库)（真源）为准。第一次进库的字必须人裁（11-03 定）；每批新册集中出一次页，不零碎出。OCR 候选：认不出的字先看 5b 两路（分类头、embedding 检索）的候选，见 [5b 笔画证据](https://github.com/open-guji/guji-manager/blob/dev/doc/参考/5b笔画证据.md)；以图代字、私用码见 [无法识别字](https://github.com/open-guji/guji-manager/blob/dev/doc/参考/无法识别字.md)。

## 相关页面

- [字形快速入库](字形快速入库)：四层页：快速审阅单 → 高置信 → 低置信 → 难认字（真源）
- [快审减量](快审减量)：参校本对上字、还没放行的格先按位置和字跳过，再分流
- [放行格回库](放行格回库)：机器已放行、库里缺例的字自动补回库
- [回库事后核](回库事后核)：回库的少见字抢常用字库首位的事后核
- [库文一致](库文一致)：字形库标签与文本逐格核对
- [无法识别字](https://github.com/open-guji/guji-manager/blob/dev/doc/参考/无法识别字.md)：图上是什么、用什么码：以图代字、私用码、〓
