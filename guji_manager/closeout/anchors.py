"""auto_remap 的分流项 → 待审格。

分流项（`remap_anchors.remap_data` 的 report）：(层, 条目, 旧锚, 新锚, 内容, "原因码｜说明")，
层 ∈ punct／entity／entity-复核；原因码 ∈ ADD_DEL／ANCHOR_MISS／SPAN_REWORD。
漂移告警（local_check「其他标点」）：由调用方整理成同形的 (层, 条目, 旧锚, 新锚, 内容, "ANCHOR_DRIFT｜说明")。

**detail 格式**（8.8 待定项 2）：`pending_reason_detail` 是若干段用 " | " 隔开的文字；锚点信息是以
`anchor=` 开头的一段，后接紧凑 JSON 数组，每项 `{l 层, i 条目, o 旧锚, n 新锚, t 内容, c 原因码, w 说明}`。
别的段（字组场景、细分等）原样保留，所以一格多因时主因不变、锚点信息追加在后面，解析只认 `anchor=` 段。
"""
from __future__ import annotations

import json
import re
from collections import Counter

from ..review.pending_reason import PendingReason as R
from ..review.pending_reason import specs

SEP = " | "
MARK = "anchor="
CELL_RE = re.compile(r"(?:vol\d+:)?\d+:\d+:\d+[ab]?")   # 双栏格带 a／b 后缀（殿本职名页 88:6:15b），丢了网站就找不到格

#: auto_remap／local_check 的原因码 → 待审原因。认不出的码按 anchor_miss 处理（并在 detail 里带着原码）。
CODE_TO_REASON = {
    "ADD_DEL": R.ADD_DEL,
    "ANCHOR_MISS": R.ANCHOR_MISS,
    "SPAN_REWORD": R.ANCHOR_MISS,
    "ANCHOR_DRIFT": R.ANCHOR_DRIFT,
}
ANCHOR_REASONS = (R.ADD_DEL, R.ANCHOR_MISS, R.ANCHOR_DRIFT)
ANCHOR_REASON_VALUES = frozenset(r.value for r in ANCHOR_REASONS)


def split_code(tag: str) -> tuple[str, str]:
    code, _, why = tag.partition("｜")
    return code.strip(), why.strip()


def reason_of(code: str) -> R:
    return CODE_TO_REASON.get(code, R.ANCHOR_MISS)


def cell_of(anchor: str) -> str | None:
    """锚点（`3:1:2`、`vol04:3:1:2`、专名 `3:1:2～3:1:4`）→ 第一个格号（去册前缀）。"""
    m = CELL_RE.search(anchor or "")
    if not m:
        return None
    s = m.group(0)
    return s.split(":", 1)[1] if s.startswith("vol") else s


def entry(item: tuple) -> dict:
    layer, ident, old, new, content, tag = item
    code, why = split_code(tag)
    return {"l": layer, "i": ident, "o": old, "n": new, "t": content, "c": code, "w": why}


def encode(entries: list[dict]) -> str:
    return MARK + json.dumps(entries, ensure_ascii=False, separators=(",", ":"))


def decode(detail: str | None) -> list[dict]:
    for seg in (detail or "").split(SEP):
        if seg.startswith(MARK):
            try:
                v = json.loads(seg[len(MARK):])
            except ValueError:
                return []
            return v if isinstance(v, list) else []
    return []


def append(detail: str | None, entries: list[dict]) -> str:
    """把锚点信息并进已有 detail：已有的 `anchor=` 段合并（同一条不重复），别的段不动。"""
    segs = [s for s in (detail or "").split(SEP) if s and not s.startswith(MARK)]
    have = decode(detail)
    for e in entries:
        if e not in have:
            have.append(e)
    return SEP.join(segs + [encode(have)])


def main_reason(entries: list[dict]) -> R:
    """一格挂着多条时的锚点主因：按 yaml priority 取最先的（add_del＜anchor_miss＜anchor_drift）。"""
    rs = [reason_of(e["c"]) for e in entries]
    return min(rs, key=lambda r: specs()[r].priority)


