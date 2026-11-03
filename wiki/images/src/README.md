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
- `pipeline-overlays.png`：`guji product overlay vol03 <步> --page 10`（殿本总目 vol03，★main 包），四张拼一行。
- `source-split-2x2.png`：`guji source pull --book-id 96mid1ogzk --vol 03 --rev 2` 的 105–108 页按页表裁切坐标拼回原扫描。
- `triage-sheet.png`、`group-view.png`：用 vol03 的 cell_shrink 框从原图裁字块，喂 `review_triage.sheet.build` 与 `tools/开书/按组看图/build_page.py`。
- `job-ls.png`、`pack-list.png`：`guji job ls`、`guji products pack list` 的输出（去掉了连库地址那一行）。
- `web-read.png`、`web-proofing.png`：kaiyuanguji.com 阅读页、校对页。
- `case-gallery.png`：五部书各取一页 R2 原图。
