"""换单时把 dev 上已有的人工改字叠到新导出的 char 上（方案七之二）。

A33 的 auto_remap 只吃叠好后的 char，不处理人工改字；原样导出（`--reuse-products`）会覆盖人工直改的字
（事故 11-06，#408 五册退回 116 格），所以换单必须先叠这一步，叠完**必须核对位**，不过整册停下。

输入：改字清单条目 [{anchor, old, new}]（book-text `NNN.char-edits.json` 的 edits）、对照表 {旧格: 新格}、新 char。
每条按旧格号经对照表换成新格号：
- 新格字＝改后字：已含，不动；
- 新格字＝旧字（机器没动）而≠改后字：覆盖为改后字；
- 新格字既不是旧字也不是改后字（机器本轮又改了）：保留人改字，记为 `overturned`（原因 machine_changed，入新一轮待审单）；
- 表里该格是删／新增（无对应）或新格不在 char 里：不叠，记为 `lost`（交待审格）。
不碰 glyph.db／glyph_store。
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field


@dataclass
class OverlayReport:
    applied: list[dict] = field(default_factory=list)
    already: list[dict] = field(default_factory=list)
    overturned: list[dict] = field(default_factory=list)
    lost: list[dict] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {k: len(getattr(self, k)) for k in ("applied", "already", "overturned", "lost")}


class AlignmentError(Exception):
    """叠加后格序／格数变了，或改了不该改的格。"""


def _cells(char: dict):
    return [c for p in char.get("pages") or [] for col in p.get("columns") or [] for c in col.get("cells") or []]


def overlay(char: dict, edits: list[dict], cellmap: dict[str, str], same=None) -> tuple[dict, OverlayReport]:
    """返回 (叠好的新 char 副本, 报告)。入参 char 不动。``same``：同字判定（charnorm），别／別 之类不算「机器又改了」。"""
    eq = same or (lambda p, q: p == q)
    out = copy.deepcopy(char)
    by_a = {c["a"]: c for c in _cells(out)}
    rep = OverlayReport()
    for e in edits:
        old_a, old_c, new_c = e["anchor"], e["old"], e["new"]
        n = cellmap.get(old_a)
        rec = {"old_anchor": old_a, "new_anchor": n, "old": old_c, "new": new_c}
        cell = by_a.get(n) if n else None
        if cell is None:
            rep.lost.append(rec)
        elif eq(cell["c"], new_c):
            rep.already.append(rec)
        elif eq(cell["c"], old_c):
            cell["c"] = new_c
            rep.applied.append(rec)
        else:
            rep.overturned.append({**rec, "machine": cell["c"]})
            cell["c"] = new_c               # 人改字保留；机器的字记在报告里，格进待审（machine_changed）
    verify(char, out, {r["new_anchor"] for r in rep.applied + rep.overturned})
    return out, rep


def verify(before: dict, after: dict, touched: set[str]) -> None:
    """核对位：格序（格号序列）不变，且只有 touched 里的格换了字。不过抛 AlignmentError。"""
    a, b = _cells(before), _cells(after)
    if [c["a"] for c in a] != [c["a"] for c in b]:
        raise AlignmentError(f"格序或格数变了：{len(a)} → {len(b)}")
    bad = [x["a"] for x, y in zip(a, b) if x["c"] != y["c"] and x["a"] not in touched]
    if bad:
        raise AlignmentError(f"改了不该改的格 {len(bad)} 处，如 {bad[:5]}")
