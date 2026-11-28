"""第四步收尾步 seed_admit → char_decide 改名的过渡期读写口（GM3 11-28，CV4 P3 通知）。

- 事件 `target.step`：manager 写入统一用 `RULING_STEP`；cv 兼容读口（#2008）上线后产物仍叫 seed_admit，
  改名版发布后只改这一处常量（旧事件不改，cv 读时把两名当同一步）。
- 产物：目录与页顶层键先新后旧（`final_dir`、`page_body`）；纯本地判断，不依赖 cv 版本。
- 书级参数：`params.char_decide` 与 `params.seed_admit` 二选一，两个都有报错（与 cv 一致）。
"""

from __future__ import annotations

from pathlib import Path

NEW, OLD = "char_decide", "seed_admit"
RULING_STEP = OLD   # 事件写入用名；cv 改名版发布后改成 NEW
STEP_NAMES = (NEW, OLD)


def final_dir(book_root) -> Path:
    """`<册根>` 下收尾产物目录：有 char_decide 用它，否则 seed_admit（都没有也返回 seed_admit，调用方照旧处理空目录）。"""
    root = Path(book_root)
    return root / NEW if (root / NEW).is_dir() else root / OLD


def page_body(doc: dict) -> dict:
    """一页产物 JSON 的正文：顶层键 char_decide／seed_admit 先新后旧，都没有就是 doc 本身。"""
    return doc.get(NEW) or doc.get(OLD) or doc


def params_block(params: dict | None) -> dict:
    """`params` 里收尾步的参数块；两个键都写了报错。"""
    p = params or {}
    if p.get(NEW) and p.get(OLD):
        raise ValueError(f"params 里 {NEW} 与 {OLD} 只能写一个（改名过渡期）")
    return p.get(NEW) or p.get(OLD) or {}