def group_by_cell(items, *, use_new: bool = True) -> dict[str, list[dict]]:
    """分流项按**新格**分组（出卡要在新图上看；没有新格的退回旧格）。"""
    out: dict[str, list[dict]] = {}
    for it in items:
        e = entry(it)
        c = (cell_of(e["n"]) if use_new else None) or cell_of(e["o"])
        if c:
            out.setdefault(c, []).append(e)
    return out


def purge(plan: dict) -> int:
    """清掉上一次现算写进单子的锚点信息（A01–A03 不写清除事件，每次出单按当前 book-text 重算，方案 8.9）：
    src=closeout_anchor 的格、主因是 A 类的格整格去掉；别的格只去掉 detail 里的 `anchor=` 段和 `pending_reason_also` 里的 A 类。返回清掉几处。"""
    n = 0
    keep = []
    for x in plan.get("cells", []):
        if x.get("src") == "closeout_anchor" or x.get("pending_reason") in ANCHOR_REASON_VALUES:
            n += 1
            continue
        d = x.get("pending_reason_detail")
        if d and MARK in d:
            segs = [g for g in d.split(SEP) if g and not g.startswith(MARK)]
            if segs:
                x["pending_reason_detail"] = SEP.join(segs)
            else:
                x.pop("pending_reason_detail")
            n += 1
        also = [r for r in x.get("pending_reason_also") or [] if r not in ANCHOR_REASON_VALUES]
        if len(also) != len(x.get("pending_reason_also") or []):
            n += 1
            if also:
                x["pending_reason_also"] = also
            else:
                x.pop("pending_reason_also")
        keep.append(x)
    plan["cells"] = keep
    return n


def _reasons_sorted(es: list[dict]) -> list[R]:
    rs = {reason_of(e["c"]) for e in es}
    return sorted(rs, key=lambda r: specs()[r].priority)


def stamp(plan: dict, items, *, char_of: dict[str, str] | None = None, fresh: bool = True) -> Counter:
    """把现算出的分流项写进待审单 `plan["cells"]`（就地改）。`fresh=True`（缺省）先 `purge`，所以重复跑幂等、
    问题消了的锚点自然从单上消失。

    - 该格已因别的原因待审：主因 `pending_reason` 不动（字的原因优先，A 类 priority 900+）；锚点类原因按 priority 放进
      `pending_reason_also`，旧新锚与说明追加进 detail；不重复计格。
    - 该格不在单上：新增一格，主因取最先的锚点原因，其余进 `pending_reason_also`，带 `src: closeout_anchor`
      （route deferred／reviewer none：不进人审字卡、不算人审率）。新格的坐标字段（页、列、框）由调用方按新包补；
      `char_of` 给了就填 `char`。
    返回计数：{"purged", "appended", "new", "<主因>": 新增格数}。
    """
    n: Counter = Counter()
    if fresh:
        n["purged"] = purge(plan)
    cells = plan.setdefault("cells", [])
    index = {}
    for x in cells:
        k = cell_of(x.get("cell", ""))
        if k:
            index[k] = x
    prefix = ""
    for x in cells:                      # 沿用单上格号的写法（带不带册前缀）
        m = re.match(r"(vol\d+:)", x.get("cell", ""))
        if m:
            prefix = m.group(1)
            break
    for cell, es in sorted(group_by_cell(items).items()):
        rs = [r.value for r in _reasons_sorted(es)]
        x = index.get(cell)
        if x is not None:
            x["pending_reason_detail"] = append(x.get("pending_reason_detail"), es)
            also = list(x.get("pending_reason_also") or [])
            x["pending_reason_also"] = also + [r for r in rs if r not in also and r != x.get("pending_reason")]
            n["appended"] += 1
            continue
        x = {"cell": prefix + cell, "pending_reason": rs[0], "pending_reason_detail": append(None, es),
             "src": "closeout_anchor"}
        if rs[1:]:
            x["pending_reason_also"] = rs[1:]
        if char_of and cell in char_of:
            x["char"] = char_of[cell]
        cells.append(x)
        index[cell] = x
        n["new"] += 1
        n[rs[0]] += 1
    return n


def anchor_cells(plan: dict) -> list[dict]:
    """待审单上带锚点信息的格（主因是锚点类，或 detail 里有 `anchor=` 段）。"""
    return [x for x in plan.get("cells", [])
            if x.get("pending_reason") in ANCHOR_REASON_VALUES or decode(x.get("pending_reason_detail"))]
