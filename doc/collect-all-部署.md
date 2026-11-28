# 定时收单部署（GM4，2026-11-28）

脚本：`scripts/collect_all.py`（不需要 AI）。每轮：读中心库 `web_inbox` 有票的书 → 每本 `guji collect --books auto --fresh` → 有落格的册触发 kaiyuanguji-web 的 `proofing-sync.yml`（target=production, parts=publish, only=书/册）。

## 机器要求
- guji-manager 须 ≥ v0.7.11（章号按册 yaml 位数）；v0.7.10（含 v0.7.5 的会员号热修、v0.7.7 的配置组层、v0.7.8 的事件写端、v0.7.10 的收尾改名护栏、v0.7.11 的改号后章号；cv 配 v0.9.16）（网站新票的 `voter` 是 8 位会员号、迁移前票带 `voter_prev`；身份识别在 `guji_manager/voter.py` 的 `voter_ident`，collect 里写人裁事件的「意见来源」用它，脚本本身只数票、不碰这字段）。
- Python 3.12 venv，装 open-guji-cv（tag v0.9.9 或更新）与 guji-manager（本分支/main），`guji model fetch` 取过模型。
- 磁盘：每本书工作区在 `--ws-root` 下，数据目录 `$GUJI_DATA_HOME`（缺省 ~/.guji-data）；book-text 检出（dev 分支，可稀疏，只需 scripts、docs 与要收的书目录）。
- `gh` 已登录，且能触发 open-guji/kaiyuanguji-web 的 workflow。

## 环境变量（值由 Deploy 从密钥库取，不进仓）
- `GUJI_DATA_URL=https://data.open-guji.com`
- `GUJI_DATA_TOKEN_PROD`（写中心库）、`GUJI_DATA_TOKEN_READ`（只读，可选）
- `GUJI_BOOK_TEXT=<book-text dev 检出路径>`；推 dev 要有能写 open-guji/book-text 的令牌（密钥库里只有 GH_ORG_TOKEN 一个 GitHub 令牌；先 `git push --dry-run` 验证有写权限）
- `GUJI_ACTOR=GM4`、`GUJI_JOBS_WHO=GM4`
- `GH_TOKEN_WEB`（可触发 kaiyuanguji-web workflow 的令牌；缺省用 gh 当前登录）
- `COLLECT_EXCLUDE`：不收的书 ID，逗号分隔（见下）

## 命令与频率
```
python scripts/collect_all.py --ws-root ~/ws
```
每 30 分钟一次（cron `7,37 * * * *`）；上一轮没跑完不要重叠（用 flock）。`--dry-run` 只列有票的书。`--only <id,…>` 只做指定书。

## 当前排除名单（COLLECT_EXCLUDE）
- 96mid1ogzk 殿本（四库总目）、995ejelvk0 全唐文：原线程在管，合并进来前先问 ZM／QTW 线要不要纳入。
- 99k3i35yww 脉经：等其迁移完成。
- 98y6h42f41 朱楓林集、988g7gsqhd 北行日錄、988g3f0wsu 史記：正在改册号位数（01→1），等「配合册号位数统一迁移」线程通知后才可移出名单。
- 朱楓林集还要等 MBJ 通知 001-r2 出单。

## 已知注意
- `db pull` 被本地未推文件挡住时脚本会 `--force` 强拉（中心库为准）。
- 没出新台账即报「collect 失败」，不会拿旧台账冒充。
- 发站：全站超 40 分钟会被取消，脚本只发有落格的册；3 小时节流。
