# 按组看图定夺（脚本＋页面模板）

方案文档：[doc/01-开新书/按组看图定夺.md](../../../doc/01-开新书/按组看图定夺.md)。全唐文码位对照页（2026-11-01，33 组）就是用这套出的。

```bash
D=out/cp-批1
python find_groups.py --ws $WS --ref <借库书>/config/codepoints.yaml --extra 為,爲 --extra 既,旣 \
       --grid ~/.guji-data/main/<书>/corpus/<逐列语料>.txt --out $D          # 1 找组＋抽样
GUJI_WORKSPACE=$WS <cv python> render.py $D/cells.jsonl                      # 2 渲字块
python build_page.py --groups $D/groups.json --cache $WS/cache --out $D/page.html \
       --title "全唐文码位对照" --lede "批 1（册 04–15）里同一种刻法被认成了两个码位。" --suggest 為=爲   # 3 出页
# 4 Artifact 发布 page.html，capabilities {db: {}}；人点完后 ArtifactData list 集合 cp 存成 choices.json
python to_codepoints.py --groups $D/groups.json --choices choices.json --who Sheldon > 片段.yaml   # 5 落配置
```

| 文件 | 作用 |
|---|---|
| `find_groups.py` | 候选组 → 只留两边都有放行格的组，统计放行/整理本数，每字抽样 |
| `render.py` | 抽中的格渲成字块（要 cv 与中心库读令牌） |
| `build_page.py` | 字块嵌进 `tpl.html`，出自包含页 |
| `tpl.html` | 页面模板（db 存选择；统一/分开/合并到别的字/其余按建议） |
| `to_codepoints.py` | 页上选择 → codepoints 片段＋异体登记清单 |

配置要推中心库数据目录的 `config/`，不是工作区仓（见方案文档第三节第 5 步）。
