# 专名匹配（entity_match）

`match.py`：A 稿专名（conv 产出 entity.json）→ 对 book-index Entity 的匹配状态。
- `alias.tsv` 通用别名（单字称谓、帝号前缀、避讳）；书级补充用 `--alias 书仓/code/entity_alias.tsv`（同格式，覆盖通用）。
- `annotators.tsv` 注家／常见引称人物的朝代，同名多人时按它消歧（选中记 `by: annotator`）；书级用 `--annot`。
- 状态 matched／ambiguous／new_candidate／no_work_layer（书名要另接 Work 层）；单字人名唯一匹配标 `weak`，须抽检（人名唯一≠安全）。
- 异体归一表在 `match.py` 的 EXT，随各书补。
- 史记册 1–2 试跑（11-23）：人名 ambiguous 683→224，new_candidate 914→573（别名 453＋注家消歧 459）；经验见 wiki/文意与知识/文意与知识-各册经验.md §四。
