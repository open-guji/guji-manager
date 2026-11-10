# 设计：待审单（条目）进 KV，网站直接读

2026-11-10 A31。起因：ZM 反映 proofing-sync 发布太慢（run 42765432259，only=001：单子 1.5 分钟传完，其后约 5 分钟全站冒烟，又被别章旧缓存拦红）。

## 已做（短期，不改架构）
1. proofing-sync 带 `only` 时，冒烟只严查所指章节；别章只比单子 rev，问题只告警（kaiyuanguji-web #752）。
2. `only` 发布时 `index.json` 只改所选章，别章保持 COS 现有写法。**这是 007/008 的真问题**：旧写法下 index 按中心库全部单子生成（007=r11、008=r7），而 COS 上这两章的单子没传（仍 r10、r6），读者侧 rev 对不上，且每次 only 发布都会重现，直到下次全站发布。
3. cv `republish push --sync`（以及 edit-cell／add-alt／add-sprites 的 `--sync`）补上 `publish_only`（open-guji-cv #1372）；guji-manager 的 `guji pending --sync` 本来就带。

## 中期：条目进 KV
现状：条目日志在中心库 `feedback/lists/pending/<书>/<章>.items.jsonl`，网站读的是 COS `proof/<书>/<章>.pending.json`（整张单），所以撤下一格、加一格都要「导出单 → 推库 → 触发 workflow → 传 COS → 清 CDN」。票已按条目记在 KV（`cr:i:<书>:<条目>:<voter>`）。

方案：
- KV 增 `pi:<书>:<章>:<条目id>`（条目本体：格号、图块指纹、候选、状态、图名）和 `pi-idx:<书>:<章>`（条目 id 列表＋单头 rev，小对象）。图仍走 COS 不可变雪碧图（文件名含内容哈希，一次性传好，不受 CDN 旧缓存影响）。
- 写入：manager 新增 `guji pending --kv`，经站点管理接口（沿用 FEEDBACK_ADMIN_TOKEN，web 角色）PUT 单条／整章；撤下＝改条目 status，不删；加格需先确认其图已在 COS（先传图、后写 KV，与现在「先图后 index」同序）。
- 读取：精校页 SSR 改读 `/api/pending?book=&vol=`（边缘函数，读 `pi-idx` ＋批量 get 条目，短缓存 30–60 秒）；读不到 KV 退回 COS 的 pending.json（过渡期两路并存，proofing-sync 照常发布整张单作兜底和备份）。
- 一致性：条目带 `v`（单调版本）；index 里记每条的 v，读者侧不再有「单子 rev ≠ index rev」这一类问题。
- 影响面：边缘函数新增一个读接口和一个管理写接口；SSR 一处读取点（`nextjs/src/lib/proofing.ts`）；manager 增一个推送子命令。预计 3 个 PR，约一天，不动 cv。
- 风险：KV list／get 的批量上限（单章约 30–100 条，一章一次 get index＋并发 get 条目，可接受）；整册 3900 余格同时写需分批。

## 建议
先上线 #752／#1372（解掉眼前的慢和红），用几天看 only 发布是否稳定；KV 化等 v0.2.8 晋升正式站、条目票稳定后再做，需要的话开单独 thread。是否现在就做，请 sheldon 定。
