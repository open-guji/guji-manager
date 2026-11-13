"""少见字人审分层：每个待人审格落进 快审／高把握／低把握／难认字／对位可疑 之一。

逻辑固定在这里，书与书之间只调 `BookParams`（参校本可信度、每列字数），不在出页时临场想规则。
规矩来源与回测见 doc/01-粗校/开书/字形快速入库.md 第三节「分层规则（代码）」。

| 层 | 去向 | 条件（按顺序判，先中先走） |
|---|---|---|
| hard  | 难认字页（整列图＋上下文） | 没有参校本字；或 5b 首位分 < `hard_below`；或参校本字是 一二三／己已巳／日曰（要看上下文） |
| align | 上低把握页（预选 5b 首位，不预选参校本字），同时列给切分线查对位 | 参校本可信度 ≥ high，参校本字不在 5b 前三，而 5b 首位分 ≥ `align_min`（图认得清、却不是参校本字：多是参校本字对到了邻格） |
| quick | 快审单（char_grid，只点错） | 按 `ref_trust` 定的快审条件（下表）；且不是列首／列尾／双行小注格，参校本字不在形近组 |
| high  | 高把握（char_card 3 格一卡） | (库首位＝5b 首位 或 5b 领先第二名 ≥ .03) 且 cov ≥ .90 且库里该字有刻例 |
| low   | 低把握（一格一卡，不带上下文） | 其余 |

快审条件随参校本可信度：

| ref_trust | 快审条件 | 依据 |
|---|---|---|
| very_high | 5b 首位＝参校本字，5b 首位分 ≥ .90，库首位 cov ≥ .90 | 史記 r53（11-13）人点 216 格回测：53 格中 1 格不对（切分） |
| high      | 同上，5b 首位分 ≥ .93 | 同批 47 格 0 错 |

库首位 cov 不论首位是哪个字，都当「这格图干不干净」用：cov < .90 的格多是切坏、带框线、墨糊。
「参校本字在 5b 前三」（不要求首位）回测 83 格错 7（8%），不用。
| medium    | 库首位＝5b 首位＝参校本字，cov 在 .90–.95，库里有刻例 | 全唐文 H-cold：97.5% |
| none      | 不出快审（没有参校本可比） | |
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..review_triage.cells import COL_LEN, skip_reason
from ..review_triage.rules import is_han

TRUST_LEVELS = ("none", "medium", "high", "very_high")
CONTEXT_CHARS = set("一二三己已巳日曰")          # 用户定：只凭字形不判，一律进难认字看上下文
NEAR_GROUPS = ("人入八", "十士土干", "木本末未", "戊戌戍", "上卜", "宫官", "目日", "未末")
LAYERS = ("quick", "high", "low", "hard", "align")


@dataclass
class BookParams:
    ref_trust: str = "medium"          # 参校本可信度：none / medium / high / very_high
    col_len: int | None = COL_LEN      # 每列字数，判列尾；列长不定的书给 None
    hard_below: float = 0.90           # 5b 首位分低于此 → 难认字
    align_min: float = 0.93            # 参校本字不在 5b 前三、5b 首位分 ≥ 此 → 对位可疑
    near_pairs: frozenset = field(default_factory=frozenset)   # 额外形近对（cv NEVER_MATCH_FAMILIES）

    def __post_init__(self):
        if self.ref_trust not in TRUST_LEVELS:
            raise ValueError(f"ref_trust 只能是 {TRUST_LEVELS}，收到 {self.ref_trust!r}")

    @property
    def near_chars(self) -> set[str]:
        s = {c for g in NEAR_GROUPS for c in g}
        for p in self.near_pairs:
            s |= set(p)
        return s


@dataclass
class Cell:
    id: str
    ref: str = ""                       # 参校本此位的字
    lib: str = ""                       # 字形库首位字
    cov: float = 0.0                    # 库首位 cov
    lib_n: int = 0                      # 库里 lib 字的刻例数
    emb: list = field(default_factory=list)   # 5b 候选 [(字, 分)]，分从高到低

    @property
    def top(self) -> list[str]:
        return [c for c, _ in self.emb]

    @property
    def best(self) -> float:
        return self.emb[0][1] if self.emb else 0.0

    @property
    def lead(self) -> float:
        return self.emb[0][1] - self.emb[1][1] if len(self.emb) > 1 else 0.0


def _quick_ok(c: Cell, bp: BookParams) -> bool:
    t = bp.ref_trust
    if t == "very_high":
        return c.top[:1] == [c.ref] and c.best >= 0.90 and c.cov >= 0.90
    if t == "high":
        return c.top[:1] == [c.ref] and c.best >= 0.93 and c.cov >= 0.90
    if t == "medium":
        return c.lib == c.ref and c.top[:1] == [c.ref] and 0.90 <= c.cov <= 0.95 and c.lib_n > 0
    return False


def classify(c: Cell, bp: BookParams) -> tuple[str, str]:
    """返回 (层, 原因)。"""
    ref = c.ref if is_han(c.ref) else ""
    if not ref:
        return "hard", "no_ref"
    if c.best < bp.hard_below:
        return "hard", "5b_low"
    if ref in CONTEXT_CHARS:
        return "hard", "context_char"
    if bp.ref_trust in ("high", "very_high") and ref not in c.top[:3] and c.best >= bp.align_min:
        return "align", "ref_not_in_5b_top3"
    pos = skip_reason(c.id, bp.col_len)
    if _quick_ok(c, bp):
        if pos:
            pass                                   # 列首尾、小注不进快审，往下落
        elif ref in bp.near_chars:
            pass                                   # 形近组里的字要逐格看
        else:
            return "quick", "ref_trust_" + bp.ref_trust
    lib_ok = c.lib and c.top[:1] == [c.lib]
    if (lib_ok or c.lead >= 0.03) and c.cov >= 0.90 and c.lib_n > 0:
        return "high", "lib_eq_5b" if lib_ok else "5b_lead"
    return "low", ("quick_but_" + pos) if (pos and _quick_ok(c, bp)) else "rest"


def to_row(c: Cell, bp: BookParams) -> dict:
    """出页用的一行：层、原因、预选字、候选（5b 前十 → 库首位 → 参校本）。"""
    layer, why = classify(c, bp)
    cands, seen = [], set()
    for ch, src in [(x, "5b") for x in c.top[:10]] + [(c.lib, "库候选"), (c.ref, "参校本")]:
        if ch and ch != "?" and ch not in seen:
            seen.add(ch)
            cands.append([ch, src])
    pre = c.ref if layer == "quick" else (c.top[0] if c.top else c.ref)
    return {"id": c.id, "layer": layer, "why": why, "pre": pre, "ref": c.ref, "lib": c.lib, "cov": c.cov,
            "lib_n": c.lib_n, "best5": c.best, "top5": c.top[:3], "cands": cands}


# ---- 从产物包读格 ----

def _load(pack: Path, step: str, page: int):
    f = pack / step / f"p{page:04d}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8")).get(step)


def _find(doc, cid):
    for col in (doc or {}).get("columns", []):
        for ch in col.get("chars", []):
            if ch.get("id") == cid:
                return ch
    for ch in (doc or {}).get("chars", []):
        if ch.get("id") == cid:
            return ch
    return None


def cells_from_pack(ids: list[str], pack_dir: str, lib_counts: dict[str, int] | None = None) -> list[Cell]:
    """pack_dir 可带 {vol}；各册须有 glyph_match / rare_candidates / align_ref。找不到 glyph_match 的格跳过。"""
    lib_counts = lib_counts or {}
    out = []
    for cid in ids:
        vol, page = cid.split(":")[0], int(cid.split(":")[1])
        pk = Path(pack_dir.format(vol=vol))
        g = _find(_load(pk, "glyph_match", page), cid)
        if g is None:
            continue
        r5 = _find(_load(pk, "rare_candidates", page), cid) or {}
        ar = _find(_load(pk, "align_ref", page), cid) or {}
        cands = g.get("candidates") or []
        lib, cov = (cands[0][0], float(cands[0][1])) if cands else ("", 0.0)
        emb = sorted(((x["char"], float(x["score"])) for x in r5.get("candidates", []) if x.get("font") == "emb"),
                     key=lambda t: -t[1])
        out.append(Cell(cid, ar.get("align_char") or "", lib, cov, lib_counts.get(lib, 0), emb))
    return out


def lib_counts_from_exemplars(path: str) -> dict[str, int]:
    n: dict[str, int] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            ch = json.loads(line).get("char")
            n[ch] = n.get(ch, 0) + 1
    return n


def default_near_pairs() -> frozenset:
    try:
        from ..review.reasons import _near_pairs
        return frozenset(frozenset(p) for p in _near_pairs())
    except Exception:  # noqa: BLE001 —— 没装 cv 时只用内置形近组
        return frozenset()
