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
    PageType("char_card", "一字一卡（第一次进库字确认）", "char_card.tpl.html", "1.6.4",
             "L01、L03 冷启动；同字头一张卡，看 3–5 个样例，其余跟随；逐格点选（切分/改字/看不清/对），每点即存"),
    PageType("char_grid", "字形快审表（全对点错）", "char_grid.tpl.html", "1.3.2",
             "参校字＝库首位的格；默认全对只点不对（史记冷启动 GUJI-750）"),
    PageType("pair_whitelist", "字对白名单抽样", "group_decide.tpl.html", "1.2.0",
             "N01、V01、越过参校本；按字组各抽 30 格带前后文，逐格点同字/不同字/看不清，每组页尾显示同字率，再定组结论（pair.py）",
             options=("同字", "不同字", "不确定"), doc_prefix="review_pair"),
    PageType("variant_compare", "异体/差异对比（终稿 vs 另一版本，按字对聚类）", "group_decide.tpl.html", "1.0.0",
             "拿另一版本（如维基文库 Page: 版）逐字对比终稿后的差异；按（终稿字，另本字）聚类，每格看图点 终稿对／另本对／都可以（异体不分）／看不清，也可整组一键标记（全唐文 11-19）",
             options=("终稿对", "另本对", "异体都可", "要逐格看"), doc_prefix="review_vc"),
    PageType("codepoint", "码位定夺", "codepoint.tpl.html", "2.2.0",
             "V02（原 Z06）、V01、M 类；按组看图定夺：每字一行原书字块＋已认/整理本数，定统一作某字／分开·互认（follow_ref 双向）"
             "／分开·不同字／合并到别的字（全唐文码位页 11-01–11-04 并入，见 codepoint.py）；2.2 起字体缺字的候选可带字形图 glyphs",
             options=("unify", "other", "split_follow", "split_distinct"), doc_prefix="review_cp"),
    PageType("gold_sample", "金标抽样（含上下文，文意判读）", "cell_pick.tpl.html", "1.2.0",
             "新放行类别上线前（R3）；终审标注页的通用版，保留 cell/pick/other/note/review 字段；点即存、读回、切分错/看不清/库里无此字、整理本字入上下文、横向邻格条、按 kind 筛选",
             doc_prefix="labels"),
    PageType("ref_check", "整理本真错复核（快速确认整理本字，疑整理本错置顶）", "cell_pick.tpl.html", "1.0.0",
             "待审里「整理本字对不对」：D01 库否决、L02、X01 等；预选整理本字，库首位并排一键改作；按 ref_suspect 排序（ref 最前）；"
             "横向邻格条＋整理本前后文；结果 `ref-check-apply` 出改字 tsv，喂 book-text 改字流程",
             doc_prefix="labels"),
    PageType("seg_cause", "切分归因看图", "seg_cause.tpl.html", "1.1.0",
             "S01–S04；按页成卡，列该页待审格，定切分错/切对了不是切分/特殊页型/看不出；输入来自 review/seg_causes.py（切分归因）",
             options=("切分错", "切对了不是切分", "特殊页型", "看不出"), doc_prefix="review_seg"),
    PageType("seg_cut", "人裁切线（小字被并成一格，点哪里该切开）", "seg_cut.tpl.html", "1.0.0",
             "两套格网都切错、夹注小字被并成整字格；每格一段列图叠两套格界，点图画切线、或标不切/看不出；"
             "结果存列图与页图坐标，用 segcut-apply 导出交重切（见 seg_cut.py）",
             options=("cut", "keep", "unsure"), doc_prefix="review_segcut"),
    PageType("col_check", "整列切分抽查（一页书一屏，点切错的格）", "col_check.tpl.html", "1.0.3",
             "切字 benchmark 银标抽查、整列验收；各列从右到左叠格框，点并字/劈字/框歪的格标红，整列没问题翻页记全对；"
             "结果用 colcheck-apply 导出（见 col_check.py）",
             options=("ok", "bad", "unsure"), doc_prefix="review_colcheck"),
    PageType("cut_check", "逐格切线审查（一格一图带上下半格，点不准的切线）", "cut_check.tpl.html", "1.0.0",
             "切字 benchmark L2 层：字与字之间的切点；一屏原书一列，每格上下各带半个邻格、画上下切线，点图上半/下半标那条切线不准，"
             "列首尾与边框之间、左右宽窄不审；结果用 cutcheck-apply 导出（见 cut_check.py）",
             options=("ok", "bad", "unsure"), doc_prefix="review_cutcheck"),
    PageType("near_pair", "形近字对比卡（两字各摆库刻例，待审格居中）", "near_pair.tpl.html", "1.0.1",
             "L4 同字聚合后的形近对（畫/書、全/今、文/又…）；选 A/B/都不是/看不清/切分有问题，点即存；"
             "可带 near_shape 差异区高亮；结果经 `pair_audit` 出 relabel/confirm 事件",
             options=("a", "b", "neither", "unclear", "seg"), doc_prefix="review_np"),
    PageType("lib_audit", "库内刻例审阅卡（按字头列刻例，标错的改字或撤库）", "lib_audit.tpl.html", "1.0.1",
             "体检/形近字对比发现的库标错（官/宫、之/史…）；点刻例标「这条标错」并填应为的字；"
             "结果经 `pair_audit` 出 glyph_audit relabel/evict/near_form 事件",
             options=("relabel", "evict", "near_form"), doc_prefix="review_la"),
    PageType("glyph_quality", "字块质量（干净/带框/切笔/污渍/看不清）", "glyph_quality.tpl.html", "1.1.0",
             "切分字块验收（列端框线等）；单块或同格新旧两版同倍放大并排，按字块 sha 锚定；"
             "输入可直接用 dataset 金标信封（如 frame-end-crop），结果用 gq-apply 回写（见 glyph_quality.py）",
             options=("clean", "frame", "cut", "stain", "unsure"), doc_prefix="review_glyph"),
    PageType("closeout", "收口单", "closeout.tpl.html", "1.2.0",
             "判停（R5）；每类剩余格一行，定去向：放行／留人审／算法再处理，合计即收口单；还有「算法再处理」就不出 v0.1",
             options=("放行", "留人审", "算法再处理"), doc_prefix="review_closeout"),
]}


def get(key: str) -> PageType:
    try:
        return PAGE_TYPES[key]
    except KeyError:
        raise SystemExit(f"没有这个页型：{key}（有：{', '.join(PAGE_TYPES)}）") from None
