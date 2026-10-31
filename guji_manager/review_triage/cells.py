"""格号解析与「哪些格不进快审」。

格号 `<册>:<页>:<列>:<格>`，格可带 a/b（双行小注右/左半），如 `02:122:4:11b`。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

COL_LEN = 21          # 史記文淵閣本每列 21 字；别的书按版式改（或传每列实际格数）


@dataclass(frozen=True)
class CellId:
    book: str
    page: int
    col: int
    slot: int
    half: str          # "" | "a" | "b"

    @classmethod
    def parse(cls, cid: str) -> "CellId":
        b, p, c, s = cid.split(":")
        m = re.fullmatch(r"(\d+)([ab]?)", s)
        if not m:
            raise ValueError(f"格号不认识：{cid}")
        return cls(b, int(p), int(c), int(m.group(1)), m.group(2))

    @property
    def patch_name(self) -> str:
        """同 cv `scripts/char_review_sheet.py::patch_name`。"""
        return f"p{self.page:04d}c{self.col:02d}s{self.slot}{self.half}.png"

    @property
    def page_key(self) -> str:
        return f"{self.book}:{self.page}"


def skip_reason(cid: str, col_len: int | None = COL_LEN) -> str | None:
    """不进快审的原因；None＝要进。col_len=None 时不判列尾（列长不定的书，传每列实际格数更准）。"""
    c = CellId.parse(cid)
    if c.half:
        return "jiazhu"
    if c.slot == 1:
        return "col_head"
    if col_len is not None and c.slot >= col_len:
        return "col_tail"
    return None


def patch_path(root: Path, cid: str, layout: str = "cache") -> Path:
    """裁图路径。layout="cache"：工作区 `cache/<册>/char_patch/<名>`；"flat"：`<root>/<册>/<名>`（导出的 patches.tar）。"""
    c = CellId.parse(cid)
    if layout == "cache":
        return root / c.book / "char_patch" / c.patch_name
    return root / c.book / c.patch_name
