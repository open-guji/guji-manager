# 示意图源文件

`diagrams.html` 里每个 `<div class="d" id=…>` 是一张图，id 即 `../<id>.png`。改完重截：

```js
// node shot.js（需 playwright）
const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();
const p=await b.newPage({viewport:{width:1500,height:900},deviceScaleFactor:1.5});
await p.goto('file://'+process.cwd()+'/diagrams.html');
for(const id of ['boundary','dataflow','stages','loop','gc','wikirule','pending'])
  await p.locator('#'+id).screenshot({path:'../'+id+'.png'});
await b.close()})();
```

真截图的来处（2026-11-03）：
- `pipeline-overlays.png`：`guji pipeline product overlay vol03 <步> --page 10`（殿本总目 vol03，★main 包），四张拼一行。
- `source-split-2x2.png`：`guji start source pull --book-id 96mid1ogzk --vol 03 --rev 2` 的 105–108 页按页表裁切坐标拼回原扫描。
- `triage-sheet.png`、`group-view.png`：用 vol03 的 cell_shrink 框从原图裁字块，喂 `review_triage.sheet.build` 与 `tools/开书/按组看图/build_page.py`。
- `job-ls.png`、`pack-list.png`：`guji pipeline job ls`、`guji pipeline products pack list` 的输出（去掉了连库地址那一行）。
- `web-read.png`、`web-proofing.png`：kaiyuanguji.com 阅读页、校对页。
- `case-gallery.png`：五部书各取一页 R2 原图。
- `uid-blank-cell.png`（2026-11-26）：史記 18 第 2 页原图（blob.open-guji.com 按页图 sha 取）裁第 5 列，叠身份账 `feedback/uid/18.jsonl` 里 03:19、10:49 两行的框与 u；③ 按 0.6.24 对照规则回放的结果。
