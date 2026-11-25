"""入账时参考 book-text 已发的号（主线程 11-25 口径）。

book-text 的改字工具（``char_edits``、manager 意见修订 B′）会自己发 ``u = u_max + 1``，下次 ``advance`` 之前账里没有这一格。所以：

1. **发号下限**：``advance`` 发新号从 ``max(账 u_max, char 顶层 u_max, char 里最大的 u)`` 往上发，作废号取账与 char ``u_retired`` 的并集，
   绝不发出 book-text 已用过的号。
2. **认领**：这一页本来要发新号（``new``／``split_from``）的格，若与 book-text 里「账上还没有的 u」那一格框对得上
   （IoU ≥ 0.5；或中心距近且同字），就用 book-text 的 u 入账，谱系记 ``src: "book-text"``。

book-text 位置：``GUJI_BOOK_TEXT``（缺省同 ``online_lists``），书 id／章号按册配置（``online_lists.ident``）。找不到就不参考（照旧只看账）。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .match import IOU_MIN, iou, xywh_to_box


@dataclass
class BookTextState:
    path: str
    u_max: int = 0
    retired: set[int] = field(default_factory=set)
    # 页 → [(u, box x0y0x1y1 或 None, 字)]
    cells: dict[int, list[tuple[int, tuple | None, str | None]]] = field(default_factory=dict)

    def floor(self) -> int:
        top = max((u for cs in self.cells.values() for u, _, _ in cs), default=0)
        return max(self.u_max, top, max(self.retired, default=0))


def from_char(char: dict, cord: dict | None, path: str = "") -> BookTextState:
    box_of = {x["a"]: x["box"] for pg in (cord or {}).get("pages") or [] for x in pg.get("cells") or [] if x.get("box")}
    st = BookTextState(path=path, u_max=int(char.get("u_max") or 0),
                       retired={int(x["u"] if isinstance(x, dict) else x) for x in char.get("u_retired") or []})
    for pg in char.get("pages") or []:
        out = []
        for col in pg.get("columns") or []:
            for x in col.get("cells") or []:
                if isinstance(x.get("u"), int):
                    out.append((x["u"], xywh_to_box(box_of.get(x["a"])), x.get("c")))
        st.cells[int(pg["page"])] = out
    return st


def load(book: str, ws: str | None = None, repo: str | None = None, edition: str = "default") -> BookTextState | None:
    """按册配置找到 book-text 的 char＋cord；找不到返回 None。"""
    try:
        from ..online_lists import _cfg, book_text_dir, ident
        bid, ch = ident(book, ws or os.environ.get("GUJI_WORKSPACE"))
        if not (bid and ch):
            return None
        d = Path(book_text_dir(repo or _cfg()["book_text"], bid)) / edition
        cp = d / f"{ch}.char.json"
        if not cp.exists():
            return None
        char = json.loads(cp.read_text(encoding="utf-8"))
        kp = d / f"{ch}.cord.json"
        cord = json.loads(kp.read_text(encoding="utf-8")) if kp.exists() else None
        return from_char(char, cord, str(cp))
    except Exception:  # noqa: BLE001 —— 参考不到就照旧只看账
        return None


def adopt(line: dict, cut, bt: BookTextState, known: set[int]) -> int:
    """把本行里要发新号的格，换成 book-text 已发、账上还没有的 u（框对得上的）。就地改 ``line``，返回认领格数。"""
    cand = [(u, b, c) for u, b, c in bt.cells.get(int(line["page"]), []) if u not in known]
    if not cand:
        return 0
    fresh = {x["u"]: x for x in line["lineage"] if x.get("new") or "split_from" in x}
    if not fresh:
        return 0
    cell_of_u = {u: k for k, u in line["map"].items()}
    box = {c.id: c.box for c in cut.cells}
    ch = {c.id: c.c for c in cut.cells}
    pairs = []
    for nu in fresh:
        k = cell_of_u.get(nu)
        nb = box.get(k)
        if nb is None:
            continue
        for bu, bb, bc in cand:
            if bb is None:
                continue
            s = iou(nb, bb)
            if s >= IOU_MIN:
                pairs.append((-s, nu, bu))
            elif bc and ch.get(k) == bc:
                d = (((nb[0] + nb[2]) - (bb[0] + bb[2])) ** 2 + ((nb[1] + nb[3]) - (bb[1] + bb[3])) ** 2) ** .5 / 2
                if d < 0.6 * max(nb[2] - nb[0], nb[3] - nb[1], bb[2] - bb[0], bb[3] - bb[1]):
                    pairs.append((1 + d, nu, bu))      # 排在所有 IoU 配对之后
    used_n: set[int] = set()
    used_b: set[int] = set()
    n = 0
    for _, nu, bu in sorted(pairs):
        if nu in used_n or bu in used_b:
            continue
        used_n.add(nu)
        used_b.add(bu)
        line["map"][cell_of_u[nu]] = bu
        x = fresh[nu]
        x["u"] = bu
        x["src"] = "book-text"
        n += 1
    if n:
        v = line.setdefault("via", {})
        v["book_text"] = v.get("book_text", 0) + n
    return n
