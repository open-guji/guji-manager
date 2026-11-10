# 设计：待审单（条目）进 KV，网站直接读

2026-11-10 A31。起因：ZM 反映 proofing-sync 发布太慢（run 42765432259，only=001：单子 1.5 分钟传完，其后约 5 分钟全站冒烟，又被别章旧缓存拦红）。

## 已做（短期，不改架构）
1. proofing-sync 带 `only` 时，冒烟只严查所指章节；别章只比单子 rev，问题只告警（kaiyuanguji-web #752）。
2. `only` 发布时 `index.json` 只改所选章，别章保持 COS 现有写法。**这是 007/008 的真问题**：旧写法下 index 按中心库全部单子生成（007=r11、008=r7），而 COS 上这两章的单子没传（仍 r10、r6），读者侧 rev 对不上，且每次 only 发布都会重现，直到下次全站发布。
3. cv `republish push --sync`（以及 edit-cell／add-alt／add-sprites 的 `--sync`）补上 `publish_only`（open-guji-cv #1372）；guji-manager 的 `guji pending --sync` 本来就带。

## 条目进 KV（11-10 已实现，sheldon 定现在就做）
现状：条目日志在中心库 `feedback/lists/pending/<书>/<章>.items.jsonl`，原先网站只读 COS `proof/<书>/<章>.pending.json`，撤下一格、加一格要「导出单 → 推库 → 触发 workflow → 传 COS → 清 CDN」。

实现（kaiyuanguji-web #753、本 PR）：
- KV key `pd:<书>:<章>` 存整张单（几十 KB）。边缘函数 `/api/pending`：GET 公开读（15 秒缓存，没有 404）；POST 管理令牌（`put` 整张单、`hide`／`unhide` 撤下放回、`delete`）。
- 精校页先读 `/api/pending`，没有或坏了退回 COS pending.json——KV 里没有内容时行为不变。
- proofing-sync 发布 COS 后把发布的单子同步写进 KV；写不进就删这章 KV（退回 COS），所以 KV 不会比 COS 旧。
- manager：`guji pending … --kv`（需环境变量 CELLREVIEW_TOKEN）= `db sync` 后把导出的整张单 put 进 KV；单里图不在 COS（HEAD 核对）、没令牌、写失败时自动退回 `--sync`。图仍是 COS 上带哈希的不可变文件。
- 取舍：没拆成「逐条写」——整张单 put 一次几十 KB，比维护条目级 KV 简单，且与 COS 同一格式，退回路径零转换。`hide`／`unhide` 接口留给不想重导整张单的场景。
- 读者侧撤下后，已加载页面的人要刷新才见（缓存 15 秒）。
