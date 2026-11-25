"""按 cv 切字五小步（2026-11-25，cv #1869／#1872）后的产物布局读列窗口与出口闸。

- 列窗口：刻本链 2a `column_warp` 的 `column_windows` 只剩拉直量，`band` 在 2b `column_band` 的 `column_bands`，
  `trim_*`／`triage`／`frame_residue_*` 在 2c `column_end` 的 `column_ends`。`merged_windows` 照 cv
  `steps/_colview.merged_windows` 拼回一份字段齐全的 `PageWindows`；没有 2b／2c 产物（老产物、现代链）原样返回。
- 出口闸：刻本链的 `gate_manifest`／`row_segment_gate_manifest` 改由挂在 `cell_shrink` 出口的 `cut_gate` 落盘；
  现代链与老产物仍在 `column_gate`／`row_segment_gate`。`GATE_DIRS` 按先新后旧列出该读的目录。
"""
from __future__ import annotations

#: {闸产物种类: 依次试读的步目录}
GATE_DIRS: dict[str, tuple[str, ...]] = {
    "gate_manifest": ("cut_gate", "column_gate"),
    "row_segment_gate_manifest": ("cut_gate", "row_segment_gate"),
}


def merged_windows(store, book: str, key: str, step: str = "column_warp"):
    """一页列窗口（`PageWindows`），2b／2c 字段拼回；读不到返回 None。"""
    wins = store.read(book, step, key, "column_windows")
    if wins is None or not wins.columns:
        return wins
    bands = store.read(book, "column_band", key, "column_bands")
    ends = store.read(book, "column_end", key, "column_ends")
    if bands is None or ends is None:
        return wins
    cols = []
    for c in wins.columns:
        b, e = bands.column(c.col), ends.column(c.col)
        if b is None or e is None:
            cols.append(c)
            continue
        cols.append(c.model_copy(update={
            "band": b.band, "trim_top": e.trim_top, "trim_bottom": e.trim_bottom, "triage": e.triage,
            "frame_residue_top": e.frame_residue_top, "frame_residue_bottom": e.frame_residue_bottom}))
    return wins.model_copy(update={"columns": cols})


def read_gate(store, book: str, key: str, kind: str = "gate_manifest"):
    """出口闸产物（模型），先 `cut_gate` 后旧目录；都没有返回 None。"""
    for sid in GATE_DIRS[kind]:
        m = store.read(book, sid, key, kind)
        if m is not None:
            return m
    return None


def read_gate_raw(store, book: str, key: str, kind: str = "gate_manifest") -> dict | None:
    """同 `read_gate`，返回原始 dict（`store.read_raw(...)[kind]`）。"""
    for sid in GATE_DIRS[kind]:
        d = store.read_raw(book, sid, key) or {}
        if kind in d:
            return d[kind]
    return None
