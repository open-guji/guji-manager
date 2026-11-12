"""`guji seg pin`：把一列切分整列写定（manual-cells），不用手写 JSON（A22，2026-11-12，Sheldon 定）。

总表与什么时候该用整列写定见 cv `doc/切分覆盖.md` 第四节。流程：

1. 起稿：这一列已有 active 的 manual-cells 就从它起，否则从现行 row_segment 产物抽出本列的格表（列图坐标）；
2. 按命令行的编辑一条条改（拆、并、挪、插、删、整列按格线重排），格号按位置从 1 重排；
3. 出草稿：整行 JSON、改前改后格号对照（给 `guji swap`）、叠框图（有列图缓存时），并用 cv 的 `check_manual_cells` 查格式；
4. `--write` 才写进本机数据目录的 `feedback/verdicts/char-segmentation/manual-cells/items.jsonl`（同 id 原地替换、加一条 history），
   之后照打印出来的下一步做：`seg_pins_check` 沙箱核 → `guji db sync` → 交单 `--from row_segment`。

存储格式不变（每格 slot、sub、kind、x0、x1、y0、y1 都写全）：编辑时省掉的 x 一律取本列内容宽，写进去的是全的。

编辑写法（格号＝改之前那一刻的格号，按命令行顺序依次生效）：

    --split 5@412          第 5 格在列图 y=412 处拆成两格
    --merge 7-8            第 7、8 格并成一格（框取并集）
    --move 3.y1=455        第 3 格下沿挪到 455（y0／y1／x0／x1 都行）
    --insert-after 4@380:455   第 4 格后插一格，y 从 380 到 455（--insert-after 0@… 插在最前）
    --delete 9             删掉第 9 格
    --ys 12,140,268,…      整列按这些格线重排成 len-1 个正文格（覆盖起稿）

夹注格（同格号 a/b 两半）只能挪、删、整体插；拆／并碰到夹注格就报错，请改用 --ys 或手写。
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MANUAL_CELLS_SHARD = "char-segmentation/manual-cells"


class PinError(ValueError):
    pass


@dataclass
class Draft:
    book: str
    page: int
    col: int
    cells: list[dict]
    content_x: tuple[float, float]
    source: str                          # "manual-cells" | "row_segment"
    old_slots: list[int] = field(default_factory=list)   # 起稿时每个位置的格号（给对照表）

    @property
    def item_id(self) -> str:
        return f"{self.book}:{self.page}:{self.col}"


# ── 纯函数：编辑 ──────────────────────────────────────────────────────────

def _groups(cells: list[dict]) -> list[list[dict]]:
    """按格号分组（夹注 a/b 同一组），保持出现顺序。"""
    out: list[list[dict]] = []
    idx: dict[int, int] = {}
    for c in cells:
        s = int(c["slot"])
        if s not in idx:
            idx[s] = len(out)
            out.append([])
        out[idx[s]].append(c)
    return out


def _renumber(groups: list[list[dict]]) -> list[dict]:
    out = []
    for i, g in enumerate(groups, 1):
        for c in g:
            c["slot"] = i
            out.append(c)
    return out


def _find(groups: list[list[dict]], slot: int) -> int:
    for i, g in enumerate(groups):
        if int(g[0]["slot"]) == slot:
            return i
    raise PinError(f"没有第 {slot} 格（现有 {[int(g[0]['slot']) for g in groups]}）")


def _char(y0: float, y1: float, cx: tuple[float, float]) -> dict:
    return {"slot": 0, "sub": None, "kind": "char", "x0": float(cx[0]), "x1": float(cx[1]),
            "y0": float(y0), "y1": float(y1)}


def apply_edit(cells: list[dict], edit: tuple[str, str], content_x: tuple[float, float]) -> list[dict]:
    """一条编辑 → 新格表（格号从 1 重排）。不改输入。"""
    op, arg = edit
    groups = [[dict(c) for c in g] for g in _groups(copy.deepcopy(cells))]
    if op == "ys":
        ys = [float(v) for v in arg.split(",") if v.strip()]
        if len(ys) < 2 or any(b <= a for a, b in zip(ys, ys[1:])):
            raise PinError(f"--ys 要至少两条、严格自上而下的格线：{arg}")
        return _renumber([[_char(a, b, content_x)] for a, b in zip(ys, ys[1:])])
    if op == "split":
        s, _, y = arg.partition("@")
        i = _find(groups, int(s))
        g = groups[i]
        if len(g) != 1:
            raise PinError(f"第 {s} 格是夹注（a/b 两半），不能拆；改用 --ys 或手写")
        c, y = g[0], float(y)
        if not (c["y0"] < y < c["y1"]):
            raise PinError(f"拆点 y={y} 不在第 {s} 格里（{c['y0']}–{c['y1']}）")
        top, bot = dict(c, y1=y), dict(c, y0=y, kind="char", sub=None)
        groups[i:i + 1] = [[top], [bot]]
    elif op == "merge":
        a, _, b = arg.partition("-")
        i, j = _find(groups, int(a)), _find(groups, int(b))
        if j <= i:
            raise PinError(f"--merge 要前小后大：{arg}")
        span = groups[i:j + 1]
        if any(len(g) != 1 for g in span):
            raise PinError(f"--merge {arg} 里有夹注格，不能并；改用 --ys 或手写")
        cs = [g[0] for g in span]
        m = dict(cs[0], y0=min(c["y0"] for c in cs), y1=max(c["y1"] for c in cs),
                 x0=min(c["x0"] for c in cs), x1=max(c["x1"] for c in cs), kind="char", sub=None)
        groups[i:j + 1] = [[m]]
    elif op == "move":
        s, _, rest = arg.partition(".")
        k, _, v = rest.partition("=")
        if k not in ("y0", "y1", "x0", "x1"):
            raise PinError(f"--move 只认 y0／y1／x0／x1：{arg}")
        for c in groups[_find(groups, int(s))]:
            c[k] = float(v)
    elif op == "insert-after":
        s, _, span = arg.partition("@")
        y0, _, y1 = span.partition(":")
        new = [_char(float(y0), float(y1), content_x)]
        i = -1 if int(s) == 0 else _find(groups, int(s))
        groups.insert(i + 1, new)
    elif op == "delete":
        del groups[_find(groups, int(arg))]
    else:
        raise PinError(f"不认识的编辑 {op}")
    out = _renumber(groups)
    for c in out:
        if not (c["y0"] < c["y1"] and c["x0"] < c["x1"]):
            raise PinError(f"编辑 {op} {arg} 后第 {c['slot']} 格框不对：{c}")
    return out


def slot_map(before: list[dict], after: list[dict]) -> list[tuple[int | None, int | None, str]]:
    """改前改后格号对照：按格心 y 就近配（一格配一格），配不上的记增删。给 `guji swap` 的格号对照表参考。"""
    def centers(cs):
        return [(int(g[0]["slot"]), (min(c["y0"] for c in g) + max(c["y1"] for c in g)) / 2) for g in _groups(cs)]
    b, a = centers(before), centers(after)
    used: set[int] = set()
    rows: list[tuple[int | None, int | None, str]] = []
    for sb, yb in b:
        best = None
        for sa, ya in a:
            if sa in used:
                continue
            g = next(g for g in _groups(after) if int(g[0]["slot"]) == sa)
            y0, y1 = min(c["y0"] for c in g), max(c["y1"] for c in g)
            if y0 <= yb <= y1 and (best is None or abs(ya - yb) < abs(best[1] - yb)):
                best = (sa, ya)
        if best is None:
            rows.append((sb, None, "删／并"))
        else:
            used.add(best[0])
            rows.append((sb, best[0], "同" if sb == best[0] else "改号"))
    for sa, _ya in a:
        if sa not in used:
            rows.append((None, sa, "新增"))
    return rows


def make_item(d: Draft, why: str, prev: dict | None = None) -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    hist = list((prev or {}).get("history") or [])
    hist.append({"ts": ts, "change": "updated" if prev else "created", "why": why})
    item = dict(prev or {})
    item.update({"id": d.item_id, "anchor": {"book": d.book, "page": d.page, "col": d.col},
                 "expected": {**((prev or {}).get("expected") or {}), "cells": d.cells},
                 "status": "active", "label_origin": "human", "history": hist})
    item.setdefault("input", {})
    item.setdefault("source_events", [])
    return item


# ── 读写本机数据 ──────────────────────────────────────────────────────────

def parse_target(s: str) -> tuple[str, int, int]:
    parts = s.split(":")
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        raise PinError(f"列写成 册:页:列，如 vol01:88:4（收到 {s!r}）")
    return parts[0], int(parts[1]), int(parts[2])


def items_path() -> Path:
    from ._cv import verdicts_root
    return Path(verdicts_root()) / MANUAL_CELLS_SHARD / "items.jsonl"


def read_items(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_item(path: Path, item: dict) -> None:
    """同 id 原地替换，没有就追加。"""
    rows = read_items(path)
    for i, r in enumerate(rows):
        if r.get("id") == item["id"]:
            rows[i] = item
            break
    else:
        rows.append(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def draft_from_data(book: str, page: int, col: int, store=None) -> tuple[Draft, dict | None]:
    """起稿：active 的 manual-cells 优先，否则现行 row_segment 产物。返回 (草稿, 已有条目或 None)。"""
    from ._cv import ProductStore, page_key
    st = store or ProductStore()
    pc = st.read(book, "row_segment", page_key(page), "cells")
    cc = None if pc is None else next((c for c in pc.columns if c.col == col), None)
    content_x = tuple(cc.content_x) if cc is not None and cc.content_x else None
    prev = next((r for r in read_items(items_path())
                 if r.get("id") == f"{book}:{page}:{col}" and r.get("status") == "active"), None)
    if prev is not None:
        cells = [dict(c) for c in prev["expected"]["cells"]]
        if content_x is None:
            content_x = (min(c["x0"] for c in cells), max(c["x1"] for c in cells))
        src = "manual-cells"
    else:
        if cc is None:
            raise PinError(f"{book} p{page} 没有 row_segment 产物或没有第 {col} 列：先 products pack fetch，或用 --ys 从零写")
        cells = [{"slot": int(c.slot), "sub": c.sub, "kind": c.kind if c.kind in ("char", "jiazhu_a", "jiazhu_b") else "char",
                  "x0": round(float(c.x0), 1), "x1": round(float(c.x1), 1),
                  "y0": round(float(c.y0), 1), "y1": round(float(c.y1), 1)}
                 for c in cc.cells if c.kind != "blank"]
        cells = _renumber(_groups(cells)) if cells else []
        src = "row_segment"
    if content_x is None:
        raise PinError("拿不到本列内容宽：没有产物也没有已写的钉子")
    d = Draft(book, page, col, cells, content_x, src, [int(c["slot"]) for c in cells])
    return d, prev


def overlay(d: Draft, before: list[dict], out: Path) -> Path | None:
    """列图上画框：灰＝起稿、红＝新格表，格号标在右边。没有列图缓存返回 None。"""
    try:
        import cv2
        from ._cv import column_key
    except Exception:  # noqa: BLE001
        return None
    try:
        from ._cv import cache_root
        p = Path(cache_root()) / d.book / "column_image" / f"{column_key(d.page, d.col)}.png"
    except Exception:  # noqa: BLE001
        return None
    if not p.exists():
        return None
    img = cv2.cvtColor(cv2.imread(str(p), cv2.IMREAD_GRAYSCALE), cv2.COLOR_GRAY2BGR)
    img = cv2.copyMakeBorder(img, 0, 0, 0, 30, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    for cs, color, dx in ((before, (160, 160, 160), 0), (d.cells, (0, 0, 220), 2)):
        for c in cs:
            cv2.rectangle(img, (int(c["x0"]) + dx, int(c["y0"]) + dx), (int(c["x1"]) - dx, int(c["y1"]) - dx), color, 1)
    for c in d.cells:
        cv2.putText(img, f"{c['slot']}{c.get('sub') or ''}", (int(c["x1"]) + 2, int(c["y0"]) + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 220), 1)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img)
    return out
