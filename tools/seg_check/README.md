# seg_check：切分核查一条命令

输入一轮出包（产物根＋列图／字块缓存），输出切分类问题列清单、需看图的整列缩略图和报告。用法、判据、处置分类与 r41 结果见 [doc/01-粗校/切分快筛.md](../../doc/01-粗校/切分快筛.md) 第九至十一节。

```
python tools/seg_check/seg_check.py --products <产物根> --cache <缓存根> --vols 01,02 \
    --pins <manual-cells items.jsonl> --layout <layout_slots.jsonl> --skip <册:页,…> --out <报告目录>
```

| 文件 | 作用 |
|---|---|
| `seg_check.py` | 总入口：调下面两步，再做钉子核对、版式对格号、待审原因码归类，汇总成 `列清单.tsv`、`需看图_*.png`、`report.md` |
| `seg_detect.py` | 逐格 flags（FOR/Fend/Fpatch/Lh/Lv/JZW） |
| `orphan.py` | 漏切块（整块墨不在任何格框里） |
| `ctx2.py`、`frame_end.py`、`segqc.py` | 上两步用的墨账、列端框线、字块边线判据 |

只读产物与缓存，不改中心库。依赖 cv2、numpy、PIL；原因码归类要能 import `guji_manager`。
