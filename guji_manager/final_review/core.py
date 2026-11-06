"""纯逻辑：分类、分批、提示词、放行门槛。不依赖 cv，可单测。"""
from __future__ import annotations

import re
from collections import Counter

#: pending_reason → 判读类（对应降人审框架 6.2 的三种提示词）
CLASS_OF = {
    "group_abstain": "Z", "group_conflict": "Z", "group_demoted": "Z", "group_ref_dissent": "Z", "group_weak": "Z",
    "near_form_guard": "N",
    "lib_sparse_dissent": "L",
    "ref_diff_final": "P", "ref_diff_align": "P",
    "ref_mismatch": "P", "ref_replaced": "P",   # 2026-11-06 改名前的旧名，旧单照认
    "occluded_with_ref": "D",
}
CLASS_LABEL = {"Z": "字组（文意类）", "N": "形近护栏（文意类）", "L": "库样本少且与参校本不一致", "P": "参校本不一致（参校本作证人）", "D": "遮挡但参校本有字"}
#: 参校本是证人的类：来源「整理本」权重高，提示词问「放进去通不通」
REF_WITNESS = {"P", "D"}

PROMPT_HEAD = """你是古籍校勘助手，只读文意，不看图（也没有图）。下面是{book}的若干字位，OCR 与参校本在这一位的字有疑问。每条给：id、前文 left（至多20字）、后文 right（至多20字）、候选列表（每个候选带来源：参校本、机器识别、字形库前五、各解法、组成员、护栏对）。上下文是按版面阅读顺序拼的（夹注双行已按阅读顺序，可跨列），其中个别字可能是机器识别错字，不要全信。目标位在 left 与 right 之间。
"""
PROMPT_BY_CLASS = {
    "Z": "任务：按文意（人名、书名、地名、典故、词组、语法、本书常用语）在候选里选一个最合文意的字；不要凭「参校本」「机器」的来源去选，来源只是线索，不能当证据。",
    "N": "任务：按文意在候选里选一个最合文意的字；形近字常出现「两个字放进去都通」，必须给 low。不要凭来源选。",
    "L": "任务：字形库对这些字样本很少，库的排序不可信。只按文意在候选里选字，来源不能当证据。",
    "P": "任务：参校本是本位的证人，机器识别与它不同。问的是「把参校本的字放进上下文通不通」：通且比机器的字更通→选参校本字 high；两个字都通（可能是真异文）→low。不要因为参校本是整理本就选它，也不要因为机器识别就选机器。",
    "D": "任务：这一位被印章或污渍遮挡，参校本有字。问「参校本的字放进去通不通」：文意明确通→参校本字 high；通不通说不准→low。",
}
PROMPT_TAIL = """候选都不对就填「其他」并在 why 写你认为的字（别被前一个字的 OCR 错牵着走）。
置信：high＝文意明确只有这一个候选说得通（有词组、专名或引文印证）；mid＝倾向某字但另一候选也说得通；low＝文意区分不了（两字都通）。形近字常出现「两个字放进去都通」，这时必须给 low，不要硬猜。人名「字于某／號于某」、卷数序数（一二）、學宮／學官、書名＋◎卷，两字都通的一律 low。
只输出 JSON 数组，每条 {"id":…, "char":"<候选字|其他>", "conf":"high|mid|low", "why":"≤30字，写出依据的词组或专名"}。
"""


def prompt_for(cls: str, book: str = "一部古籍刻本") -> str:
    return PROMPT_HEAD.format(book=book) + "\n" + PROMPT_BY_CLASS[cls] + "\n" + PROMPT_TAIL


def half_cell(cell_id: str) -> bool:
    """a/b 后缀半格归切分（S），不判读。"""
    return bool(re.search(r"[ab]$", cell_id.rsplit(":", 1)[-1]))


def select(rows: list[dict], vol_fmt: str = "vol{n}", classes: set[str] | None = None) -> tuple[list[dict], Counter]:
    """cells.tsv 的行 → 待判读格 [{id, cls, reason, group, ref}]；不判读的记数量与原因。"""
    out, skipped = [], Counter()
    for r in rows:
        reason = r.get("pending_reason") or "unknown"
        cls = CLASS_OF.get(reason)
        if not cls:
            skipped[f"不属判读类：{reason}"] += 1
            continue
        if classes and cls not in classes:
            skipped[f"本次不含类 {cls}"] += 1
            continue
        vol = str(r["vol"])
        n = int(re.sub(r"\D", "", vol) or 0)
        cid = f"{vol_fmt.format(n=n)}:{r['cell']}"
        if half_cell(cid):
            skipped["a/b 半格（归 S）"] += 1
            continue
        out.append({"id": cid, "cls": cls, "reason": reason, "group": (r.get("key") or "") if cls == "Z" else "",
                    "ref": r.get("ref") or ""})
    return out, skipped


