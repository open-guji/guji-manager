"""给要写进库的东西盖字格永久编号 u（T2，设计 doc/4-反馈迭代/设计-字格u改挂.md）。

u 来自 `cell_ref()`（T1 字格身份账）：册**有账**时返回 int，册**没账**时恒等返回格号字符串——这时一律**不盖**，
写出来的东西与以前逐字节相同。有账但查不到这一格，`cell_ref` 报错，这里不吞：宁可整批不写，也不写半截（先 `guji uid advance <册>`）。

- 裁定（`ctx_ruling`）：`payload.u`（cv `RulingStore` 按 (group, 册, payload.u) 查，T3）；
- 人裁事件（`unit=cell`）：`target.anchor["u"]`（`EventTarget` 是 cv 的 pydantic 模型，多的字段会丢，只能放自由字典 anchor）。

格号照旧写（双写期），u 只是**加**的字段。
"""
from __future__ import annotations

from typing import Callable, Iterable


def _cell_ref() -> Callable[[str], object]:
    """批量用的 cell_ref：同一次调用里每册只读一次账、只建一次「格号→u」表（`cell_ref` 逐格查要每次重算各页最后一行）。
    口径同 `cell_ref`：册没账恒等返回格号；有账缺格抛 `UidMissing`。"""
    from .cell_ref import UidMissing, _ledger
    cur: dict[str, dict[str, int] | None] = {}

    def ref(cid: str):
        book = cid.split(":", 1)[0]
        if book not in cur:
            led = _ledger(book)
            cur[book] = led.current() if led is not None and led.exists else None
        m = cur[book]
        if m is None:
            return cid
        if cid not in m:
            raise UidMissing(f"{cid}：{book} 有字格身份账，但现行账里没有这一格（切字后没入账？跑 guji uid advance {book}）")
        return m[cid]
    return ref


def is_full_cell(cid: object) -> bool:
    """`册:页:列:格[ab]`（四段、后三段是数）。"""
    if not isinstance(cid, str) or cid.count(":") != 3:
        return False
    _, p, c, s = cid.split(":")
    s = s[:-1] if s[-1:] in ("a", "b") else s
    return all(x.lstrip("-").isdigit() for x in (p, c, s))


def u_of(cid: str, ref: Callable[[str], object] | None = None) -> int | None:
    """完整格号 → u；册没账（`cell_ref` 恒等）或不是完整格号 → None。有账缺格照抛。"""
    if not is_full_cell(cid):
        return None
    r = (ref or _cell_ref())(cid)
    return r if isinstance(r, int) and not isinstance(r, bool) else None


def u_map(book: str, cells: Iterable[str], ref: Callable[[str], object] | None = None) -> dict[str, int]:
    """`{格号(不带册前缀): u}`；册没账 → 空字典（调用方据此走旧路）。"""
    ref = ref or _cell_ref()
    out: dict[str, int] = {}
    for c in cells:
        bare = str(c).split(":", 1)[1] if str(c).count(":") == 3 else str(c)
        full = f"{book}:{bare}"
        if not is_full_cell(full):
            continue
        u = u_of(full, ref)
        if u is None:
            return {}                     # 册没账：cell_ref 恒等
        out[bare] = u
    return out


def _ledger(book: str):
    from .cell_ref import _ledger as L
    return L(book)


def export_uids(book: str) -> dict | None:
    """book-text 导出用（`from_pages_json(uids=…)`）：册有账 → {map, u_max, u_retired}；没账 → None。"""
    led = _ledger(book)
    if led is None or not led.exists:
        return None
    return {"map": led.u_map(), "u_max": led.u_max(),
            "u_retired": [led.retired()[u] for u in sorted(led.retired())]}


def current_cell(p: dict) -> str | None:
    """裁定 payload → 它**现在**挂的格号：带 u 且册有账就按账反查（重切、补删字后格号变了也跟着走），
    u 已作废／账里没有 → None；没带 u → 原 `cell`。"""
    cell = p.get("cell")
    u = p.get("u")
    if not (isinstance(u, int) and not isinstance(u, bool)) or not is_full_cell(cell):
        return cell
    from .cell_ref import UidMissing, cell_of
    book = cell.split(":", 1)[0]
    if _ledger(book) is None:
        return cell
    try:
        return cell_of(u, book)
    except UidMissing:
        return None


def stamp_rulings(evs: list, ref: Callable[[str], object] | None = None) -> int:
    """裁定事件盖 `payload.u`（只盖 `payload.cell` 是完整格号的）。→ 盖了几条。已有 u 的不动。"""
    ref = ref or _cell_ref()
    n = 0
    for e in evs:
        if not hasattr(e, "payload"):
            continue
        p = e.payload if e.payload is not None else {}
        if "u" in p:
            continue
        u = u_of(p.get("cell"), ref)
        if u is not None:
            p["u"] = u
            e.payload = p
            n += 1
    return n


def stamp_human(evs: list, ref: Callable[[str], object] | None = None) -> int:
    """`unit=cell` 的人裁事件盖 `target.anchor["u"]`。→ 盖了几条。已有的不动。"""
    ref = ref or _cell_ref()
    n = 0
    for e in evs:
        t = getattr(e, "target", None)
        if t is None or t.unit != "cell" or "u" in (t.anchor or {}):
            continue
        u = u_of(t.key, ref)
        if u is not None:
            t.anchor = {**(t.anchor or {}), "u": u}
            n += 1
    return n
