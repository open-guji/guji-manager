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
    PageType("char_card", "一字一卡（第一次进库字确认）", "char_card.tpl.html", "1.2.0",
             "L01、L03 冷启动；同字头一张卡，看 3–5 个样例，其余跟随；逐格点选（切分/改字/看不清/对），每点即存"),
    PageType("char_grid", "字形快审表（全对点错）", "char_grid.tpl.html", "1.1.0",
             "参校字＝库首位的格；默认全对只点不对（史记冷启动 GUJI-750）"),
    PageType("pair_whitelist", "字对白名单抽样", "group_decide.tpl.html", "1.0.0",
             "N01、V01、越过参校本；每个字对抽样看图，定同字/不同字",
             options=("同字", "不同字", "不确定"), doc_prefix="review_pair"),
    PageType("codepoint", "码位定夺", "codepoint.tpl.html", "2.0.0",
             "Z06、V01、M 类；按组看图定夺：每字一行原书字块＋已认/整理本数，定统一作某字／分开·互认（follow_ref 双向）"
             "／分开·不同字／合并到别的字（全唐文码位页 11-01–11-04 并入，见 codepoint.py）",
             options=("unify", "other", "split_follow", "split_distinct"), doc_prefix="review_cp"),
    PageType("gold_sample", "金标抽样（含上下文，文意判读）", "cell_pick.tpl.html", "1.0.0",
             "新放行类别上线前（R3）；终审标注页的通用版，保留 cell/pick/other/note/review 字段",
             doc_prefix="labels"),
    PageType("seg_cause", "切分归因看图", "seg_cause.tpl.html", "1.0.0",
             "S01–S04；按页成卡，列该页待审格，定切分错/切对了不是切分/特殊页型/看不出；输入来自 A22 seg_causes",
             options=("切分错", "切对了不是切分", "特殊页型", "看不出"), doc_prefix="review_seg"),
    PageType("closeout", "收口单", None, "0.0.0", "判停（R5），待建"),
]}


def get(key: str) -> PageType:
    try:
        return PAGE_TYPES[key]
    except KeyError:
        raise SystemExit(f"没有这个页型：{key}（有：{', '.join(PAGE_TYPES)}）") from None
