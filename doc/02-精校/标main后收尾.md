# 标 main 后收尾（`guji closeout`）

方案原文：ai-team `domain/CV/质检/重跑轮次/标main后自动收尾-方案.md` 第八节（8.8、8.9）。这里只写代码里怎么落的。

## 原则

不另存「余项」。对不上的标点／专名锚点就是**待审格**：

| 原因 | 码 | 判据（每次出单／换单／点校提交时按当前 book-text 现算） |
|---|---|---|
| `anchor_miss` | A01 | F-OV-02 式：锚点指向不存在的格，或校验字（`pre_char`／专名 `text`）与该格现字不符 |
| `add_del` | A02 | 同上，但落在增删格（对照表「新增」格、紧邻「删」格的新格）所在的句子里 |
| `anchor_drift` | A03 | `check_anchor_drift`（local_check --dev「其他标点」）仍报漂移 |

三条 route=deferred、reviewer=none：不进人审字卡、不算人审率，留点校阶段统一重挂。**不写清除事件**：
点校重挂并过检查后，下次现算自然没了（`anchors.stamp` 先 `purge` 上次写的再写这次的）。

一格多因：`pending_reason` 放主因（字的原因优先，A 类 priority 900+），其余锚点原因按 priority 放
`pending_reason_also`；旧新锚和说明放 `pending_reason_detail` 里以 `anchor=` 开头的一段（JSON 数组，
每项 `l 层／i 条目／o 旧锚／n 新锚／t 内容／c 原因码／w 说明`），别的段原样保留，段间用 ` | `。

## 命令

```
guji closeout derive  <待审单.json> --repo <book-text> --vdir <版本目录> --chapter NNN [--cells 旧→新对照表]
guji closeout stamp   <待审单.json> --report <auto_remap 分流项.json>
guji closeout stats   <待审单.json…>        # 现算：按册、原因码
guji closeout list    <待审单.json> [--reason anchor_miss]
guji closeout redline <册> --human-total N --human-lost N --anchors-moved N --anchors-left N [--error …] [--glyph-verify-fail]
guji closeout fix-misplaced --repo … --vdir … --chapter NNN --cells <dev当前→正确 对照表> [--apply] [--audit 审计.tsv]
```

## 红线（A31 定）

人裁丢失 > 本册人裁格 1%；锚点余项 > 15%（分母＝改＋分流）；任何一步报错或字形库 verify 不过。
超了整册不写、轮报告标「超红线」。阈值常量在 `closeout/redlines.py`。

## dev 错位自动写回（`writeback`）

三条件同时满足才写：来源是机器；对照表位置上的字等于 `pre_char`；dev 当前锚点上的字与 `pre_char` 不同。
对照表要用「dev 当前→正确」的表，不能复用换图那张（已挪过的会被再挪一次）。缺省只出计划；
`--apply` 才写，审计行进 commit 信息和轮报告，另抽 30 条（固定种子）上审阅页复核，有错回退并关自动。

## 换单叠改字（`swap/overlay_edits.py`）

在导出新 char 之后、交 auto_remap 之前：按对照表把 dev 上登记的人工改字叠到新 char，叠完核对位（格序不变、
只有登记的格换字），不过抛 `AlignmentError`，整册停下。机器本轮又改了的格保留人改字，记 `overturned`（入新一轮待审单，X03）。

## 还没做

- 出单脚本（cv `republish.py`／`pending_list.py`）调用 `derive`＋`stamp`，把 A 类写进线上单。
- 别仓 enum 副本（kaiyuanguji-web TS、看板、book-text 校验器）按 `python -m guji_manager.review.pending_reason --json` 同步。
- 把 `derive`／`overlay`／`remap_lib`／红线串成 `swap book_text` 的一条龙。
