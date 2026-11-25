"""字格永久编号 u 的身份账（CV0「字格永久编号 u」T1，2026-11-24）。

- ``ledger``：账文件 ``<feedback>/uid/<册>.jsonl`` 的读写与自洽核对；
- ``match``：一页两份切分之间的 u 继承（IoU → 中心距 → 拆 → 并 → 字序列 → 新号／消失）；
- ``source``：一页的切分从 cv 产物或 book-text char＋cord 取；
- 本模块：``advance``（切字后入账）、``init_from_book_text``（用现行文本重建账）；
- 命令 ``guji uid advance|init|show|verify``（``cli``）。

格式与口径：``doc/参考/字格身份账.md``；对外格式（char 的 ``u``、``u_max``、``u_retired``）：guji-format spec 02 §4.10。
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from .ledger import Ledger, UidMissing, ledger_path, make_line, parse_cell, verify  # noqa: F401
from .match import Cell, PageMatch, fresh, match_page, xywh_to_box  # noqa: F401
from .source import PageCut


class _Counter:
    def __init__(self, start: int):
        self.n = start

    def __call__(self) -> int:
        self.n += 1
        return self.n


def _prev_cells(line: dict) -> tuple[list[Cell], dict[str, int]]:
    boxes = line.get("boxes") or {}
    chars = line.get("chars") or {}
    cells = [Cell(k, xywh_to_box(boxes.get(k)), chars.get(k)) for k in line["map"]]
    return cells, {k: int(v) for k, v in line["map"].items()}


def enter_page(led: Ledger, cut: PageCut, nxt, *, src: str = "advance", force: bool = False) -> dict | None:
    """把一页的一份切分入账（不写盘，返回要追加的行）；同一 cells_sha 已是该页现行行 → None。"""
    last = led.page(cut.page)
    if last is not None and not force and cut.cells_sha and last.get("cells_sha") == cut.cells_sha:
        return None
    if last is None:
        m = fresh(cut.cells, nxt)
    else:
        prev, pu = _prev_cells(last)
        m = match_page(prev, pu, cut.cells, nxt)
        if (last.get("cells_sha") is None and cut.cells_sha is None and not force
                and m.map == {k: int(v) for k, v in last["map"].items()}):
            return None
    chars = {c.id: c.c for c in cut.cells if c.c}
    return make_line(led.book, cut.page, cut.cells_sha, m.map, boxes=cut.boxes, chars=chars or None,
                     lineage=m.lineage, via=m.via, src=src)


def _known_u(led: Ledger) -> set[int]:
    out: set[int] = set()
    for d in led.lines:
        out.update(int(u) for u in (d.get("map") or {}).values())
        out.update(int(x["u"]) for x in d.get("lineage") or [])
    return out


def advance(book: str, store, pages: Iterable[int] | None = None, *, root=None, dry_run: bool = False,
            force: bool = False, booktext="auto", src: str = "advance", label: str | None = None) -> dict:
    """切字后入账：现行产物里每页的切分，cells_sha 与该页现行账行不同就入一行。返回统计。

    ``booktext``：book-text 这册的现状（``uid.booktext.BookTextState``）；缺省 ``"auto"`` 按册配置去找，``None`` 不参考。
    参考时新号从 book-text 已发的最大号之上发，且要发新号的格若对得上 book-text 已发、账上没有的 u，就认领它（见 ``booktext``）。"""
    from . import booktext as BT
    from . import source
    from .ledger import line_id
    led = Ledger.load(book, root)
    bt = BT.load(book) if booktext == "auto" else booktext
    if booktext == "auto" and bt is None and BT.required(led):
        raise SystemExit(f"✗ {book} 的账是从 book-text 建的，但找不到这册的 char.json（GUJI_BOOK_TEXT、书 id／章号按册配置，"
                         "章号两位三位都试过）；不参考 book-text 入账可能发出它已用过的号。设好 GUJI_BOOK_TEXT 或 --book-text <仓> 再跑，"
                         "确认不要参考就加 --no-book-text")
    nxt = _Counter(max(led.u_max(), bt.floor() if bt else 0))
    known = _known_u(led) if bt else set()
    adopted = 0
    todo = sorted(set(pages)) if pages is not None else source.product_pages(store, book)
    new: list[dict] = []
    via: Counter = Counter()
    skipped = missing = 0
    for pg in todo:
        if not force:                # 先只算 sha：没变的页不读产物（pipeline 跑完每次都会过一遍全册）
            sha = source.cells_sha(store, book, pg)
            last = led.page(pg)
            if sha and last is not None and last.get("cells_sha") == sha:
                skipped += 1
                continue
        cut = source.from_products(store, book, pg)
        if cut is None or not cut.cells_sha:
            missing += 1
            continue
        d = enter_page(led, cut, nxt, force=force, src=src)
        if d is None:
            skipped += 1
            continue
        if bt:
            k = BT.adopt(d, cut, bt, known)
            if k:
                adopted += k
                d["id"] = line_id(book, cut.page, d.get("cells_sha"), d["map"])
            known.update(int(u) for u in d["map"].values())
        if label:
            d["label"] = label       # 哪个产物包的切分（标 main 钩子／sync 记；自检按它判断 main 包入过没有）
        new.append(d)
        led.lines.append(d)          # 同一页多次出现时后面的按新行对照（内存里）
        via.update(d.get("via") or {})
    if not dry_run and new:
        led.lines = led.lines[:len(led.lines) - len(new)]
        led.append(new)
    return {"book": book, "pages": len(todo), "entered": len(new), "unchanged": skipped,
            "no_product": missing, "u_max": nxt.n, "via": dict(via), "path": str(led.path),
            "book_text": bt.path if bt else None, "book_text_adopted": adopted, "dry_run": dry_run}


def init_from_book_text(book: str, char: dict, cord: dict | None, *, root=None, dry_run: bool = False,
                        store=None) -> dict:
    """用 book-text 现行 char＋cord 建该册的第一份账：char 已带 u（v0.6）就照抄、u_max 取 char 顶层；
    没带就按读序 1..N 发号。``store`` 给了且该页现行产物切分与 char 同（格号集合一致）时记上 cells_sha，
    否则 cells_sha 为 null（之后 ``advance`` 按框对照接上）。账里已有行 → 拒绝（不覆盖）。"""
    from . import source
    led = Ledger.load(book, root)
    if led.exists:
        raise SystemExit(f"{led.path} 已有 {len(led.lines)} 行，init 只给没账的册用（要接着入账用 advance）")
    cuts, have_u = source.from_book_text(book, char, cord)
    n_cells = sum(len(c.cells) for c in cuts)
    if have_u and len(have_u) != n_cells:
        raise SystemExit(f"char 里 {len(have_u)}/{n_cells} 格有 u：要么都有要么都没有")
    nxt = _Counter(0)
    lines = []
    for cut in cuts:
        sha = None
        if store is not None:
            try:
                cur = source.from_products(store, book, cut.page, with_chars=False)
            except Exception:  # noqa: BLE001
                cur = None
            if cur is not None and [c.id for c in cur.cells] == [c.id for c in cut.cells]:
                sha = cur.cells_sha
        if have_u:
            umap = {c.id: have_u[c.id] for c in cut.cells}
            lineage = []
        else:
            umap = {c.id: nxt() for c in cut.cells}
            lineage = [{"u": u, "new": True} for u in umap.values()]
        chars = {c.id: c.c for c in cut.cells if c.c}
        lines.append(make_line(book, cut.page, sha, umap, boxes=cut.boxes, chars=chars or None,
                               lineage=lineage, via={"init": len(umap)}, src="init"))
    retired = []
    if have_u:
        top = int(char.get("u_max") or 0)
        retired = char.get("u_retired") or []
        if retired or top > max(have_u.values()):
            # 册级记录（page=0，没有格）：char 的作废号进谱系，顶层 u_max 照抄（改字工具删过尾号时 u_max 比现存最大号大）
            meta = make_line(book, 0, None, {}, lineage=[dict(x) for x in retired], src="init")
            meta["u_max"] = top
            lines.append(meta)
    if not dry_run:
        led.append(lines)
    return {"book": book, "pages": len(cuts), "cells": n_cells, "copied_u": bool(have_u),
            "u_max": led.u_max() if not dry_run else max([nxt.n, *have_u.values()], default=0),
            "retired": len(retired), "with_cells_sha": sum(1 for d in lines if d.get("cells_sha")),
            "path": str(led.path), "dry_run": dry_run}


def enabled(book: str, root=None) -> bool:
    """这册启用了 u（有身份账）。"""
    return ledger_path(book, root).exists()


def mark_synced(book: str, label: str, *, root=None, src: str = "sync") -> bool:
    """记一笔「main 包 ``label`` 已对过账、没有要入的页」（page 0、空 map 的册级行），自检就不再重取这个包。
    已有同一笔 → 不写，返回 False。"""
    import hashlib
    led = Ledger.load(book, root)
    lid = f"uid-{book}-sync-{hashlib.sha256(label.encode()).hexdigest()[:12]}"
    if any(d.get("id") == lid for d in led.lines) or any(d.get("label") == label for d in led.lines):
        return False
    from .ledger import make_line
    d = make_line(book, 0, None, {}, src=src)
    d["id"] = lid
    d["label"] = label
    led.append([d])
    return True


def book_enabled(root=None) -> bool:
    """这部书启用了 u：书的账目录（``<feedback>/uid``，一个工作区一部书）里已有任一册账。
    没 book-text 的册（如全唐文 031 起）没法从 book-text init，靠它判断标 main 时要不要按 main 包首次入账。"""
    from pathlib import Path
    from .ledger import default_root
    r = Path(root) if root else default_root()
    return r.is_dir() and any(r.glob("*.jsonl"))
