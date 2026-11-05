"""降人审迭代框架的验收与报告工具（A31，2026-11-05）。

设计依据：ai-team `domain/CV/质检/迭代降人审框架/新书降人审迭代框架-2026-11-05.md` 第十一节 T3/T6/T7/T8/T9；
执行版 `doc/01-粗校/降人审迭代框架.md`、`doc/01-粗校/轮报告与验收工具.md`。

  guji-manager iterate round-report  轮报告：与上一轮按册按列对比、回退清单、按 pending_reason 分布（T7）
  guji-manager iterate gold          金标登记与校验（T8）
  guji-manager iterate audit         每轮滚动抽检台账（T9）
  guji-manager iterate leverage      杠杆排序：人审点选页的出卡顺序（T3）
  guji-manager iterate freeze        三书冻结日历（T6）

全部只读文件（pending-stats 的输出目录、tsv、yaml），不连库、不依赖 open_guji_cv。
"""
