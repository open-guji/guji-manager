"""存量迁移提案：给一册已有的裁定、人裁、待审条目配上字格永久编号 u（T2，设计 doc/4-反馈迭代/设计-字格u改挂.md §二.7）。

**只出提案和清单，不写库**。真写（追加事件、推库）放在试点那一步，问过 Sheldon 再做。

口径（总方案「T2」一节、GM4 意见⑤）：

- **裁定**（每格最新一条，没有 u 的）：
  - 直接迁：裁定记的 `cells_sha`（格锚点，#899 回填）＝账上该页某一行的 `cells_sha`，u 取那一行的 map；
  - 宽松证明：没记 `cells_sha` 或对不上时，用账上该页**现行**切分的字（账行 `chars`）核裁定窗口——
    格号前后各 2 字与裁定 `ctx.left` 末 2 字、`ctx.right` 首 2 字**两侧都同**（manager 拿不到候选，比 cv 的「一侧同＋字在候选」严），
    过了取现行 u；
  - 其余进清单（理由：账上没这一页／格号不在账里／窗口对不上／账行没记字）。
- **人裁**（每格最新一条算人裁的 confirm，`anchor` 没 u 的）：事件带框（`anchor.bbox`）且账行有框时，框 IoU ≥ 0.5 才迁；
  没框可比 → 只在该页账**只入过一次**（切分没变过）时按格号迁；其余进清单。
- **待审条目**：条目格号在账上该页现行 map 里 → 补 u（同 `reconcile(us=…)`）；不在 → 清单。

守恒：每类 `迁前 = 迁出 + 没迁`，对不上直接抛错。
"""
from __future__ import annotations

from collections import Counter

from .uid.ledger import Ledger
from .uid.match import iou, xywh_to_box

MIN_IOU = 0.5


def _page_of(cell: str) -> int | None:
    try:
        return int(cell.split(":")[1])
    except (IndexError, ValueError):
        return None


def _window(line: dict, cell: str, n: int = 2) -> tuple[str, str] | None:
    """账行里这一格前后各 n 字（同页读序，账行 map 的键按读序）；账行没记字 → None。"""
    chars = line.get("chars") or {}
    if not chars:
        return None
    keys = list(line["map"])
    try:
        i = keys.index(cell)
    except ValueError:
        return None
    left = "".join(chars.get(k, "") for k in keys[max(0, i - n):i])
    right = "".join(chars.get(k, "") for k in keys[i + 1:i + 1 + n])
    return left, right


def plan_rulings(led: Ledger, rulings: list[dict]) -> tuple[list[dict], list[dict]]:
    """rulings：本册每格最新一条裁定 payload（带 `cell`）。→ (迁出 [{cell, u, how, payload}], 清单 [{类别, 键, 理由}])。"""
    out, left = [], []
    for p in rulings:
        cell = p.get("cell") or ""
        if "u" in p:
            continue
        pg = _page_of(cell)
        cur = led.page(pg) if pg is not None else None
        if cur is None:
            left.append({"类别": "裁定", "键": cell, "理由": "账上没有这一页"})
            continue
        sha = p.get("cells_sha")
        hit = led.by_sha(pg, sha) if sha else None
        if hit is not None and cell in hit["map"]:
            u = int(hit["map"][cell])
            if led.cell_of(u) is None:
                left.append({"类别": "裁定", "键": cell, "理由": f"切分对上了，但 u{u} 已作废"})
                continue
            out.append({"cell": cell, "u": u, "how": "直接", "payload": {**p, "u": u}})
            continue
        if cell not in cur["map"]:
            left.append({"类别": "裁定", "键": cell, "理由": "格号不在现行账里"})
            continue
        w = _window(cur, cell)
        if w is None:
            left.append({"类别": "裁定", "键": cell, "理由": "账行没记字，核不了窗口"})
            continue
        ctx = p.get("ctx") or {}
        l2, r2 = (ctx.get("left") or "")[-2:], (ctx.get("right") or "")[:2]
        wl, wr = w[0][-2:], w[1][:2]
        # 页首／页尾账行这一侧不满 2 字（裁定窗口跨页）：只比账行有的那几个字；两侧都没字可比不算证明
        lok = l2.endswith(wl) if wl else None
        rok = r2.startswith(wr) if wr else None
        if (lok, rok) != (None, None) and lok is not False and rok is not False:
            u = int(cur["map"][cell])
            out.append({"cell": cell, "u": u, "how": "宽松", "payload": {**p, "u": u}})
        else:
            left.append({"类别": "裁定", "键": cell,
                         "理由": f"窗口对不上（裁定 {l2}｜{r2}，现行 {w[0][-2:]}｜{w[1][:2]}）"})
    return out, left