def batches(cells: list[dict], size: int = 350) -> dict[str, list[list[dict]]]:
    """按类、再按册排序后切批，每批 ≤size 格（一个会话 300–400 格）。"""
    by: dict[str, list[dict]] = {}
    for c in sorted(cells, key=lambda c: (c["cls"], c["id"])):
        by.setdefault(c["cls"], []).append(c)
    return {k: [v[i:i + size] for i in range(0, len(v), size)] for k, v in by.items()}


def session_name(side: str, cls: str, k: int) -> str:
    return f"{side}_{cls}_{k:03d}"


def score(x: dict, ch: str) -> float:
    for s in x["cands"].get(ch, []):
        m = re.match(r"字形库前五\((\d\.\d+)\)", s)
        if m:
            return float(m.group(1))
    return 0.0


def nsrc(x: dict, ch: str) -> int:
    return len({s.split("(")[0] for s in x["cands"].get(ch, []) if not s.startswith(("组成员", "护栏对"))})


def is_ideograph(ch: str) -> bool:
    """放行字必须是一个汉字，口径同 cv `seed_admit` 的 vis_ruling（cv #1135）：统一表意文字各区（含 Unicode 17 Ext J
    U+323B0–3347F）加兼容表意；不含部首区与表意描述符。整理本缺字的占位（ခ、〓、□、○）、私用区码、换行都不是
    ——它们当「整理本字」时会被两路和参校本一起「认同」而放行（2026-11-05 史記 3 格）。"""
    if len(ch) != 1:
        return False
    o = ord(ch)
    return (0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF or 0x20000 <= o <= 0x323AF
            or 0x323B0 <= o <= 0x3347F or 0x2F800 <= o <= 0x2FA1F)


FOLD_GROUPS = ("己已巳", "日曰")   # 用户 11-05：折叠组内任一字算对，领先量不把组内字当竞争者


def _same(a: str, b: str) -> bool:
    return a == b or any(a in g and b in g for g in FOLD_GROUPS)


def lead_of(x: dict, ch: str):
    """字形库前五（`glyph_cands`，按名次）里 ch 是不是首位。→ None（不是首位或没有候选）或 (首位分, 领先次优异字的量)。
    次优异字＝名次靠后、且与 ch 不同折叠组的最高分；没有这样的字，领先量取首位分本身。"""
    gc = x.get("glyph_cands") or []
    if not gc or not _same(gc[0][0], ch):
        return None
    top = float(gc[0][1])
    rest = [float(v) for c, v in gc[1:] if not _same(c, ch)]
    return top, top - (max(rest) if rest else 0.0)


def glyph_witness(x: dict, ch: str, min_score: float | None, min_margin: float | None) -> bool:
    """L2 图一致证人（ai-team 字形领域/L2图一致证人标定）：首位、分 ≥ min_score、领先次优异字 ≥ min_margin。
    两项都没给＝旧口径（`字形库前五` 分 ≥ 0.95）。"""
    if min_score is None and min_margin is None:
        return score(x, ch) >= 0.95
    lo = lead_of(x, ch)
    return bool(lo) and lo[0] >= (min_score if min_score is not None else 0.0) and lo[1] >= (min_margin or 0.0)


