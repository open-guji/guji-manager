"""新书体检：按待审原因的分布给出「往哪努力」的信号（A24，2026-11-04，sheldon 定长期计划 G1）。

框架见 ai-team `domain/CV/规划/形近字领域-长期计划与总览-草稿-2026-11-04.md` 第三节「新书诊断表」：
每类原因分 A 易（开开关、看图核字对，书项目自己做）／B 中期（新算法、本书标注，报 A24 排期）／C 暂不看（定人审或留后）。

纯函数：只看 `pending_stats.analyse` 给的每格一行（含 pending_reason、conc、ref、top、tok），不连库。
阈值是经验值（殿本 r4、史記／全唐文 11-02 三份单子定的），信号只是方向提示，动手前仍要抽样看图。
"""
from __future__ import annotations

import unicodedata
from collections import Counter

#: 占比门槛
SEG_SHARE = 0.25          # 切分类超过这个比例，先当版式问题
LIB_SHARE = 0.10          # 「库里没有」超过这个比例才看是不是借来的字形不像
LIB_COMMON_N = 30         # 整理本字库样本 ≥ 这个数算常用字
LIB_COMMON_SHARE = 0.30   # 常用字占「库里没有」的比例超过它 → 借来的字形不像
LIB_REPEAT_N = 3          # 没给字形库时：同一个整理本字在「库里没有」里反复出现 ≥ 这个数，当作常用字
GROUP_SHARE = 0.10
PAIR_SHARE = 0.08
SYMBOL_SHARE = 0.30
OCC_SHARE = 0.05

SEG = {"seg_page_unaligned", "seg_col_unaligned", "col_width_out_of_band", "seg_defect"}
OCC = {"occluded_with_ref", "occluded_no_ref"}
GROUP = {"group_abstain", "group_conflict", "group_demoted", "group_ref_dissent", "group_weak", "group_unconfirmed"}
PAIR = {"variant_pair", "near_form_guard"}
_SHAPE_TOK = ("ids", "margin", "hog", "unet", "shape", "stroke")
_CTX_TOK = ("ctx", "l1", "l2", "llm", "context")


def is_symbol(ch: str | None) -> bool:
    """非汉字的单个字符（○、●、△…）。"""
    if not ch or len(ch) != 1:
        return False
    name = unicodedata.name(ch, "")
    return "CJK UNIFIED" not in name and "CJK COMPATIBILITY IDEOGRAPH" not in name and unicodedata.category(ch) != "Co"


def _top(counter: Counter, k: int = 8) -> str:
    return "、".join(f"{a} {b}" for a, b in counter.most_common(k))


