"""第四步定字产物的读口：`seed_admit`（旧名）与 `char_decide`（新名，cv P3）两名并认。

规则（CV4 通知 11-28 第四、六节）：
- 目录／页顶层键／事件 `target.step`：先新后旧；新旧目录并存时以 `char_decide/` 为准。
- 旧事件 `target.step=seed_admit` 永不改写，读端永久并认；写端先写旧名（`RULING_STEP`），
  读端全认新名后再切（切前通知）。
- manager 里不再写 `"seed_admit"` 字面，一律经这里。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

def _cv_attr(name: str):
    """cv 的兼容读口（`manager_api`：read_final_store／final_page_dict／final_dir／invalidate_final／is_admit_step）。
    有就转给 cv，规则只在 cv 一处；旧 cv 没有时返回 None，退回下面的本地实现（行为相同）。"""
    try:
        from . import _cv
        return getattr(_cv, name)
    except Exception:  # noqa: BLE001 —— 旧 cv／没装 cv／没登记
        return None


DECIDE_NEW = "char_decide"
DECIDE_OLD = "seed_admit"
DECIDE_STEPS = (DECIDE_NEW, DECIDE_OLD)
#: 人裁／AI 裁定事件 target.step 的写名（cv 兼容读口上线、各读端全认新名前继续写旧名）
RULING_STEP = DECIDE_OLD


def is_decide_step(step: Any) -> bool:
    f = _cv_attr("is_admit_step")
    return bool(f(step)) if f else step in DECIDE_STEPS


def decide_dir(root: Path | str, book: str | None = None) -> Path:
    """`<root>[/<book>]/char_decide`；没有新目录时退回旧名目录（都没有也返回新名路径，调用方自行判存在）。"""
    base = Path(root) / book if book else Path(root)
    f = _cv_attr("final_dir")
    if f and book:
        d = f(root, book)
        return d if d is not None else base / DECIDE_NEW
    new = base / DECIDE_NEW
    if new.is_dir() or not (base / DECIDE_OLD).is_dir():
        return new
    return base / DECIDE_OLD


def decide_pages(root: Path | str, book: str | None = None) -> list[Path]:
    return sorted(decide_dir(root, book).glob("p*.json"))


def layer(doc: dict) -> dict:
    """页 json 的定字层：顶层键 char_decide／seed_admit 都认；都没有当整页就是层（同旧 `doc.get("seed_admit", doc)`）。"""
    if not isinstance(doc, dict):
        return doc
    f = _cv_attr("final_page_dict")
    if f:
        return f(doc, strict=False)
    for k in DECIDE_STEPS:
        if k in doc:
            return doc[k]
    return doc


def layer_strict(doc: dict) -> dict:
    """同 `layer`，但缺键时 KeyError（旧 `doc["seed_admit"]` 的语义）。"""
    f = _cv_attr("final_page_dict")
    if f:
        return f(doc)
    for k in DECIDE_STEPS:
        if k in doc:
            return doc[k]
    raise KeyError(DECIDE_NEW)


def resolve_step_dir(root: Path | str, book: str, step: str) -> Path:
    """通用：step 属于定字两名时按并认选目录，其余原样。"""
    return decide_dir(root, book) if is_decide_step(step) else Path(root) / book / step


def read_decide(store: Any, book: str, pk: str) -> dict | None:
    """`ProductStore.read` 的两名版；返回定字层（没有该页返回 None）。"""
    f = _cv_attr("read_final_store")
    if f:
        return f(store, book, pk)
    for s in DECIDE_STEPS:
        try:
            a = store.read(book, s, pk, s)
        except (KeyError, ValueError, LookupError):     # 旧 cv 不认新步名／新 cv 撤了旧名
            continue
        if a is not None:
            return a
    return None


def exists_decide(store: Any, book: str, pk: str) -> bool:
    for s in DECIDE_STEPS:
        try:
            if store.exists(book, s, pk):
                return True
        except (KeyError, ValueError, LookupError):
            continue
    return False


def invalidate_decide(store: Any, book: str, pk: str, reason: str, cells: list[str] | None = None) -> bool:
    """这一页的定字产物显式失效（两名目录都标，只标有条目的）；有任一名被标返回 True。"""
    f = _cv_attr("invalidate_final")
    if f:
        return bool(f(store, book, pk, reason, cells))
    hit = False
    for s in DECIDE_STEPS:
        if store.manifest(book, s).invalidate(pk, reason, cells):
            hit = True
    return hit