def gate_ex(x: dict, a: dict, b: dict, over_ref: set[str], min_score: float = 0.95, min_src: int = 2, lib_n=None,
            glyph: tuple | None = None, ref_lead: dict | None = None, oov=None) -> dict:
    """放行门槛（降人审框架 6.2/6.3）。→ {ok, why, via?, layer?, lead?}。

    1 两路同字且都 high、字在候选里；2 越过参校本只许本书白名单组（Z 类），N/L/P/D 一律只收与参校本同字，
    但 P 类本意就是「取参校本字」，同样只收与参校本同字；3 字形分够或 ≥2 个独立来源；
    4 L 类若给了 lib_n，选中的字库样本须 >2；5 选中的字必须是汉字；整理本缺字占位（ခ／〓）不放行，本书造字（私用区码、○）只在本书库里已有 >2 个样本（需 lib_n）且图一致证人成立时才放行，否则 `not_ideograph`。
    `glyph`＝(ruling_glyph_min_score, ruling_glyph_min_margin)，来自册 yaml，给了就按「首位、≥t、领先 ≥ margin」判图一致证人
    （不给：命令行 min_score 加前五分，旧口径）。
    `ref_lead`＝{"unseen": 阈值|None, "oov": 阈值|None}（册 yaml `ruling_ref_lead_min_*`）：选中字就是整理本字、且在稀见层
    （unseen＝本书库样本 ≤2，需 lib_n；oov＝不在 CNN 类表，需 oov(ch)）时，整理本字须是首位且领先 ≥ 该层阈值，
    **并且**图一致证人成立才放行；任一不成立→`ref_lead_fail`。证据 via=ref_lead，带 layer、lead。其余格不适用；绝不单独放行。
    """
    ch = a["char"]
    if not (a["char"] == b["char"] and a["conf"] == "high" and b["conf"] == "high" and ch in x["cands"]):
        return {"ok": False, "why": "no_double_high"}
    ref = x.get("ref_char")
    if ch != ref:
        if not (x["cls"] == "Z" and x.get("group") in over_ref):
            return {"ok": False, "why": "over_ref_not_allowed"}
    gs, gm_ = glyph if glyph else (None, None)
    gw = glyph_witness(x, ch, gs if glyph else min_score, gm_) if glyph else (score(x, ch) >= min_score)
    if not is_ideograph(ch) and not (lib_n is not None and lib_n(ch) > 2 and gw):
        return {"ok": False, "why": "not_ideograph"}     # 本书造字（私用区、○ 等）只在库里已有 >2 个样本且图一致证人成立时才放行
    if not (gw or nsrc(x, ch) >= min_src):
        return {"ok": False, "why": "weak_evidence"}
    if x["cls"] == "L" and lib_n is not None and lib_n(ch) <= 2:
        return {"ok": False, "why": "lib_sparse_pick"}
    if ref_lead and ch == ref:
        layer = ("unseen" if lib_n is not None and ref_lead.get("unseen") is not None and lib_n(ch) <= 2
                 else "oov" if oov is not None and ref_lead.get("oov") is not None and oov(ch) else None)
        if layer:
            lo = lead_of(x, ch)
            lead = None if lo is None else round(lo[1], 4)
            if lo is None or lo[1] < ref_lead[layer] or not gw:
                return {"ok": False, "why": "ref_lead_fail", "layer": layer, "lead": lead}
            return {"ok": True, "why": "ok", "via": "ref_lead", "layer": layer, "lead": lead}
    return {"ok": True, "why": "ok"}


def gate(x: dict, a: dict, b: dict, over_ref: set[str], min_score: float = 0.95, min_src: int = 2, lib_n=None, **kw) -> tuple[bool, str]:
    r = gate_ex(x, a, b, over_ref, min_score, min_src, lib_n, **kw)
    return r["ok"], r["why"]


def gold_check(rows: list[dict], gold: dict[str, str]) -> dict:
    """金标上放行子集的对错：{checked, wrong:[id…], covered}。"""
    adm = [r for r in rows if r["admit_ok"] and r["id"] in gold]
    wrong = [r["id"] for r in adm if r["A"]["char"] != gold[r["id"]]]
    return {"gold": len(gold), "covered": sum(1 for r in rows if r["id"] in gold), "checked": len(adm), "wrong": wrong}


def override_groups_from_yaml(text: str) -> set[str] | None:
    """册/书 yaml 的 `params.seed_admit.ruling_override_groups`（cv #1064）→ 组名集合；没写返回 None（缺省不核）。
    写法可以是列表或空格/逗号分隔的字符串；空列表＝一律不许越过参校本（返回空集）。"""
    import yaml
    v = ((((yaml.safe_load(text) or {}).get("params") or {}).get("seed_admit") or {}).get("ruling_override_groups"))
    if v is None:
        return None
    if isinstance(v, str):
        v = re.split(r"[\s,]+", v.strip())
    return {str(x) for x in v if str(x)}


def seed_admit_params_from_yaml(text: str) -> dict:
    """册/书 yaml 的 `params.seed_admit`（只取终审用到的键）：ruling_glyph_min_score/margin、ruling_ref_lead_min_unseen/oov。"""
    import yaml
    sa = (((yaml.safe_load(text) or {}).get("params") or {}).get("seed_admit") or {})
    return {k: sa.get(k) for k in ("ruling_glyph_min_score", "ruling_glyph_min_margin", "ruling_ref_lead_min_unseen", "ruling_ref_lead_min_oov")}
