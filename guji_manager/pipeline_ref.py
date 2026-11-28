"""管线引用（cv 2026-11-28 三链合一，cv #2055）：只剩一条默认链 `guji_default`，原三条链成了它的版式。

- `pipeline_for(book, pid)`：按册展开管线。裸 `guji_default` 要带册才知道版式（不带会当 grid，自由版式／现代排印的册就错了）；
  老 cv（没有 `book=` 参数）退回 `load_pipeline(pid)`，旧链 id 在老 cv 上本来就对。
- `norm_pipeline(pid, layout)`：统计、任务单里新旧 id 混用时归一成 `guji_default@<版式>`，按它分组。
"""

from __future__ import annotations

DEFAULT_CHAIN = "guji_default"
#: 合并前的三条链 id → 版式（同 cv `core/seg_set.LEGACY_PIPELINES`；老 cv 没有这张表，这里留一份）。
LEGACY_PIPELINES: dict[str, str] = {"keben_body_v2": "grid", "keben_free": "free", "modern_body": "print"}


def pipeline_for(book, pid: str | None = None):
    """这册书要跑的管线对象。`pid` 不给按册推（cv `default_pipeline_id`）。"""
    from ._cv import default_pipeline_id, load_pipeline
    pid = pid or default_pipeline_id(book)
    try:
        return load_pipeline(pid, book=book)
    except TypeError:                     # cv 早于 #2055：load_pipeline 不收 book=
        return load_pipeline(pid)


def norm_pipeline(pid: str | None, layout: str | None = None) -> str | None:
    """新旧管线 id 归一：旧链 id → `guji_default@版式`；`guji_default` 带上 `layout`（有的话）；别的原样。"""
    if not pid:
        return pid
    if pid in LEGACY_PIPELINES:
        return f"{DEFAULT_CHAIN}@{LEGACY_PIPELINES[pid]}"
    if pid == DEFAULT_CHAIN and layout:
        return f"{DEFAULT_CHAIN}@{layout}"
    return pid
