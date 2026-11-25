# 字格永久编号 u 与身份账

> 0.7.0 起（2026-11-25）。设计与格式细节见仓里 [doc/参考/字格身份账.md](https://github.com/open-guji/guji-manager/blob/dev/doc/参考/字格身份账.md)、[doc/4-反馈迭代/设计-字格u改挂.md](https://github.com/open-guji/guji-manager/blob/dev/doc/4-反馈迭代/设计-字格u改挂.md)。

## 为什么要 u

格号（`册:页:列:格`，如 `vol28:4:1:3`）是**切分的位置**，不是字的身份：重切、换图源、补删一格，后面的格号就全挪了。以前每次重切，挂在格号上的裁定、人裁、待审条目、网站票都要跑一遍「旧格→新格」对照（框 IoU）去迁，迁不准就丢。

**u** 是册内唯一的正整数，发给一格以后跟着这格的字走，永不改、永不复用。重切以后格号变了，u 不变；挂在 u 上的东西就不用迁。

![字格永久编号 u](images/uid.png)

## 身份账

每册一份 `feedback/uid/<册>.jsonl`，**只追加**，推进中心库 events 表（`stream=uid`）。每页每次切分一行，记这一页当时的「格号→u」、字、框和变化来历：

```json
{"kind": "uid_ledger", "src": "advance", "book": "vol28", "page": 4,
 "cells_sha": "fc122fc65a74…", "via": {"iou": 112, "new": 84},
 "map":   {"vol28:4:1:-1": 327, "vol28:4:1:1": 328, "vol28:4:1:2": 329, "…": "…"},
 "chars": {"vol28:4:1:-1": "經", "vol28:4:1:1": "綸", "vol28:4:1:2": "創"},
 "boxes": {"vol28:4:1:-1": [1574, 94, 116, 92], "…": "…"},
 "lineage": [{"u": 29064, "new": true}, {"u": 795, "into": 796}, {"u": 499, "gone": true}]}
```

（殿本总目 vol28 第 4 页真数据，删节。）一页最后一行就是现行切分；`lineage` 记拆出来的新格（`split_from`）、并掉的（`into`）、删掉的（`gone`）。

| 命令 | 做什么 |
|---|---|
| `guji uid init <册>` | 从 book-text 现有切分建账（每格发 u）。一册只做一次 |
| `guji uid advance <册>` | 切字后入账：按框 IoU→中心距→拆→并→字序列对照，把旧 u 接到新格上。**标 main 时自动入**（`guji pipeline products pack promote` 之后拉这册的账、按新 main 包入账、推回中心库；`GUJI_UID_ON_PROMOTE=0` 关，`GUJI_UID_AUTO_PUSH=0` 只入本机）。执行机跑完不入账，没标 main 的试跑包不进账 |
| `guji uid show <册> --cell 格号` ／ `--u N` | 查一格的 u，或一个 u 现在在哪格、来历 |
| `guji uid verify <册>` | 核账：u 不重复、作废的不再出现、每页最后一行和产物对得上 |
| `guji uid table <册> [--pages …]` | 出「旧切分→新切分」格级对照表（`旧格 新格 旧字 新字 类别 IoU 说明`），和 A31 的 old_new_cells 同格式，`cell_migrate`／`cell_rekey`／swap 直接读 |
| `guji uid migrate-plan <册> [--items …] [--write]` | 存量迁移：给旧的裁定、人裁、待审条目配 u（见下） |

`guji uid table vol28` 的一段（第 4 页第 1 列列首多切出一格，后面格号全挪一位，u 不变）：

```
旧格          新格           旧字 新字 类别 IoU    说明
vol28:4:1:1   vol28:4:1:-1  經   經   改号 0.936  u327
vol28:4:1:2   vol28:4:1:1   綸   綸   改号 0.933  u328
vol28:9:1:-1                國        删         u794 并入 u795
```

## u 写在哪里

| 东西 | 字段 | 谁读 |
|---|---|---|
| 文意裁定（`ctx_ruling`） | `payload.u` | cv `RulingStore` 按 (组, 册, u) 建索引 |
| 人裁事件（格级 confirm 等） | `target.anchor.u` | seed_admit、`rulings-hits`、网站票去重 |
| 待审条目 | `u`；线上单 `cells[]` 每格也带 | 出单、落票按 u 先认（再指纹、再格号） |
| 网站票 | D1 票表的 `u` 列 | `cellvotes` 按 u 分组；u 已作废的票挂起（`moved`） |
| book-text | char v0.6 每格 `u`，顶层 `u_max`、`u_retired`；norm v0.3 条目带 `u` | 网站、标点专名按 u 挂 |

**写入一律以 u 为准**（0.7.0）：manager 里所有写人裁事件、裁定的地方（`EventLog`／`RulingLog`）追加前自动盖 u。册有身份账而盖不上（账上没这一格、格号不全）的，**整批报错不写**，提示先 `guji uid advance <册>`。格号照写，方便人读。没账的册行为不变。

## 存量迁移（2026-11-25 已对全库做完）

`guji uid migrate-plan` 给已有的东西配 u，只追加：裁定、人裁各抄一条带 u 的（id、批次名加 `~u`，时间和序号不变，原事件不动），待审条目追加一版补 `u`。认格的依据：

- **裁定**：记了格锚 `cells_sha` 且等于账上某行 → 直接取那行的 u；否则比窗口（格号前后各 2 字，按本书异体归一表比）：两侧都同，或一侧同且裁定字＝账上字；没记窗口的（私用码记录）裁定字＝账上字，或账上各版这格都是同一个 u。
- **人裁**：锚里的 `cells_sha` 主段＝账上某行 → 取那行的 u；否则人裁字（字形或读作）＝账上字；没字可比时账上各版这格同一个 u。
- **待审条目**：格号在现行账里就补。

每册出 `守恒.json`（迁前＝迁出＋没迁，对不上直接报错）和 `清单.tsv`（没迁的每条一行、写理由）。没迁的多是：九月旧格号（那时列内顺序号和现行格网号不同，本来就挂不上现格）、人裁字和现行文本不同而切分又变过的、旧提示词版本的裁定（seed_admit 本来就不认）。

做法：先 `guji db pull`，`guji uid migrate-plan <册> --items <条目文件> --write`，再按 `写入.json` 列的文件 `guji db push --only …`（推库要设 `GUJI_ACTOR`）。
