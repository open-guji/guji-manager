"""待审单体检（11-13 ZM）：一张单上线前，机械地查「不该进单」的几类格，查出来就拦。

背景：重跑／换单后连着出了几类「不该进判字单的格进了单」——印章遮挡、机器无字被写成「机器改判为 □，推翻人裁」；
旧人裁其实早已失效（换图源后 unanchored／review）却被当成「被机器推翻」；字没问题、只因标点专名要重挂的格混进判字单。
这些格产生在不同的出单路径（proof_cycle、republish、closeout），每条路径各修各的。本模块只看**最后那张单**，
不管它从哪条路径来：下面几类一律不能上线（``BLOCK``），``WARN`` 的只提示。

只读单子本身（需要的话传码位归一表 ``norm``），不读产物、不读事件，所以出单前后、线上单都能跑：
``guji pending audit <册> -w <工作区>``（线上单）、``guji pending audit <册> --sheet <候选单.json>``。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..closeout import anchors as A

#: 自动写的「机器推翻人裁」说明：机器改判「旧」→「新」，推翻人裁，请核（cv proof_cycle）
OVERTURN_NOTE = re.compile(r"机器改判「([^」]*)」→「([^」]*)」，?推翻人裁")
#: 旧人裁已经不被采信的绑定状态（`feedback/bindings.py`：valid／rebound 才认）
UNTRUSTED = {"unanchored", "review", "void"}
BLANKS = {"", "□", "〓"}

BLOCK = {
    "overturn_empty": "「机器改判为 □／无字」不是推翻人裁（机器没认出字，如印章遮挡）：该留人裁字、不进复审",
    "overturn_untrusted": "旧人裁已不被采信（换图源或切分变了），不存在「被机器推翻」：它是普通待审格，不是复审格",
    "overturn_same": "机器改判前后是同一个字（码位归一后相同）：没有分歧，不该复审",
    "anchor_only_in_cells": "只因标点专名要重挂的格混在判字单 cells[] 里：该放 anchor_cells[]（字没问题，不让人判字）",
    "dup_cell": "同一格在单上出现两次",
}
WARN = {
    "no_reason": "没有待审原因码（pending_reason），网站显示「原因不明」",
    "recheck_no_note": "复审格没有说明，用户不知道为什么要再看",
}


@dataclass(frozen=True)
class Finding:
    code: str
    cell: str
    msg: str = ""

    @property
    def block(self) -> bool:
        return self.code in BLOCK

    def line(self) -> str:
        return f"{'✗' if self.block else 'ⓘ'} {self.cell}\t{self.code}\t{self.msg or (BLOCK | WARN)[self.code]}"


def _u(c: str, norm: dict[str, str]) -> str:
    return norm.get(c, c)


def audit_sheet(doc: dict, norm: dict[str, str] | None = None) -> list[Finding]:
    """体检一张单（``cells[]`` 才是判字单；``anchor_cells[]`` 不查）。``norm``：码位归一表 {另一码位: 本书码位}。"""
    norm = norm or {}
    out: list[Finding] = []
    seen: set[str] = set()
    for x in doc.get("cells") or []:
        cell = x.get("cell", "?")
        if cell in seen:
            out.append(Finding("dup_cell", cell))
        seen.add(cell)
        if A.anchor_only(x) and not x.get("recheck"):
            out.append(Finding("anchor_only_in_cells", cell))
        note = str(x.get("note") or "")
        m = OVERTURN_NOTE.search(note) if x.get("recheck") else None
        if m:
            old, new = m.group(1), m.group(2)
            if new in BLANKS:
                out.append(Finding("overturn_empty", cell, f"{note}"))
            elif old and _u(old, norm) == _u(new, norm):
                out.append(Finding("overturn_same", cell, f"{note}"))
            st = (x.get("stale") or {}).get("state")
            if st in UNTRUSTED and new not in BLANKS:
                out.append(Finding("overturn_untrusted", cell, f"{note}（旧人裁绑定状态 {st}）"))
        elif x.get("recheck") and not note:
            out.append(Finding("recheck_no_note", cell))
        if not x.get("pending_reason") and not x.get("recheck"):
            out.append(Finding("no_reason", cell))
    return out


def summary(findings: list[Finding]) -> dict[str, int]:
    n: dict[str, int] = {}
    for f in findings:
        n[f.code] = n.get(f.code, 0) + 1
    return n