def signals(rows: list[dict], lib_n=None) -> list[dict]:
    """→ [{sig, n, share, why, todo, tier, who}]，只列命中的信号，按格数从多到少。"""
    n = len(rows) or 1
    by = Counter(r.get("pending_reason") or "unknown" for r in rows)
    out: list[dict] = []

    def add(sig, k, why, todo, tier, who):
        out.append({"sig": sig, "n": k, "share": k / n, "why": why, "todo": todo, "tier": tier, "who": who})

    seg = [r for r in rows if r.get("pending_reason") in SEG]
    if len(seg) / n >= SEG_SHARE:
        pages = Counter(f"{r['vol']}p{str(r['cell']).split(':')[0]}" for r in seg)
        whole = sum(1 for r in seg if r.get("conc") == "整页")
        add("版式／切分为主", len(seg), f"整页成片 {whole} 格；最多的页：{_top(pages, 6)}",
            "不是识字问题：先和 A22 定页型（表页、书衣、考證页），整页走人审或跳过；形近字线先不动", "A–B", "A22＋书项目")

    lm = [r for r in rows if r.get("pending_reason") == "lib_missing"]
    if len(lm) / n >= LIB_SHARE:
        refs = Counter(r.get("ref") for r in lm if r.get("ref"))
        if lib_n:
            common = sum(k for ch, k in refs.items() if lib_n(ch) >= LIB_COMMON_N)
            hit, why = common / max(len(lm), 1) >= LIB_COMMON_SHARE, f"整理本字在库里已有 ≥{LIB_COMMON_N} 例的占 {common / max(len(lm), 1):.0%}"
        else:
            rep = sum(k for _, k in refs.items() if k >= LIB_REPEAT_N)
            hit, why = rep / max(len(lm), 1) >= LIB_COMMON_SHARE, f"反复出现 ≥{LIB_REPEAT_N} 次的整理本字占 {rep / max(len(lm), 1):.0%}（没给 --glyph-db，按重复度估）"
        if hit:
            add("借来的字形不像这本书", len(lm), f"{why}；{_top(refs)}",
                "常用字也认不出，说明刻风不同：本书刻例点选补库；该字体族没有就建族（cv#897）", "B", "书项目＋A23／A24")
        else:
            add("真生僻字多（第一次进库）", len(lm), f"{why}；{_top(refs)}",
                "第一次进库原则上人裁：走成批审页，审完即入库", "C", "人审")

    gr = [r for r in rows if r.get("pending_reason") in GROUP]
    if len(gr) / n >= GROUP_SHARE:
        groups = Counter(r.get("key") or "?" for r in gr)
        toks = Counter(t for r in gr for t in (r.get("tok") or "").split(",") if t)
        shape = sum(k for t, k in toks.items() if any(s in t.lower() for s in _SHAPE_TOK))
        ctx = sum(k for t, k in toks.items() if any(s in t.lower() for s in _CTX_TOK))
        add("字组弃权／打架多", len(gr), f"组：{_top(groups)}；疑问码字形类 {shape}、文意类 {ctx}",
            "字形组（门 辶 xjz 于千子干）→ 本书标注、重训模板（B）；文意组 → 先开 group_flow_llm，再进只读文意终审（A→B）",
            "A→B", "A24＋书项目")

    pr = [r for r in rows if r.get("pending_reason") in PAIR]
    if len(pr) / n >= PAIR_SHARE:
        pairs = Counter(f"{r.get('ref') or '∅'}/{r.get('top') or '?'}" for r in pr)
        add("异体／形近字对多", len(pr), f"整理本/机器：{_top(pairs, 10)}",
            "按字对每对抽 10 格看图：整理本总对的同义对写 follow_ref_variants、不同义对写 follow_ref_seen；"
            "整本可信的书考虑 reference_trust", "A", "书项目")

    gap = [r for r in rows if r.get("pending_reason") == "ref_gap"]
    sym = Counter(r.get("top") for r in gap if is_symbol(r.get("top")))
    if gap and sum(sym.values()) / len(gap) >= SYMBOL_SHARE:
        add("整理本空位、图上是符号", sum(sym.values()), f"机器读到：{_top(sym)}",
            f"书级开 seed_admit.symbol_ref_blank: \"{''.join(c for c, _ in sym.most_common(3))}\"，从 seed_admit 重落", "A", "书项目")

    occ = [r for r in rows if r.get("pending_reason") in OCC]
    if len(occ) / n >= OCC_SHARE:
        pages = Counter(f"{r['vol']}p{str(r['cell']).split(':')[0]}" for r in occ)
        add("遮挡多", len(occ), f"{len(pages)} 页；最多的页：{_top(pages, 6)}",
            "先看是不是真印章：纸面噪点当成大印的书，配 seal_detect.stain_pages（真印页才列），从 seal_detect 重跑", "A", "书项目＋A32")

    # 11-05 用户定：己已巳、日曰折叠（图上匹配组内任一字都算对），不再单列「留到标点阶段」；其他极难形近照旧要分开
    hp = [r for r in rows if r.get("pending_reason") == "hard_pair"]
    fold = [r for r in hp if _folded(r.get("ref"), r.get("top"))]
    if fold:
        add("折叠组（己已巳、日曰）", len(fold), "`hard_pair`，整理本字与机器首选同在折叠组",
            "按 11-05 折叠口径，整理本字在组内就放行（管线侧待 A24 实现）", "A", "A24")
    if len(hp) > len(fold):
        add("其他极难形近", len(hp) - len(fold), "`hard_pair`", "近形决胜 near_shape 等（A24 定开不开）", "B", "A24")

    for reason, sig, todo, tier, who in (
        ("variant_form_open", "同义写法待定", "出码位看图页请 sheldon 定码位结局（暂归一／照录／按参校本取字）", "A", "书项目"),
        ("ref_lacuna", "整理本缺字（〓／私用码）", "新图源文本层取字、私用码统一码表；剩下的人审", "A–B", "A24"),
        ("lib_sparse_agree", "刻例太少但与整理本一致（本书库 1～2 例）", "人裁：同字全书一卡，走成批审页；放行规则待 L03 benchmark", "C", "人审"),
    ):
        if by.get(reason):
            add(sig, by[reason], f"`{reason}`", todo, tier, who)

    return sorted(out, key=lambda d: -d["n"])


FOLD_GROUPS = ("己已巳", "日曰")


def _folded(a, b) -> bool:
    """两字同在一个折叠组（11-05 用户定：己已巳、日曰图上分不开，算同一个）。"""
    return bool(a and b) and any(a in g and b in g for g in FOLD_GROUPS)


def render(rows: list[dict], lib_n=None) -> list[str]:
    sg = signals(rows, lib_n)
    out = ["## 零·二、诊断信号（往哪努力）", "",
           "按 ai-team `domain/CV/规划/形近字领域-长期计划与总览-草稿-2026-11-04.md` 第三节自动判。"
           "档：A 易（书项目先做）／B 中期（报 A24 排期）／C 暂不看。信号只是方向，动手前先抽样看图。", ""]
    if not sg:
        return out + ["没有命中的信号。", ""]
    out += ["| 信号 | 格数 | 占比 | 依据 | 往哪努力 | 档 | 谁 |", "|---|---|---|---|---|---|---|"]
    for d in sg:
        out.append(f"| {d['sig']} | {d['n']} | {d['share']:.1%} | {d['why']} | {d['todo']} | {d['tier']} | {d['who']} |")
    return out + [""]
