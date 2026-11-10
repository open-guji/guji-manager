"""标 main 后收尾（A32，方案 `ai-team domain/CV/质检/重跑轮次/标main后自动收尾-方案.md` 第八节 8.8）。

不另建「余项表」：对不上的锚点就是**待审格**，带 `pending_reason`（add_del／anchor_miss／anchor_drift）和
`pending_reason_detail`（旧新锚、建议），自然进线上单和人审率。本包只做纯函数，不连库、不推送：

- `anchors`    auto_remap 分流项／漂移告警 → 待审格（主因、detail 格式、一格多因）
- `redlines`   红线（人裁丢失、锚点余项、程序报错／字形库 verify）
- `stats`      按册、原因码汇总（现算）
- `writeback`  dev 上机器错位锚点的自动写回（三条件）
- `remap_lib`  把 book-text 的 `remap_anchors.remap_data` 当库调用
"""
