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
    PageType("char_card", "一字一卡（第一次进库字确认）", "char_card.tpl.html", "1.5.3",
             "L01、L03 冷启动；同字头一张卡，看 3–5 个样例，其余跟随；逐格点选（切分/改字/看不清/对），每点即存"),
    PageType("char_grid", "字形快审表（全对点错）", "char_grid.tpl.html", "1.2.0",
             "参校字＝库首位的格；默认全对只点不对（史记冷启动 GUJI-750）"),
    PageType("pair_whitelist", "字对白名单抽样", "group_decide.tpl.html", "1.2.0",
             "N01、V01、越过参校本；按字组各抽 30 格带前后文，逐格点同字/不同字/看不清，每组页尾显示同字率，再定组结论（pair.py）",
             options=("同字", "不同字", "不确定"), doc_prefix="review_pair"),
    PageType("codepoint", "码位定夺", "codepoint.tpl.html", "2.2.0",
             "Z06、V01、M 类；按组看图定夺：每字一行原书字块＋已认/整理本数，定统一作某字／分开·互认（follow_ref 双向）"
             "／分开·不同字／合并到别的字（全唐文码位页 11-01–11-04 并入，见 codepoint.py）；2.2 起字体缺字的候选可带字形图 glyphs",
             options=("unify", "other", "split_follow", "split_distinct"), doc_prefix="review_cp"),
    PageType("gold_sample", "金标抽样（含上下文，文意判读）", "cell_pick.tpl.html", "1.1.0",
             "新放行类别上线前（R3）；终审标注页的通用版，保留 cell/pick/other/note/review 字段；点即存、读回、切分错/看不清/库里无此字、整理本字入上下文、横向邻格条、按 kind 筛选",
             doc_prefix="labels"),
    PageType("seg_cause", "切分归因看图", "seg_cause.tpl.html", "1.1.0",
             "S01–S04；按页成卡，列该页待审格，定切分错/切对了不是切分/特殊页型/看不出；输入来自 A22 seg_causes",
             options=("切分错", "切对了不是切分", "特殊页型", "看不出"), doc_prefix="review_seg"),
    PageType("near_pair", "形近字对比卡（两字各摆库刻例，待审格居中）", "near_pair.tpl.html", "1.0.1",
             "L4 同字聚合后的形近对（畫/書、全/今、文/又…）；选 A/B/都不是/看不清/切分有问题，点即存；"
             "可带 near_shape 差异区高亮；结果经 `pair_audit` 出 relabel/confirm 事件",
             options=("a", "b", "neither", "unclear", "seg"), doc_prefix="review_np"),
    PageType("lib_audit", "库内刻例审阅卡（按字头列刻例，标错的改字或撤库）", "lib_audit.tpl.html", "1.0.1",
             "体检/形近字对比发现的库标错（官/宫、之/史…）；点刻例标「这条标错」并填应为的字；"
             "结果经 `pair_audit` 出 glyph_audit relabel/evict/near_form 事件",
             options=("relabel", "evict", "near_form"), doc_prefix="review_la"),
    PageType("glyph_quality", "字块质量（干净/带框/切笔/看不清）", "glyph_quality.tpl.html", "1.0.0",
             "切分字块验收（列端框线等）；单块或同格新旧两版同倍放大并排，按字块 sha 锚定；"
             "输入可直接用 dataset 金标信封（如 frame-end-crop），结果用 gq-apply 回写（见 glyph_quality.py）",
             options=("clean", "frame", "cut", "unsure"), doc_prefix="review_glyph"),
    PageType("closeout", "收口单", "closeout.tpl.html", "1.2.0",
             "判停（R5）；每类剩余格一行，定去向：放行／留人审／算法再处理，合计即收口单；还有「算法再处理」就不出 v0.1",
             options=("放行", "留人审", "算法再处理"), doc_prefix="review_closeout"),
]}


def get(key: str) -> PageType:
    try:
        return PAGE_TYPES[key]
    except KeyError:
        raise SystemExit(f"没有这个页型：{key}（有：{', '.join(PAGE_TYPES)}）") from None
