"""格引用的唯一出口（字格永久编号 `u`，GM4 留口 2026-11-24；CV0 T1 接上身份账）。

manager 里凡是要「这是哪一格」的身份（待审单、人裁事件、裁定、票、book-text 落格），都经 `cell_ref()` 取，
不自己拼格号。

- 该册**有字格身份账**（`<feedback>/uid/<册>.jsonl`，见 `guji_manager.uid`、`doc/参考/字格身份账.md`）：
  查该页现行账行的 map，返回整数 `u`；**查不到报 `UidMissing`，不回退格号**（CV0 条件：入账漏了要响，不能静默挂回位置）。
- 该册**还没启用 u**（没有账）：照旧恒等返回格号字符串。试点册先启用，其他册行为不变。

账按文件修改时间缓存，同一进程里账被追加后下一次调用自动重读。
"""
from __future__ import annotations

from pathlib import Path

from .uid.ledger import Ledger, UidMissing, ledger_path, parse_cell

__all__ = ["cell_ref", "cell_of", "is_uid", "UidMissing", "clear_cache"]

_CACHE: dict[tuple[str, str], tuple[float, Ledger]] = {}


def clear_cache() -> None:
    _CACHE.clear()


def _ledger(book: str, root: Path | str | None = None) -> Ledger | None:
    p = ledger_path(book, root)
    try:
        mt = p.stat().st_mtime_ns
    except FileNotFoundError:
        return None
    k = (book, str(p))
    hit = _CACHE.get(k)
    if hit and hit[0] == mt:
        return hit[1]
    led = Ledger.load(book, root)
    _CACHE[k] = (mt, led)
    return led


def is_uid(ref) -> bool:
    return isinstance(ref, int) and not isinstance(ref, bool)


def cell_ref(cell_id: str, *, root: Path | str | None = None) -> int | str:
    """完整格号 `册:页:列:格[a|b]` → 引用：有账的册返回 u（int），没账的册返回格号本身。"""
    book, page = parse_cell(cell_id)
    led = _ledger(book, root)
    if led is None:
        return cell_id
    line = led.page(page)
    u = (line or {}).get("map", {}).get(cell_id)
    if u is None:
        raise UidMissing(f"{cell_id}：{book} 有字格身份账，但第 {page} 页现行账里没有这一格"
                         f"（切字后没入账？跑 guji uid advance {book}）")
    return int(u)


def cell_of(ref, book: str | None = None, *, root: Path | str | None = None) -> str:
    """`cell_ref` 的反函数（引用 → 当前格号）。ref 是 u（int）时要给 `book`；是字符串时恒等。"""
    if not is_uid(ref):
        return ref
    if not book:
        raise ValueError("u 是册内编号，cell_of(u) 要给 book")
    led = _ledger(book, root)
    cid = led.cell_of(ref) if led else None
    if cid is None:
        raise UidMissing(f"{book} u={ref}：现行账里没有（已作废或账不存在）")
    return cid
