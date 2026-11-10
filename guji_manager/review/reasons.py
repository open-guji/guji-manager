"""判一格的待审原因 `PendingReason`（A31，sheldon 2026-11-03 定）：出单时算好、写进待审单的 `pending_reason`。

取代 `review/causes.py` 的成因码（A1…I）与 `review/cards.py` 的卡片类别（`cls`）作为「为什么待审」的口径；
那两样过渡期照旧出（双写），两轮后停。判法搬自 A31 统计用的分类 v2（ai-team `按包统计人审率/classify_v2.py`），
按 `pending_reasons.yaml` 里的 `priority` 从小到大逐条试，第一条命中的就是这一格的原因；都不中＝`unknown`。

**这里只判原因，不放行、不改字、不碰任何 Step**：读 seed_admit／align_ref／glyph_match 三层产物和待审单上已有的字段，
不在任何 Step 的 `code_deps` 里，产物指纹不变。判定依据（证据）照旧是 `why[]`，不在这里。

缺事实时不猜：比如没给字形库样本数（`lib_n`），「刻例太少」这两条就判不了，落到后面的规则或 `unknown`。
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .cards import doubt_codes
from .pending_reason import PendingReason as R, specs

#: 极难形近：机器字、整理本字、库首选全落在这几个字里（sheldon 11-03：留到标点、专名阶段）
HARD_CHARS = frozenset("日曰己已巳")
#: 整理本字在字形库的刻例 ≤ 这个数算「刻例太少」
LIB_SPARSE = 2
#: 同页无对位（或弱证据）格 ≥ PAGE_MIN 算整页对不上；同列无对位 ≥ COL_MIN 算整列对不上
PAGE_MIN, COL_MIN = 10, 5
#: 弱证据格（有参校字、机器字不同）只在「本列大多对不上」时才算进整页对不上：本列有参校字的格里机器字＝参校字的比例
#: 低于这个数。真错位的列几乎全不一致；半色调／褪色页对位是对的、只是认不准，列一致率多在 0.6 以上，不归 S01（A22 11-05）
COL_AGREE_MAX = 0.5
#: 碎片格（R02 深挖 11-06，sheldon 定直接改归 S04）：格框边长（√宽×高）小于本页同类（正文／夹注分开）格中位数的这个比例，
#: 或短边／长边小于 FRAG_ASPECT，是切坏的碎片；只对**整理本这位没字**的格生效（有整理本字的格走别的原因）。
FRAG_REL, FRAG_ASPECT = 0.6, 0.35
#: 「机器改判」复审格：待审单上 recheck=true 且说明以此开头（auto_cycle 出的复审清单）
MACHINE_CHANGED_NOTE = "机器改判"
#: 11-05 起（cv #1148）只有「机器推翻最新人裁」才进复审，说明里带这几个字；老单上「机器改判…，无人裁」的复审格不算 X03，归 recheck。
MACHINE_OVERRULE_MARK = "推翻人裁"

_GARBLE = {"ctx_garble_shape", "shadow_veto", "ctx_garble_rare"}
_VARIANT = {"ref_lib_variant", "variant_indirect", "replace_form", "channel_off"}


def ref_missing(ch: str | None) -> bool:
    """整理本这位是〓、缅甸文占位或私用码（没码位的生僻字）。私用码（U+E000–F8FF、15／16 平面）11-07 起也算（A24 R01 核实，
    sheldon 同意）：史記整理本直接带私用码，不是殿本那套缅文占位；原先它们落 P02／L01。"""
    return bool(ch) and (ch == "〓" or any(0x1000 <= ord(c) <= 0x109F or 0xE000 <= ord(c) <= 0xF8FF or ord(c) >= 0xF0000
                                           for c in ch))


@dataclass
class Cell:
    """判原因要用的一格事实（都从产物或待审单来，缺就是 None／空）。"""
    id: str
    char: str | None = None
    ref: str | None = None
    ref_op: str | None = None
    cands: list = field(default_factory=list)          # 库候选 [[字, 分], …]
    doubts: list = field(default_factory=list)         # seed_admit doubts 原样
    evidence: dict = field(default_factory=dict)
    recheck: bool = False
    note: str = ""
    cls: str | None = None                             # 待审单上的旧卡片类别（老单的 seg_defect 只有这里有；11-04 起不出单）
    seg_kind: str | None = None                        # 切坏细分（单上同名字段；产物里在 evidence.seg_kind），见 SEG_KINDS
    ref_left: str = ""                                 # 整理本这位前 20 字／后 20 字（缺字格回查私用码；其余格给 ref_suspect）
    ref_right: str = ""
    pua_code: str | None = None                        # 整理本这位的私用码永久编号「来源:码位」（如 daizhige:U+E123、siku-qiefen-v2:U+F1001），没有就空；glyph_pending 凭它判
    src: str | None = None                             # 单上的来源标记；"seg_selfcheck"＝出单同字对照自检放上单的已放行格（B1③）
    page_kind: str | None = None                       # 非正文页型（border_detect_gate page_type≠body，或职名页分支 roster）；正文页是 None。非正文页不判 S01
    col_agree: float | None = None                     # 本列（含已放行格）有参校字的格里机器字＝参校字的比例；不知道是 None（照旧算弱证据）
    bleed: bool = False                                # cell_shrink 给这格打了 boundary_ink 旗（框线／邻字墨溢进格框，A22 11-08 L04 残片判据第 2 条）；没读到就是 False
    ref_by_design: bool = False                        # 本页本就没配参校本（align_ref note「未配置整理本／未配置证人」，如全唐文 001–003 故意不带）：没有对位字是设计，不是对位／切分出了事；不判 S01／S02／R02，落字形类
    frag: bool = False                                 # 格框明显小于本页同类格（半截字、墨点、框角），见 `FRAG_REL`；没读到 cell_shrink 就是 False

    @property
    def codes(self) -> set[str]:
        return set(doubt_codes(self.doubts))

    @property
    def lib_miss(self) -> bool:
        return "lib_miss" in self.codes or any(isinstance(d, str) and d.startswith("库里没有") for d in self.doubts)

    @property
    def top(self) -> str | None:
        return self.cands[0][0] if self.cands else None

    @property
    def group(self) -> dict | None:
        return (self.evidence or {}).get("group")

    @property
    def has_ref(self) -> bool:
        return bool(self.ref) and not ref_missing(self.ref)


@dataclass
class Context:
    """整册（或整单）层面的事实。"""
    page_noref: Counter = field(default_factory=Counter)
    page_weak: Counter = field(default_factory=Counter)
    col_noref: Counter = field(default_factory=Counter)
    lib_n: Callable[[str], int] | None = None            # 老口径刻例数（含借来的）；只在没给 lib_split 时兜底
    are_variants: Callable[[str, str], bool] | None = None
    same_writing: Callable[[str, str], bool] | None = None      # 同一个字的不同写法（cv 暂归一表 forms，比 are_variants 窄）；Z 类折叠解法给字用它，没给退回 are_variants
    edge_tier: Callable[[str, str], str | None] | None = None   # 异体边分型 T1／T2／T3；给了就只认 T1、T2 算异体（V01 收窄）
    lib_split: Callable[[str], tuple[int, int]] | None = None   # 字 → (本书刻例数, 借来刻例数)，给 lib_missing 细分
    lib_own: Callable[[str], int] | None = None         # 字 → 本书版本的刻例数（n_confirmed）；L01–L03 边界用它
    glyph_pending: frozenset[str] = frozenset()                 # 私用码表里登记为「已判定待收」的永久编号；没给＝一个都不算


def _page(cid: str) -> str:
    return ":".join(cid.split(":")[:-2])


def _col(cid: str) -> str:
    return ":".join(cid.split(":")[:-1])


def build_context(cells: list[Cell], lib_n=None, are_variants=None, lib_split=None, glyph_pending=(), edge_tier=None,
                  lib_own=None, same_writing=None) -> Context:
    ctx = Context(lib_n=lib_n, are_variants=are_variants, lib_split=lib_split, glyph_pending=frozenset(glyph_pending),
                  edge_tier=edge_tier, lib_own=lib_own, same_writing=same_writing)
    for c in cells:
        if not c.has_ref and not c.ref_by_design:
            if c.ref is None or not ref_missing(c.ref):      # 〓 是整理本缺字（R01），不算「无对位」（S01 深挖 11-06，与列一支同口径）
                ctx.page_noref[_page(c.id)] += 1
                ctx.col_noref[_col(c.id)] += 1
        elif c.char != c.ref and not c.group and "occluded" not in c.codes \
                and (c.col_agree is None or c.col_agree < COL_AGREE_MAX):
            ctx.page_weak[_page(c.id)] += 1
    return ctx


#: 算异体的边分型（A24 V01 深挖 11-06）：T3（只有通假、形近、简繁来源）不是异体。
VARIANT_TIERS = frozenset({"T1", "T2"})


def _variant_with_ref(c: Cell, ctx: Context) -> bool:
    """异体：带异体疑问码；或整理本字与**库首位或机器字**在异体表里有边（A24 V01 深挖 11-06 收窄：不再看前五里其它候选，
    那些多是陪衬字碰巧与整理本有边；给了 `ctx.edge_tier` 时只认 T1／T2，通假、简繁的 T3 不算）。只改分类，不放行。"""
    if c.codes & _VARIANT:
        return True
    if not (ctx.are_variants and c.has_ref and c.top and c.top != c.ref):
        return False
    for x in {c.top, c.char}:
        if not x or x == c.ref or not ctx.are_variants(c.ref, x):
            continue
        if ctx.edge_tier is None or ctx.edge_tier(c.ref, x) in VARIANT_TIERS:
            return True
    return False


def lib_own_n(c: Cell, ctx: Context) -> int | None:
    """参校字在**本书**字形库里的刻例数（L01／L02／L03 边界唯一用的数）。

    优先 `ctx.lib_own`（`lib_own_counts`：本书版本 `glyphs.n_confirmed`，不含借来的版本）；没给就退回 `ctx.lib_n`
    （老口径，所有版本求和、含借来的）。不用 `lib_split`（exemplars 数）：11-06 实测史記、全唐文库里有大批
    exemplars 指向缺失的 instances，按它数会把「一」这类常用字数成 0 例。两个都没给、或这一格没有参校字 → None（不猜，L02／L03 都不中）。
    A23 L03 深挖（sheldon 11-06 同意调 L01–L03 边界）：史記库借了全唐文，按老口径借来的刻例也算，少刻例字被算成 >2。"""
    if not c.has_ref:
        return None
    if ctx.lib_own is not None:
        return ctx.lib_own(c.ref)
    if ctx.lib_n is not None:
        return ctx.lib_n(c.ref)
    return None


def _sparse(c: Cell, ctx: Context) -> bool:
    """刻例太少：参校字本书库里 0～`LIB_SPARSE` 例。0 例的在 `classify` 里改归 L01（第一次进库）。"""
    n = lib_own_n(c, ctx)
    return n is not None and n <= LIB_SPARSE


#: 字组流程已定下字的决定（`evidence.group.decision`）；这样的格要是还在待审，不是字组的事。
GROUP_SETTLED = frozenset({"admit", "keep", "provisional"})


def _fold_fn(x: Context | None):
    """Z 类折叠「同字异形」用的判等：优先 ``same_writing``（cv 暂归一表，只认同一个字的写法），没给退回 ``are_variants``。
    cv 的异体表很宽（大／太、傳／傅、玉／王、戊／戌 都有边），拿它折会把文意与字形各执一字的真冲突折成一个字，落进 Z03
    （A24 Z03 深挖 11-07：全唐文 Z03 11 格里 9 格）。"""
    return (x.same_writing or x.are_variants) if x else None


def _same_form(sol: set, x: Context | None) -> bool:
    """解法给的几个字彼此是同字异形（象／𧰼、寇／㓂、會／㑹…）→ 不算「几个字」。没给判等函数就不折叠。"""
    fold = _fold_fn(x)
    if not (fold and len(sol) > 1):
        return False
    first, *rest = sorted(sol)
    return all(fold(first, r) for r in rest)


def _distinct(sol: set, x: Context | None) -> list[str]:
    """解法给的字按同字异形折叠后的不同字；没给判等函数就逐字比。"""
    fold = _fold_fn(x)
    out: list[str] = []
    for ch in sorted(sol):
        if not any(ch == o or (fold and fold(o, ch)) for o in out):
            out.append(ch)
    return out


#: 字组流程的场景（`evidence.group.mode`），写进 Z 类的 `pending_reason_detail`：`<组>:<场景>`。
GROUP_SCENES = ("lift", "joint", "review")


def _group_kind(c: Cell, x: Context | None = None) -> R | None:
    """字组格 → Z 类原因（A24 Z 类梳理 11-07，sheldon 同意）。**只按解法给出了什么分**，场景（补放 lift／联合判 joint／
    复核 review）写进 detail，不再决定原因：

    - 字组已定字（admit／keep／provisional）、写法待定（form_open，归 V02）、整理本缺位（ref_missing／solo_weak）→ 不是 Z；
    - 唯一的反证是参校本〓（ref／coord_dissent 而参校字是〓）→ 不是 Z，落 R01 参校本缺字；
    - Z04 与参校本不同：给了一个字，参校本是另一个真字（补放 ref／coord_dissent，复核 group_flow_ref_dissent）；
    - Z02 判法打架：给了 ≥2 个不同字（同字异形折叠后）；
    - Z03 复核推翻：复核，一个字、与放行字不同；
    - Z07 差一路确认：一个字，但规定的第二路没确认（why=weak；联合判共字组弃权 why=joint）；
    - Z01 没把握：一个字都没给。
    真正的判序就是本函数的顺序；yaml 里 Z 类的 priority 只决定它们排在 H01 之后、N/V/L/R/P 之前。"""
    g = c.group
    if not g or "form_open" in c.codes:
        return None
    why, dec = g.get("why"), g.get("decision")
    if dec in GROUP_SETTLED:
        # 字组已经定了字，格还留在待审是后面的闸拦的（影子闸、人裁绑丢等），按后面的原因落（A24 Z05 深挖 11-06）。
        return None
    chars = _distinct({s.get("char") for s in g.get("solvers") or [] if s.get("char")}, x)
    if why in ("ref_dissent", "coord_dissent"):
        # 参校本这位是〓：不是「与参校本不同」，是参校本缺字（卿𨜊 组 235 格，A24 Z 类梳理 11-07）
        return None if ref_missing(c.ref) else R.GROUP_REF_DISSENT
    if why in ("ref_missing", "solo_weak"):
        return None
    if not chars:
        return R.GROUP_ABSTAIN
    if len(chars) >= 2:
        return R.GROUP_CONFLICT
    if dec == "demote":
        return R.GROUP_REF_DISSENT if "group_flow_ref_dissent" in c.codes else R.GROUP_DEMOTED
    if why in ("weak", "joint"):
        return R.GROUP_UNCONFIRMED
    # 其余（一个字，why=abstain／conflict 但几路只差写法等）：没有一路说了算，归没把握。
    return R.GROUP_ABSTAIN


#: 己已巳、日曰两个字组（cv groups 的组 id）。
HARD_GROUPS = frozenset({"jys", "ry"})


def _occluded(c: Cell) -> bool:
    return "occluded" in c.codes or bool(c.evidence.get("occluded"))


def _occluded_hard_ref(c: Cell) -> bool:
    """遮挡格、整理本字是己已巳日曰之一（A24 D01 深挖 11-08，第 7 轮 52 格里 19 格，看图 19/19 图上就是这一族的字）。
    印泥下库首位是噪声（唐、臯、包…），机器字是 None，所以 `_hard_pair` 的「三者全在组内」永远不中；但这一格就算没有印章也只能按文意定
    是组里哪一个，留在 D01 只会让人审白看一遍。按「为什么还停在这里」归 H01，和不遮挡的己已巳同一条路（折叠组／文意裁定）。只改分类，不放行。"""
    return _occluded(c) and c.has_ref and c.ref in HARD_CHARS and (not c.char or c.char in HARD_CHARS)


def _hard_pair(c: Cell, x: Context) -> bool:
    """极难形近：参校字／机器字／库首位全在己已巳日曰内，且①三者至少两个不同，或②（A24 Z01 深挖 11-06）三者同字但字组是 jys/ry、
    或库候选前两名都在己已巳日曰内——字形分不开，按 11-05 口径归 H01 按文意定，不再落 Z01。只改分类，不放行。"""
    if _occluded_hard_ref(c):
        return True
    s = {v for v in (c.ref, c.char, c.top) if v}
    if not s or not s <= HARD_CHARS:
        return False
    if len(s) >= 2:
        return True
    gid = (c.group or {}).get("id")
    top2 = [cd[0] for cd in c.cands[:2] if cd]
    return gid in HARD_GROUPS or (len(top2) == 2 and set(top2) <= HARD_CHARS)


def _near_pairs() -> frozenset[tuple[str, str]]:
    """cv 手工形近表 NEVER_MATCH_FAMILIES（无序对）。取不到 cv 就当空表（N01 只剩护栏一条）。"""
    global _NEAR_PAIRS
    if _NEAR_PAIRS is None:
        try:
            from .._cv import NEVER_MATCH_FAMILIES
            _NEAR_PAIRS = frozenset(tuple(sorted(p)) for p in NEVER_MATCH_FAMILIES if len(p) == 2)
        except Exception:  # noqa: BLE001 —— 没装 cv 时不挡分类
            _NEAR_PAIRS = frozenset()
    return _NEAR_PAIRS


_NEAR_PAIRS: frozenset[tuple[str, str]] | None = None


def _near_form(c: Cell, x: Context) -> bool:
    """形近护栏（A24 N01 深挖 11-06 收窄）：库护栏 conflict／never_match，或参校字与（机器字、库候选前三）里某字
    构成手工形近表里的一对。原先只要疑问码有 near_form（家族字碰巧排进候选前三）就算，约九成其实是库认不出，
    现在落到后面的 lib_sparse_dissent／ref_ocr_diff／ref_final_diff 等。只改分类，不放行。"""
    if c.evidence.get("guard") in ("conflict", "never_match"):
        return True
    if not c.has_ref:
        return False
    pairs = _near_pairs()
    others = {c.char, *(cd[0] for cd in c.cands[:3] if cd)}
    return any(o and o != c.ref and tuple(sorted((c.ref, o))) in pairs for o in others)


#: 每条原因的判法；按 yaml 的 priority 依次试。没有判法的原因（如 col_width_out_of_band 还没接）永远不中。
RULES: dict[R, Callable[[Cell, Context], bool]] = {
    R.RULING_CONFLICT: lambda c, x: "src_code_conflict" in c.codes,
    R.VISION_FLAGGED: lambda c, x: "vision_flag" in c.codes,
    R.MACHINE_CHANGED: lambda c, x: c.recheck and c.note.startswith(MACHINE_CHANGED_NOTE) and MACHINE_OVERRULE_MARK in c.note,
    R.RECHECK: lambda c, x: c.recheck,
    R.SEG_DEFECT: lambda c, x: c.cls == "seg_defect" or c.src == SELFCHECK_SRC
        or bool(c.codes & {"seg_defect", JIAZHU_UNEVEN}) or (c.frag and not c.ref),
    R.OCCLUDED_WITH_REF: lambda c, x: _occluded(c) and c.has_ref and not _occluded_hard_ref(c),
    R.OCCLUDED_NO_REF: lambda c, x: _occluded(c) and not _occluded_hard_ref(c),
    R.SEG_PAGE_UNALIGNED: lambda c, x: c.page_kind is None and not c.ref_by_design and (
        (not c.has_ref and not ref_missing(c.ref) and x.page_noref[_page(c.id)] >= PAGE_MIN)
        or (c.has_ref and c.char != c.ref and not c.group and (c.col_agree is None or c.col_agree < COL_AGREE_MAX)
            and x.page_weak[_page(c.id)] >= PAGE_MIN)),
    R.SEG_COL_UNALIGNED: lambda c, x: not c.ref and not c.ref_by_design and x.col_noref[_col(c.id)] >= COL_MIN,
    R.HARD_PAIR: _hard_pair,
    R.GROUP_ABSTAIN: lambda c, x: _group_kind(c, x) is R.GROUP_ABSTAIN,
    R.GROUP_CONFLICT: lambda c, x: _group_kind(c, x) is R.GROUP_CONFLICT,
    R.GROUP_DEMOTED: lambda c, x: _group_kind(c, x) is R.GROUP_DEMOTED,
    R.GROUP_REF_DISSENT: lambda c, x: _group_kind(c, x) is R.GROUP_REF_DISSENT,
    R.GROUP_UNCONFIRMED: lambda c, x: _group_kind(c, x) is R.GROUP_UNCONFIRMED,
    R.GROUP_WEAK: lambda c, x: False,                       # Z05 11-06 停用
    R.VARIANT_FORM_OPEN: lambda c, x: "form_open" in c.codes,
    R.GLYPH_PENDING: lambda c, x: bool(c.pua_code) and c.pua_code in x.glyph_pending,
    R.REF_LACUNA: lambda c, x: ref_missing(c.ref),
    R.LIB_MISSING: lambda c, x: c.lib_miss,
    # 要有整理本字才算 L05（A24 L05 深挖 11-06，sheldon 同意）：无对位的糊格（框线碎片、并格、圈点）不是「库首位错」，落到后面的 R02
    R.GARBLE_GATE: lambda c, x: bool(c.codes & _GARBLE) and c.has_ref,
    R.REF_GAP: lambda c, x: not c.ref and not c.ref_by_design,
    R.VARIANT_PAIR: _variant_with_ref,
    R.NEAR_FORM_GUARD: _near_form,
    R.LIB_SPARSE_AGREE: lambda c, x: False,                 # L03 11-07 停用，并入 L02（不论机器字是否＝参校字；A23，sheldon 11-07）
    R.LIB_SPARSE_DISSENT: lambda c, x: _sparse(c, x),
    R.REF_OCR_DIFF: lambda c, x: c.ref_op == "replace" or "replace_align" in c.codes,
    R.LIB_UNRECOGNIZED: lambda c, x: (c.has_ref and c.char == c.ref) or (c.ref_by_design and not c.has_ref),
    R.REF_FINAL_DIFF: lambda c, x: c.has_ref and c.char != c.ref,
}


def _ordered() -> list[R]:
    return sorted((r for r in R if r is not R.UNKNOWN), key=lambda r: specs()[r].priority)


#: 切坏格细分（SJ 史記第 8 轮切坏检测，11-04 定）：作 seg_defect 的 pending_reason_detail，不新增取值。
#: merged 两字并一格；clipped 字被切掉一边或半截；bleed 邻格笔画溢入；frame_residue 框线残笔当成笔画。
#: jiazhu_uneven（史記雙行小注逐步切 cv#1011，11-04 A31 定）：夹注两行分法不是 ⌈N/2⌉／⌊N/2⌋、按整理本切的格，要人核；
#: 格上带 doubt 码 `jiazhu_uneven`（或 seg_kind=jiazhu_uneven）即归 seg_defect，细分记 jiazhu_uneven。
JIAZHU_UNEVEN = "jiazhu_uneven"
#: 出单同字对照自检（B1③，A20／A31 11-05 定）：单上 `src` 为它的格是自检从已放行格里挑出来改送人审的，
#: 原因归 seg_defect，pending_reason_detail 写 `SELFCHECK_DETAIL + seg_kind`（统计按这个前缀单独数）。
SELFCHECK_SRC = "seg_selfcheck"
SELFCHECK_DETAIL = "同字对照自检："
SEG_KINDS = ("merged", "clipped", "bleed", "frame_residue", JIAZHU_UNEVEN)


def seg_kind_of(c: Cell) -> str:
    """切坏细分：单上的 `seg_kind` 优先，其次产物 evidence.seg_kind，再次 doubt 码 jiazhu_uneven；不在 SEG_KINDS 里的不认。"""
    k = c.seg_kind or (c.evidence or {}).get("seg_kind")
    if k in SEG_KINDS:
        return k
    if JIAZHU_UNEVEN in c.codes:
        return JIAZHU_UNEVEN
    if c.bleed:
        return "bleed"
    return "clipped" if c.frag and not c.ref else ""


#: 「少见的字」细分（A23，sheldon 11-04 定本书字样标注归书 Project）：作 lib_missing 的 pending_reason_detail，
#: 写成 ``<细分>:<整理本字>``，不新增取值。lib_missing 的意思是「库里没有像这一格的刻例」（glyph_match verdict=diff），
#: 不等于库里没有这个字；按整理本字在本书库、借来库里各有几例分开派单：
#:   ref_blank           整理本这一位没字（语料漏字／对位问题，不是字形库的事，转 A24／书 Project）
#:   all_zero            本书、借来库都没有这个字（真缺字：首例人裁入库）
#:   own_zero_borrow_has 本书没有、借来库有（借来的字样不像这本：本书字样标注，归书 Project）
#:   own_has             本书已有这个字的刻例，这一格仍不像（多半淡印、切坏或形近：看图）
LIB_MISSING_KINDS = ("ref_blank", "all_zero", "own_zero_borrow_has", "own_has")


def lib_missing_kind(c: Cell, ctx: Context | None) -> str:
    """lib_missing 细分；没给库（``ctx.lib_split``）就不分（空串）。"""
    if not c.has_ref:
        return "ref_blank" if not c.ref else ""
    if ctx is None or ctx.lib_split is None:
        return ""
    own, borrowed = ctx.lib_split(c.ref)
    return "own_has" if own else ("own_zero_borrow_has" if borrowed else "all_zero")


#: 「库认不出」细分（A23，sheldon 11-06「理清 L04 流程」）：作 lib_unrecognized 的 pending_reason_detail，写成 ``<细分>:<整理本字>``，
#: 不新增取值。L04 是兜底：有参校字、机器字＝参校字、前面各条都没中。三书看图（ai-team 待审原因深挖/L04-库认不出.md）这样的格
#: 停下来的原因只有几种，对着 seed_admit 的 ``ref_lib_coord``（参校字＝库首位＝本格字就放）逐条看是哪一关没过，按先后取第一个：
#:   lib_diff       5a 判 diff（cov<0.85，带 lib_miss 码）、本书库已有这个字（≥3 例）：印糊整字，原来落 L01（A23 11-07 起归 L04／L05）
#:   lib_other      库首位不是参校字（多是糊墨，库认成笔画少的形近字，如 畫→書、全→今）：只能看图
#:   human_unbound  人裁绑丢、旧裁字与本格字不同（锚点漂移）：重锚或作废那条人裁事件
#:   doubt_blocked  带 ref_lib_coord 白名单以外的疑问码（如 coord_conflict）：看那个疑问
#:   low_cov        库首位＝参校字，但 cov < LIB_UNREC_COV（糊墨／印淡，殿本 ref_lib_coord 门槛）
#:   near_rival     库首位＝参校字，但另有别的字紧咬（差 < LIB_UNREC_GAP）
#:   clear          以上都没有：按 ref_lib_coord 该放，没放是因为这本书／这版单没开它（看单子出自哪版 cv、册 yaml 开没开）
#: 门槛与白名单取殿本 ``ref_lib_coord`` 的口径（cv seed_admit ``ref_lib_coord_cov/gap``、``_REF_LIB_COORD_DOUBTS``）；
#: 开了 ``reference_trust`` 的书（史記）门槛更松，这里的 low_cov／near_rival 对它偏严，只作分档，不作判定。
#:   no_ref         本页本就没配参校本（``ref_by_design``）：无参校字可比，库 unsure／上下文 margin 不够才停下来，看图
LIB_UNREC_KINDS = ("lib_diff", "lib_other", "human_unbound", "doubt_blocked", "low_cov", "near_rival", "clear", "no_ref")
LIB_UNREC_COV, LIB_UNREC_GAP = 0.96, 0.01
#: cv ``_REF_LIB_COORD_DOUBTS`` 里的码（中文说明「库 unsure」「上下文 margin 不足」等不是码，doubt_codes 本来就不取）。
#: ``context_page_end`` 由 cv #1184 后续 PR 加入（A31 11-06 裁定），这里先认。
REF_LIB_COORD_OK_CODES = frozenset({"ctx_guard_ref", "context_variant_form", "group_flow_abstain", "group_flow_joint",
                                    "group_flow_ref_dissent", "group_flow_coord_dissent", "human_unbound",
                                    "lane_coord_fallback", "near_form", "context_page_end"})


def lib_unrecognized_kind(c: Cell, ctx: Context | None = None) -> str:
    """lib_unrecognized 细分（见 ``LIB_UNREC_KINDS``）。给了 ``ctx.are_variants`` 时，紧咬的对手是参校字的异体不算（同 cv 按语义比）。"""
    if c.lib_miss:
        return "lib_diff"
    if c.ref_by_design and not c.has_ref:
        h = (c.evidence or {}).get("human_unbound") or {}
        return "human_unbound" if "human_unbound" in c.codes and h.get("char") and h.get("char") != c.char else "no_ref"
    if not c.cands or c.top != c.ref:
        return "lib_other"
    h = (c.evidence or {}).get("human_unbound") or {}
    if "human_unbound" in c.codes and h.get("char") and h.get("char") != c.char:
        return "human_unbound"
    if c.codes - REF_LIB_COORD_OK_CODES:
        return "doubt_blocked"
    top = float(c.cands[0][1])
    if top < LIB_UNREC_COV:
        return "low_cov"
    same = (ctx.are_variants if ctx is not None and ctx.are_variants else (lambda a, b: False))
    if any(x and x != c.ref and not same(c.ref, x) and top - float(v) < LIB_UNREC_GAP for x, v, *_ in c.cands[1:6]):
        return "near_rival"
    return "clear"


def detail_of(reason: R, c: Cell, ctx: Context | None = None) -> str:
    """给人看的一点细节（字对、组 id、页号），不是判定依据。"""
    if reason is R.SEG_DEFECT:
        return SELFCHECK_DETAIL + seg_kind_of(c) if c.src == SELFCHECK_SRC else seg_kind_of(c)
    if reason is R.LIB_MISSING:
        k = lib_missing_kind(c, ctx)
        return f"{k}:{c.ref or ''}" if k else (c.ref or "")
    if reason in (R.SEG_PAGE_UNALIGNED,):
        return _page(c.id)
    if reason in (R.SEG_COL_UNALIGNED,):
        return _col(c.id)
    if reason.name.startswith("GROUP_") and c.group:
        mode = c.group.get("mode")
        return f"{c.group.get('id') or ''}:{mode}" if mode in GROUP_SCENES else str(c.group.get("id") or "")
    if reason in (R.HARD_PAIR, R.NEAR_FORM_GUARD, R.VARIANT_PAIR):
        return "/".join(sorted({v for v in (c.ref, c.char, c.top) if v}))
    if reason in (R.REF_OCR_DIFF, R.REF_FINAL_DIFF, R.LIB_SPARSE_DISSENT):
        return f"{c.ref or ''}>{c.char or ''}"
    if reason is R.GLYPH_PENDING:
        return c.pua_code or ""
    if reason is R.LIB_UNRECOGNIZED:
        return f"{lib_unrecognized_kind(c, ctx)}:{c.ref or ''}"
    if reason is R.LIB_SPARSE_AGREE:
        return c.ref or ""
    if reason is R.REF_LACUNA and c.ref and any(0xE000 <= ord(x) <= 0xF8FF or ord(x) >= 0xF0000 for x in c.ref):
        return "/".join(f"U+{ord(x):04X}" for x in c.ref)          # 私用码参校字写码位（同一码位跨书意思不同，不能拿别书码表定字）
    if reason is R.RULING_CONFLICT and "human_unbound" in c.codes:
        h = (c.evidence or {}).get("human_unbound") or {}
        return f"human_unbound:{h.get('char') or ''}>{c.char or ''}"
    return ""


def _first_entry(c: Cell, ctx: Context) -> bool:
    """参校字在本书库里一例都没有（`lib_own_n`＝0）：这一格是它第一次进库。"""
    return lib_own_n(c, ctx) == 0


def classify(c: Cell, ctx: Context) -> R:
    """一格 → 原因。按 priority 第一个命中的；都不中 `UNKNOWN`。

    字形库类 L01–L04 的边界（A23 L03 深挖 11-06、第 6 轮梳理 11-07，sheldon 同意）只看参校字在本书库里的刻例数 n（`lib_own_n`）：

        n = 0          → L01 lib_missing        第一次进库（不论机器字；借来的刻例不算）
        1 ≤ n ≤ 2      → L02 lib_sparse_dissent 刻例太少（不论机器字是否＝参校字；L03 11-07 起停用并入）
        n ≥ 3          → 带 lib_miss 码（5a 判 diff）的印糊整字：有乱码闸码落 L05，否则落 L04（细分 lib_diff）；
                         不带 lib_miss 码的照旧往后落（多半 L04 库认不出、P01／P02）

    带 `lib_miss` 码的格：整理本这一位没字（ref_blank）不是「库里没有它」，不归 L01，往后落（多半 R02）；
    没给字形库（n 是 None）时按老办法一律 L01。其余 L01–L04 的格不受影响。
    L04 里旧人裁锚点漂移（细分 human_unbound，数据问题不是库问题）改归 X01 裁定有冲突。"""
    for r in _ordered():
        rule = RULES.get(r)
        if not (rule and rule(c, ctx)):
            continue
        if r is R.LIB_SPARSE_DISSENT and _first_entry(c, ctx):
            return R.LIB_MISSING
        if r is R.LIB_MISSING:
            if not c.has_ref:
                continue                                      # 整理本这位没字：不是库的事，往后落
            n = lib_own_n(c, ctx)
            if n is not None and n >= 1:
                if n <= LIB_SPARSE:
                    return R.LIB_SPARSE_DISSENT
                if c.codes & _GARBLE:
                    return R.GARBLE_GATE
                r = R.LIB_UNRECOGNIZED
        if r is R.LIB_UNRECOGNIZED and lib_unrecognized_kind(c, ctx) == "human_unbound":
            return R.RULING_CONFLICT
        if r is R.LIB_UNRECOGNIZED and c.bleed and lib_unrecognized_kind(c, ctx) == "lib_diff":
            return R.SEG_DEFECT                               # 印糊整字里带 boundary_ink 旗的是溢墨切坏，归切分 S04（A22 判据，A24 11-08）
        return r
    return R.UNKNOWN


# ── 读产物 ─────────────────────────────────────────────────────────────

def _load_layer(path: Path, key: str) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))[key]
    except (OSError, KeyError, ValueError):
        return None


def align_for_seed(seed: dict, align: dict | None) -> dict | None:
    """史記 `alt_cut`：准入改用备选切法的列（seed_admit `alt_cols`，退回 align_ref 的），格号与 align_ref 现役
    `chars`／`coord`（主切法）不对应，这些列改读 align_ref `alt_draft` 的坐标对位、丢掉现役对位字。
    没有备选列就原样返回（殿本等不受影响）。"""
    if not align:
        return align
    cols = set(seed.get("alt_cols") or align.get("alt_cols") or [])
    draft = align.get("alt_draft") or {}
    if not cols or not draft:
        return align
    col_of = lambda cid: int(cid.split(":")[2])
    out = dict(align)
    out["chars"] = [c for c in align.get("chars", []) if col_of(c["id"]) not in cols]
    out["coord"] = [c for c in align.get("coord") or [] if col_of(c["id"]) not in cols] + \
                   [c for c in draft.get("coord") or [] if col_of(c["id"]) in cols]
    return out


def _page_kind(root: Path, name: str) -> str | None:
    """本页非正文页型：border_detect_gate 的 page_type 不是 body，或 row_segment 有列打了 roster（职名页分支）；正文页 None。"""
    bg = _load_layer(root / "border_detect_gate" / name, "border_detect_gate_manifest") or {}
    if bg.get("page_type") and bg["page_type"] != "body":
        return str(bg["page_type"])
    rs = _load_layer(root / "row_segment" / name, "cells") or {}
    if any("roster" in (c.get("flags") or []) for c in rs.get("columns") or []):
        return "roster"
    return None


#: align_ref 的 note：本册没配整理本／证人，或册里没写 references 读不到（cv align_ref `未配置整理本`／`未配置证人`／`整理本读不到`；QTW 11-08：全唐文 002 的 208 页都是「整理本读不到」）。
NOREF_NOTES = ("未配置整理本", "未配置证人", "整理本读不到")


def _ref_by_design(root: Path, name: str) -> bool:
    """本页的对位层说「没配参校本」（不是锚不上、不是钉页无此页）→ 无对位是设计。"""
    ar = _layer_note(root, name)
    return any(n in ar for n in NOREF_NOTES)


def _layer_note(root: Path, name: str) -> str:
    return str((_load_layer(root / "align_ref" / name, "align_ref") or {}).get("note") or "")


def _bleed_ids(root: Path, name: str) -> set[str]:
    """本页 cell_shrink 打了 boundary_ink 旗的格 id。"""
    shr = _load_layer(root / "cell_shrink" / name, "char_index") or {}
    return {ch["id"] for key in ("columns", "alt_columns") for col in shr.get(key) or []
            for ch in col.get("chars") or [] if "boundary_ink" in (ch.get("flags") or [])}


def _frag_ids(root: Path, name: str) -> set[str]:
    """本页的碎片格 id：cell_shrink 的格框边长比本页同类格（夹注／非夹注分开）中位数小得多，或长宽比悬殊。"""
    shr = _load_layer(root / "cell_shrink" / name, "char_index") or {}
    boxes: dict[str, tuple[float, float, bool]] = {}
    for key in ("columns", "alt_columns"):
        for col in shr.get(key) or []:
            for ch in col.get("chars") or []:
                w, h = ch.get("width"), ch.get("height")
                if w and h and ch.get("id") not in boxes:
                    boxes[ch["id"]] = (float(w), float(h), ch.get("step3_kind") == "jiazhu")
    med: dict[bool, float] = {}
    for jz in (False, True):
        v = sorted((w * h) ** .5 for w, h, j in boxes.values() if j == jz)
        if len(v) >= 5:
            med[jz] = v[len(v) // 2]
    out = set()
    for cid, (w, h, jz) in boxes.items():
        if jz not in med:
            continue
        if (w * h) ** .5 < FRAG_REL * med[jz] or min(w, h) / max(w, h) < FRAG_ASPECT:
            out.add(cid)
    return out


def book_cells(products_dir, book: str, bigrams: Counter | None = None) -> dict[str, Cell]:
    """全册没放行的格（排除名单除外）→ `Cell`。格号不带册前缀（同 `causes.book_causes`）。

    给了 `bigrams` 就顺手把全册整理本字（按页、按列序连起来）的相邻二字计数加进去，给 `ref_suspect` 用。"""
    root = Path(products_dir) / book
    out: dict[str, Cell] = {}
    for f in sorted((root / "seed_admit").glob("p*.json")):
        seed = _load_layer(f, "seed_admit")
        if not seed:
            continue
        align = align_for_seed(seed, _load_layer(root / "align_ref" / f.name, "align_ref")) or {}
        gm = _load_layer(root / "glyph_match" / f.name, "glyph_match") or {}
        ref = {c["id"]: (c.get("align_char"), c.get("align_op")) for c in align.get("chars", [])}
        for c in align.get("coord") or []:
            if c.get("ref_char") and c["id"] not in ref:
                ref[c["id"]] = (c["ref_char"], "coord")
        cands = {c["id"]: c.get("candidates") or [] for col in gm.get("columns", []) for c in col.get("chars", [])}
        kind = _page_kind(root, f.name)
        by_design = _ref_by_design(root, f.name)
        frags = _frag_ids(root, f.name)
        bleeds = _bleed_ids(root, f.name)
        seq = [(ch["id"], (ref.get(ch["id"], (None, None))[0] or "□")) for col in seed.get("columns", [])
               for ch in col.get("chars", []) if "excluded" not in (ch.get("doubts") or [])]
        at = {cid: i for i, (cid, _) in enumerate(seq)}
        if bigrams is not None:
            text = "".join(c for _, c in seq)
            bigrams.update(text[i:i + 2] for i in range(len(text) - 1))
        for col in seed.get("columns", []):
            hit = [ch.get("char") == ref[ch["id"]][0] for ch in col.get("chars", [])
                   if "excluded" not in (ch.get("doubts") or []) and ref.get(ch["id"], (None,))[0]
                   and not ref_missing(ref[ch["id"]][0])]
            agree = sum(hit) / len(hit) if hit else None
            for ch in col.get("chars", []):
                if ch.get("admit") or "excluded" in (ch.get("doubts") or []):
                    continue
                cid = ch["id"]
                r, op = ref.get(cid, (None, None))
                out[cid.split(":", 1)[1]] = Cell(id=cid, char=ch.get("char"), ref=r, ref_op=op, cands=cands.get(cid, []),
                                                 doubts=list(ch.get("doubts") or []), evidence=dict(ch.get("evidence") or {}),
                                                 pua_code=(ch.get("evidence") or {}).get("pua_code") or ch.get("pua_code"),
                                                 col_agree=agree, page_kind=kind, ref_by_design=by_design, frag=cid in frags, bleed=cid in bleeds)
                if cid in at:          # 整理本前后文：缺字格回查私用码；其余格给 ref_suspect 比上下文
                    i = at[cid]
                    out[cid.split(":", 1)[1]].ref_left = "".join(c for _, c in seq[max(0, i - 20):i])
                    out[cid.split(":", 1)[1]].ref_right = "".join(c for _, c in seq[i + 1:i + 21])
    return out


def lib_counts(glyph_db) -> Callable[[str], int] | None:
    """字形库 SQLite（`output/glyph.db`）→ 每字刻例数（`glyphs.n_confirmed` 求和）。库不在就返回 None（不猜）。"""
    import sqlite3
    p = Path(glyph_db)
    if not p.exists() or p.stat().st_size == 0:
        return None
    n: Counter = Counter()
    con = sqlite3.connect(str(p))
    try:
        for ch, k in con.execute("select char, sum(n_confirmed) from glyphs group by char"):
            n[ch] += k or 0
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return lambda ch: n.get(ch, 0)


def lib_own_counts(glyph_db) -> Callable[[str], int] | None:
    """字形库 SQLite → 每字**本书版本**的刻例数（`glyphs.n_confirmed`，`edition_tag`＝`meta.book_edition`）。
    没有 `book_edition`（老库）就退回所有版本求和，同 `lib_counts`。库不在或读不了返回 None（不猜）。"""
    import sqlite3
    p = Path(glyph_db)
    if not p.exists() or p.stat().st_size == 0:
        return None
    n: Counter = Counter()
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        row = None
        if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone():
            row = con.execute("SELECT value FROM meta WHERE key='book_edition'").fetchone()
        if row and row[0]:
            q = con.execute("select char, sum(n_confirmed) from glyphs where edition_tag=? group by char", (row[0],))
        else:
            q = con.execute("select char, sum(n_confirmed) from glyphs group by char")
        for ch, k in q:
            n[ch] += k or 0
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return lambda ch: n.get(ch, 0)


def lib_split_counts(glyph_db) -> Callable[[str], tuple[int, int]] | None:
    """字形库 SQLite → 字 → (本书刻例数, 借来刻例数)。按 exemplars 数，借来的看 ``borrowed`` 表，字体域不算。
    库不在或读不了返回 None（不猜）。"""
    import sqlite3
    p = Path(glyph_db)
    if not p.exists() or p.stat().st_size == 0:
        return None
    own: Counter = Counter()
    bor: Counter = Counter()
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        has_b = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='borrowed'").fetchone()
        flag = ("e.instance_id IN (SELECT instance_id FROM borrowed)" if has_b else "0")
        for ch, b, k in con.execute(
                f"""SELECT g.char, {flag} AS b, count(*) FROM exemplars e JOIN glyphs g USING(glyph_id)
                    JOIN instances i USING(instance_id) JOIN sources s USING(source_id)
                    WHERE s.kind != 'font' GROUP BY g.char, b"""):
            (bor if b else own)[ch] += k
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return lambda ch: (own.get(ch, 0), bor.get(ch, 0))


def _default_are_variants():
    try:
        from .._cv import are_variants as _av
        return _av
    except Exception:  # noqa: BLE001 —— 异体表读不到就不判异体，落到后面的规则
        return None


#: cv 暂归一表之外、同一个字的写法（官宫宮 组里 宫宮 同字；cv guan 组 forms 没单列）
_EXTRA_SAME_WRITING = (frozenset("宫宮"),)


def _default_same_writing():
    """同一个字的不同写法：cv `PROVISIONAL[*].forms`（暂归一表，sheldon 定的同义写法）的并集判等。取不到 cv 返回 None（退回 are_variants）。"""
    try:
        from .._cv import groups_registry
        PROVISIONAL = groups_registry.PROVISIONAL
    except Exception:  # noqa: BLE001
        return None
    sets = [frozenset(p.forms) for p in PROVISIONAL.values()] + list(_EXTRA_SAME_WRITING)

    def same(a: str, b: str) -> bool:
        return a == b or any(a in f and b in f for f in sets)
    return same


def _default_edge_tier():
    """cv 异体边分型；旧 cv 没有就返回 None（V01 退回只看有没有边）。"""
    try:
        from .._cv import edge_tier as _et
        return _et
    except Exception:  # noqa: BLE001
        return None


#: 待收字登记表（私用码表里「已判定待收」的永久编号，一项一个 `来源:码位`）放在数据目录 `config/pua/glyph_pending_codes.json`
#: （`{"codes": [...]}`，随 `guji db sync` 进中心库；A31 11-05 定：不放语料版本，免得动 corpus 指纹、触发 CorpusDrift）。
#: 读不到＝空表＝一个都不算，全走 `ref_lacuna`，和改前一样。
GLYPH_PENDING_REL = ("config", "pua", "glyph_pending_codes.json")


def load_glyph_pending(data_root: Path | str | None = None) -> frozenset[str]:
    """读待收字登记表；数据目录取不到、文件不在、读不了都返回空集（不猜）。"""
    try:
        if data_root is None:
            from .._cv import data_root as _data_root     # cv 的数据目录（中心库工作区＝数据目录），不靠 corpus 路径推
            data_root = _data_root()
        f = Path(data_root).joinpath(*GLYPH_PENDING_REL)
        return frozenset(json.loads(f.read_text(encoding="utf-8")).get("codes") or [])
    except Exception:  # noqa: BLE001
        return frozenset()


#: 私用码码表（A24 11-06，一行一码：code「来源:码位」、verdict char/not_char/pending/open、char、orig、variant、cands…），
#: 和登记表同在数据目录 `config/pua/`，随 `guji db sync` 进中心库，不进指纹。现在只读、只在出单统计里报数，
#: **不参与原因判法**；登记表 `glyph_pending_codes.json` 由它导出，两份并存。
PUA_TABLE_REL = ("config", "pua", "pua_table.jsonl")


def load_pua_table(data_root: Path | str | None = None) -> dict[str, dict]:
    """读私用码码表 → `{code: 行}`；数据目录取不到、文件不在返回空表，坏行跳过（不猜）。"""
    try:
        if data_root is None:
            from .._cv import data_root as _data_root
            data_root = _data_root()
        text = Path(data_root).joinpath(*PUA_TABLE_REL).read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, dict] = {}
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("code"):
            out[str(row["code"])] = row
    return out


def pua_table_stats(table: dict[str, dict], glyph_pending: frozenset[str]) -> Counter:
    """码表的出单报数：总码数、各 verdict 数、登记表里有但码表不是 pending 的码数（两份应一致，不一致要报）。"""
    n: Counter = Counter()
    n["pua_table_codes"] = len(table)
    for row in table.values():
        n[f"pua_table_{row.get('verdict') or 'none'}"] += 1
    if table:
        n["pua_table_registry_mismatch"] = sum(1 for c in glyph_pending if (table.get(c) or {}).get("verdict") != "pending")
    return n


_RESOLVERS: dict[str, Callable[[str, str], str | None] | None] = {}


def pua_resolver(corpus: Path | str | None = None) -> Callable[[str, str], str | None] | None:
    """出单时用的私用码回查函数 `(整理本前文, 后文) -> "daizhige:U+XXXX" | None`；
    cv 没有 `utils.pua_lookup`（旧 cv）或源文件读不到时返回 None，调用方退回 `ref_lacuna`。"""
    try:
        if corpus is None:
            from .._cv import corpus_dir
            corpus = corpus_dir()
        key = str(Path(corpus).resolve())
    except Exception:  # noqa: BLE001
        return None
    if key not in _RESOLVERS:            # 五个源 jsonl 约 29 MB，建一次索引，同一语料目录只建一次
        _RESOLVERS[key] = _build_resolver(Path(corpus))
    return _RESOLVERS[key]


def _build_resolver(corpus: Path) -> Callable[[str, str], str | None] | None:
    try:
        from .._cv import PuaIndex, resolve_pua_code
        files = sorted((corpus / "daizhige").glob("[0-9]*.jsonl"))
        if not files:
            return None
        idx = PuaIndex.from_source(files)
    except Exception:  # noqa: BLE001
        return None
    return lambda left, right: resolve_pua_code(idx, left, right)


#: 「疑整理本错」只读标记（A32 D01 深挖 11-06 提、协调者 11-06 定做；**只排序，不放行、不改字、不改原因**）：
#: 库首位字和整理本字各放进这一格的整理本上下文（前一字＋X、X＋后一字），在本册整理本里数相邻二字出现次数，
#: 整理本这一格自己的两次不算。库首位明显更通顺写 `ref`（疑整理本错，人审页置顶），整理本更通顺写 `lib`（疑库错，排后快过），
#: 分不出不写。整理本真错率约 3–6%（D01、L02、X01 实测），所以这只是让真错先被看到。
REF_SUSPECT_MIN = 2         # 库首位的上下文次数至少这么多才标「疑整理本错」
REF_SUSPECT_FIELD = "ref_suspect"


def ref_suspect(c: Cell, bigrams: Counter | None) -> str:
    """'ref'＝疑整理本错（库首位更通顺）；'lib'＝疑库错（整理本更通顺）；''＝分不出或不适用。"""
    if not bigrams or not c.has_ref or not c.top or c.top == c.ref or ref_missing(c.top):
        return ""
    left, right = c.ref_left[-1:], c.ref_right[:1]
    if not (left or right):
        return ""

    def score(x: str, self_ref: bool) -> int:
        n = 0
        for g in ((left + x) if left else "", (x + right) if right else ""):
            if g:
                n += max(0, bigrams[g] - (1 if self_ref else 0))
        return n

    s_ref, s_top = score(c.ref, True), score(c.top, False)
    if s_top >= REF_SUSPECT_MIN and s_top > 2 * s_ref:
        return "ref"
    if s_ref > s_top:
        return "lib"
    return ""


def reasons_for_pending(doc: dict, products_dir, book: str, *, glyph_db=None, are_variants=None, glyph_pending=None,
                        pua_resolve=None, stats=None, suspect=True) -> dict[str, tuple[R, str]]:
    """待审单 `doc` 的每格 → (原因, 细节)。产物里找不到的格（如复审格）只用单上的字段判，判不出就 `unknown`。

    `suspect`（缺省开）：顺手在 `doc` 的格上写只读标记 `ref_suspect`（见 `ref_suspect()`；分不出就删掉旧值），
    `stats` 里记 `ref_suspect_ref`／`ref_suspect_lib`。只排序用，不影响原因。

    `stats`（可选 Counter）：`glyph_pending_by_window` 记「按窗口回查判成待收字」的格数——待收字不派人审，
    回查错了格会被悄悄藏起来，出单报告要单列这个数，第一次上线抽 20 格看图。"""
    tier = same_writing = None
    if are_variants is None:
        are_variants, tier = _default_are_variants(), _default_edge_tier()
        same_writing = _default_same_writing()
    bigrams: Counter | None = Counter() if suspect else None
    prod = book_cells(products_dir, book, bigrams=bigrams)
    cells: list[Cell] = []
    for x in doc.get("cells", []):
        key = x["cell"].split(":", 1)[1] if x["cell"].count(":") >= 3 else x["cell"]
        c = prod.get(key) or Cell(id=f"{book}:{key}", char=None, ref=((x.get("ref") or {}).get("c") or x.get("refc")),
                                  doubts=list(x.get("why") or []))
        c.recheck, c.note, c.cls = bool(x.get("recheck")), str(x.get("note") or ""), x.get("cls")
        if x.get("seg_kind"):
            c.seg_kind = str(x["seg_kind"])
        if x.get("src"):
            c.src = str(x["src"])
        if x.get("pua_code"):
            c.pua_code = str(x["pua_code"])
        cells.append(c)
    if glyph_pending is None:
        glyph_pending = load_glyph_pending()
        if not glyph_pending and stats is not None:
            stats["glyph_pending_registry_missing"] = 1   # 登记表没读到：全走 ref_lacuna，出单报告要提示
    if stats is not None:       # 码表只读报数，不影响判法
        stats.update(pua_table_stats(load_pua_table(), glyph_pending))
    if glyph_pending:           # 登记表是空的就不必回查（和改前一样，没有任何变化）
        if pua_resolve is None:
            pua_resolve = pua_resolver()
        for c in cells:
            if (pua_resolve and not c.pua_code and ref_missing(c.ref) and (c.ref_left or c.ref_right)
                    and not any(0xE000 <= ord(q) <= 0xF8FF or ord(q) >= 0xF0000 for q in c.ref)):    # 参校字本身是私用码（史記）不回查殿本源（A24 R01）
                c.pua_code = pua_resolve(c.ref_left, c.ref_right)
                if c.pua_code and c.pua_code in glyph_pending and stats is not None:
                    stats["glyph_pending_by_window"] += 1    # 按窗口回查判成待收字的格数（风险提示：回查错了格会被悄悄藏起来，出单报告要单列）
    ctx = build_context(cells, lib_n=lib_counts(glyph_db) if glyph_db else None, are_variants=are_variants,
                        lib_split=lib_split_counts(glyph_db) if glyph_db else None, glyph_pending=glyph_pending,
                        lib_own=lib_own_counts(glyph_db) if glyph_db else None,
                        edge_tier=tier, same_writing=same_writing)
    out = {}
    for x, c in zip(doc.get("cells", []), cells):
        r = classify(c, ctx)
        out[x["cell"]] = (r, detail_of(r, c, ctx))
        if suspect:
            v = ref_suspect(c, bigrams)
            if v:
                x[REF_SUSPECT_FIELD] = v
                if stats is not None:
                    stats[f"ref_suspect_{v}"] += 1
            else:
                x.pop(REF_SUSPECT_FIELD, None)
    return out


def stamp(doc: dict, reasons: dict[str, tuple[R, str]]) -> Counter:
    """把原因写进待审单每格：`pending_reason`（必有，判不出 `unknown`）、`pending_reason_detail`（有才写）。返回计数。"""
    n: Counter = Counter()
    for x in doc.get("cells", []):
        r, d = reasons.get(x["cell"], (R.UNKNOWN, ""))
        x["pending_reason"] = r.value
        if d:
            x["pending_reason_detail"] = d
        else:
            x.pop("pending_reason_detail", None)
        n[r.value] += 1
    return n


def stamp_cards(cards: list[dict], cells: list[Cell], *, glyph_db=None, are_variants=None, glyph_pending=()) -> None:
    """控制台待审卡（`review/cards.py`）每张带 `pending_reason`／`pending_reason_detail`，与出单同一套判法。

    `cells` 与 `cards` 一一对应；整页／整列对不上按这批卡自己数（与待审单按整单数同口径）。"""
    tier = same_writing = None
    if are_variants is None:
        are_variants, tier = _default_are_variants(), _default_edge_tier()
        same_writing = _default_same_writing()
    ctx = build_context(cells, lib_n=lib_counts(glyph_db) if glyph_db else None, are_variants=are_variants,
                        lib_split=lib_split_counts(glyph_db) if glyph_db else None, glyph_pending=glyph_pending,
                        lib_own=lib_own_counts(glyph_db) if glyph_db else None,
                        edge_tier=tier, same_writing=same_writing)
    for card, c in zip(cards, cells):
        r = classify(c, ctx)
        card["pending_reason"] = r.value
        d = detail_of(r, c, ctx)
        if d:
            card["pending_reason_detail"] = d