def plan_human(led: Ledger, humans: list[dict]) -> tuple[list[dict], list[dict]]:
    """humans：本册每格最新一条人裁 {id, cell, bbox?, u?}。→ (迁出 [{id, cell, u, how}], 清单)。"""
    out, left = [], []
    for h in humans:
        if h.get("u") is not None:
            continue
        cell = h["cell"]
        pg = _page_of(cell)
        cur = led.page(pg) if pg is not None else None
        if cur is None or cell not in cur["map"]:
            left.append({"类别": "人裁", "键": cell, "理由": "格号不在现行账里"})
            continue
        u = int(cur["map"][cell])
        nb = (cur.get("boxes") or {}).get(cell)
        if h.get("bbox") and nb:
            s = iou(xywh_to_box(h["bbox"]), xywh_to_box(nb))
            if s >= MIN_IOU:
                out.append({"id": h["id"], "cell": cell, "u": u, "how": f"框 IoU {s:.2f}"})
            else:
                left.append({"类别": "人裁", "键": cell, "理由": f"框对不上（IoU {s:.2f}）"})
            continue
        prev, _ = led.page_pair(pg)
        if prev is None:
            out.append({"id": h["id"], "cell": cell, "u": u, "how": "该页只切过一次"})
        else:
            left.append({"类别": "人裁", "键": cell, "理由": "没框可比，且该页重切过"})
    return out, left


def plan_items(led: Ledger, items: list[dict]) -> tuple[list[dict], list[dict]]:
    """items：待审条目（各 id 的现行版本，`cell` 不带册前缀）。→ (迁出 [{id, cell, u}], 清单)。"""
    cur = led.u_map()
    out, left = [], []
    for r in items:
        if r.get("u") is not None:
            continue
        if r["cell"] in cur:
            out.append({"id": r["id"], "cell": r["cell"], "u": cur[r["cell"]]})
        else:
            left.append({"类别": "待审条目", "键": f"{r['id']}（{r['cell']}）", "理由": "格号不在现行账里"})
    return out, left


def plan(led: Ledger, *, rulings: list[dict] = (), humans: list[dict] = (), items: list[dict] = ()) -> dict:
    """→ {rulings, human, items, 清单, 守恒}；守恒不过就抛错。"""
    res: dict = {"清单": []}
    cons = {}
    for name, fn, src, has_u in (("rulings", plan_rulings, rulings, lambda x: "u" in x),
                                 ("human", plan_human, humans, lambda x: x.get("u") is not None),
                                 ("items", plan_items, items, lambda x: x.get("u") is not None)):
        todo = [x for x in src if not has_u(x)]
        got, left = fn(led, list(src))
        res[name] = got
        res["清单"] += left
        cons[name] = {"迁前": len(todo), "迁出": len(got), "没迁": len(left)}
        if len(todo) != len(got) + len(left):
            raise AssertionError(f"{name} 不守恒：{cons[name]}")
    res["守恒"] = cons
    res["迁出方式"] = dict(Counter(x["how"] for x in res["rulings"]))
    return res
