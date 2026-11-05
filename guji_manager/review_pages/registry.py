"""页型注册表：每个页型一个模板、一个版本号、一份结果文档格式。

改模板就改 `version`（语义化：改交互/结果字段升 minor 或 major，改样式升 patch）；
台账按（页型，版本）分组统计，所以版本号不改就看不出改动有没有变好。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PageType:
    key: str
    title: str
    template: str | None          # templates/ 下的文件名；None 表示还没有模板
    version: str
    used_for: str                 # 对应框架里的漏斗层/格类
    options: tuple[str, ...] = field(default_factory=tuple)   # group_decide 的选项
    doc_prefix: str = "review"    # 结果存进 db 的集合名


PAGE_TYPES: dict[str, PageType] = {p.key: p for p in [
    PageType("char_card", "一字一卡（第一次进库字确认）", "char_card.tpl.html", "1.1.0",
             "L01、L03 冷启动；同字头一张卡，看 3–5 个样例，其余跟随；逐格点选（切分/改字/看不清/对），每点即存"),
    PageType("char_grid", "字形快审表（全对点错）", "char_grid.tpl.html", "1.1.0",
             "参校字＝库首位的格；默认全对只点不对（史记冷启动 GUJI-750）"),
    PageType("pair_whitelist", "字对白名单抽样", "group_decide.tpl.html", "1.0.0",
             "N01、V01、越过参校本；每个字对抽样看图，定同字/不同字",
             options=("同字", "不同字", "不确定"), doc_prefix="review_pair"),
    PageType("codepoint", "码位定夺", "group_decide.tpl.html", "1.0.0",
             "Z06、V01；按码位组看图，定归一到哪个或分开",
             options=("归一到前者", "归一到后者", "分开", "不确定"), doc_prefix="review_cp"),
    PageType("gold_sample", "金标抽样（含上下文，文意判读）", "cell_pick.tpl.html", "1.0.0",
             "新放行类别上线前（R3）；终审标注页的通用版，保留 cell/pick/other/note/review 字段",
             doc_prefix="labels"),
    PageType("name_pick", "专名待确认点选页", "cell_pick.tpl.html", "1.0.0",
             "点校预标（A33）；每项一处待定专名，上下文＋候选专名（带来源），点选或填其它；字段同 gold_sample",
             doc_prefix="review_name"),
    PageType("name_register", "库无专名建档确认页", "group_decide.tpl.html", "1.0.0",
             "点校预标（A33）；每组一个库里没有的专名，看出处语句，定建档/并入已有/不建",
             options=("建档", "并入已有", "不建", "不确定"), doc_prefix="review_namereg"),
    PageType("punct_check", "标点抽样验收页", "group_decide.tpl.html", "1.0.0",
             "点校验收（A33）；抽样段落带标点，逐段判对/错/存疑，备注写错在哪",
             options=("对", "错", "存疑"), doc_prefix="review_punct"),
    PageType("seg_cause", "切分归因看图", None, "0.0.0", "S01–S04；输入字段要和 A22 的 seg_causes 表一起定，待建"),
    PageType("closeout", "收口单", None, "0.0.0", "判停（R5），待建"),
]}


def get(key: str) -> PageType:
    try:
        return PAGE_TYPES[key]
    except KeyError:
        raise SystemExit(f"没有这个页型：{key}（有：{', '.join(PAGE_TYPES)}）") from None
