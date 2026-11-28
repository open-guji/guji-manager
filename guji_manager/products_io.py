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

DECIDE_NEW = "char_decide"
DECIDE_OLD = "seed_admit"
DECIDE_STEPS = (DECIDE_NEW, DECIDE_OLD)
#: 人裁／AI 裁定事件 target.step 的写名（cv 兼容读口上线、各读端全认新名前继续写旧名）
RULING_STEP = DECIDE_OLD


def is_decide_step(step: Any) -> bool:
    return step in DECIDE_STEPS


def decide_dir(root: Path | str, book: str | None = None) -> Path:
    """`<root>[/<book>]/char_decide`；没有新目录时退回旧名目录（都没有也返回新名路径，调用方自行判存在）。"""
    base = Path(root) / book if book else Path(root)
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
    for k in DECIDE_STEPS:
        if k in doc:
            return doc[k]
    return doc


def layer_strict(doc: dict) -> dict:
    """同 `layer`，但缺键时 KeyError（旧 `doc["seed_admit"]` 的语义）。"""
    for k in DECIDE_STEPS:
        if k in doc:
            return doc[k]
    raise KeyError(DECIDE_NEW)


def resolve_step_dir(root: Path | str, book: str, step: str) -> Path:
    """通用：step 属于定字两名时按并认选目录，其余原样。"""
    return decide_dir(root, book) if is_decide_step(step) else Path(root) / book / step


def read_decide(store: Any, book: str, pk: str) -> dict | None:
    """`ProductStore.read` 的两名版；返回定字层（没有该页返回 None）。"""
    for s in DECIDE_STEPS:
        a = store.read(book, s, pk, s)
        if a is not None:
            return a
    return None


def exists_decide(store: Any, book: str, pk: str) -> bool:
    return any(store.exists(book, s, pk) for s in DECIDE_STEPS)


def manifest_decide(store: Any, book: str):
    """manifest 先新后旧（新目录有登记就用新的）。"""
    m = store.manifest(book, DECIDE_NEW)
    try:
        if m is not None and (len(m.get_all()) if hasattr(m, "get_all") else 1):
            return m
    except Exception:  # noqa: BLE001
        pass
    return store.manifest(book, DECIDE_OLD)
