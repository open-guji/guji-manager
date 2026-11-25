"""存量迁移提案：给一册已有的裁定、人裁、待审条目配上字格永久编号 u（T2，设计 doc/4-反馈迭代/设计-字格u改挂.md §二.7）。

**只出提案和清单，不写库**。真写（追加事件、推库）放在试点那一步，问过 Sheldon 再做。

口径（总方案「T2」一节、GM4 意见⑤）：

- **裁定**（每格最新一条，没有 u 的）：
  - 直接迁：裁定记的 `cells_sha`（格锚点，#899 回填）＝账上该页某一行的 `cells_sha`，u 取那一行的 map；
  - 宽松证明：没记 `cells_sha` 或对不上时，用账上该页**现行**切分的字（账行 `chars`）核裁定窗口——
    格号前后各 2 字与裁定 `ctx.left` 末 2 字、`ctx.right` 首 2 字比（逐字按本书归一表 `charnorm.same`；页首页尾只比账行有字的一侧）：
    **两侧都同**，或**一侧同且裁定字＝账上这格的字**（manager 拿不到候选，用现行文本的字代替 cv 的「字在候选」），过了取现行 u；
    裁定没记窗口（`ctx` 空）的证明不了，进清单；
  - 其余进清单（理由：账上没这一页／格号不在账里／窗口对不上／账行没记字）。
- **人裁**（每格最新一条算人裁的 confirm，`anchor` 没 u 的）：锚里 `cells_sha` 主段＝账上某行主段就取那行的 u（锚同切分）；
  否则人裁字（`shape` 字形或 `reading` 读作，任一）＝账上这格的字（按归一表）就迁；账上记的是文本字，「巳」形读「已」的要比 reading；
  没字可比时账上该页各行这格都是同一个 u（各版同格）也迁；其余进清单。
  （人裁的 `anchor.bbox` 是 `raw_page_px@top-right` 右上原点、图源也可能换过，和账里 cord 框不在一个坐标系，不拿来比。）
- **待审条目**：条目格号在账上该页现行 map 里 → 补 u（同 `reconcile(us=…)`）；不在 → 清单。

守恒：每类 `迁前 = 迁出 + 没迁`，对不上直接抛错。

真写（`apply`，`guji uid migrate-plan --write`）只追加：裁定、人裁各抄一条带 u 的新事件（id、批次名加 `~u`，
**ts、seq 不变**，同 `feedback/cell_migrate` 的 `~q` 做法，「后到覆盖」次序不变、内容只多 u）；裁定过 cv 写前校验，
过不了的（旧提示词版本，seed_admit 本来就不认）不抄、记下；待审条目追加一版补 `u`（op=u）。原事件不动。
"""
from __future__ import annotations

from collections import Counter

from .uid.ledger import Ledger


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


def _eq(a: str, b: str, same) -> bool:
    return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))


def plan_rulings(led: Ledger, rulings: list[dict], same=None) -> tuple[list[dict], list[dict]]:
    """rulings：本册每格最新一条裁定 payload（带 `cell`）。→ (迁出 [{cell, u, how, payload}], 清单 [{类别, 键, 理由}])。"""
    same = same or (lambda a, b: a == b)
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
        if not (ctx.get("left") or ctx.get("right")):
            left.append({"类别": "裁定", "键": cell, "理由": "裁定没记窗口，证明不了"})
            continue
        l2, r2 = (ctx.get("left") or "")[-2:], (ctx.get("right") or "")[:2]
        wl, wr = w[0][-2:], w[1][:2]
        # 页首／页尾账行这一侧不满 2 字（裁定窗口跨页）：只比账行有的那几个字；没字可比的一侧不算
        lok = _eq(l2[-len(wl):], wl, same) if wl else None
        rok = _eq(r2[:len(wr)], wr, same) if wr else None
        sides = [x for x in (lok, rok) if x is not None]
        char_ok = same(p.get("char") or "", (cur.get("chars") or {}).get(cell, ""))
        if sides and (all(sides) or (any(sides) and char_ok)):
            u = int(cur["map"][cell])
            out.append({"cell": cell, "u": u, "how": "宽松", "payload": {**p, "u": u}})
        else:
            left.append({"类别": "裁定", "键": cell,
                         "理由": f"窗口对不上（裁定 {l2}｜{r2}，现行 {w[0][-2:]}｜{w[1][:2]}）"})
    return out, left


def _sha_head(sha) -> str | None:
    """格锚 cells_sha 取主段：裁定、账行是 `行切分+…` 字符串，人裁锚是 {"row_segment": …} 字典。"""
    if isinstance(sha, dict):
        sha = sha.get("row_segment") or next(iter(sha.values()), None)
    return str(sha).split("+")[0] if sha else None


def plan_human(led: Ledger, humans: list[dict], same=None) -> tuple[list[dict], list[dict]]:
    """humans：本册每格最新一条人裁 {id, cell, shape?, reading?, cells_sha?, u?}。→ (迁出 [{id, cell, u, how}], 清单)。

    次序：① 锚里的 cells_sha 主段＝账上该页某一行的主段，且格在那一行 → 取那一行的 u（还没作废）；
    ② 人裁字（字形或读作，按归一表）＝账上字 → 迁；不等 → 清单；③ 没字可比时，账上该页各行这格都是同一个 u → 迁；④ 其余清单。"""
    same = same or (lambda a, b: a == b)
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
        head = _sha_head(h.get("cells_sha"))
        if head:
            hit = None
            for d in led.lines:
                if int(d["page"]) == pg and _sha_head(d.get("cells_sha")) == head and cell in d["map"]:
                    hit = d
            if hit is not None:
                hu = int(hit["map"][cell])
                if led.cell_of(hu) is not None:
                    out.append({"id": h["id"], "cell": cell, "u": hu, "how": "锚同切分"})
                    continue
        have = (cur.get("chars") or {}).get(cell, "")
        mine = [x for x in (h.get("shape"), h.get("reading")) if x]
        if mine and have:
            if any(same(x, have) for x in mine):
                out.append({"id": h["id"], "cell": cell, "u": u, "how": "字同"})
            else:
                left.append({"类别": "人裁", "键": cell, "理由": f"人裁「{'／'.join(dict.fromkeys(mine))}」，账上这格是「{have}」"})
            continue
        lines = [d for d in led.lines if int(d["page"]) == pg]
        if all(cell in d["map"] and int(d["map"][cell]) == u for d in lines):
            out.append({"id": h["id"], "cell": cell, "u": u, "how": "各版同格"})
            continue
        left.append({"类别": "人裁", "键": cell, "理由": "没字可比，且这格重切过"})
    return out, left


def plan_items(led: Ledger, items: list[dict]) -> tuple[list[dict], list[dict]]:
    """items：待审条目（各 id 的现行版本，`cell` 不带册前缀）。→ (迁出 [{id, cell, u}], 清单)。"""
    cur = led.u_map()
    out, left = [], []
    for r in items:
        if r.get("u") is not None:
            continue
        if r["cell"] in cur:
            out.append({"id": r["id"], "cell": r["cell"], "u": cur[r["cell"]], **({"_file": r["_file"]} if "_file" in r else {})})
        else:
            left.append({"类别": "待审条目", "键": f"{r['id']}（{r['cell']}）", "理由": "格号不在现行账里"})
    return out, left


def plan(led: Ledger, *, rulings: list[dict] = (), humans: list[dict] = (), items: list[dict] = (), same=None) -> dict:
    """→ {rulings, human, items, 清单, 守恒}；守恒不过就抛错。``same``：同字判定（`charnorm.load_norm(册).same`）。"""
    res: dict = {"清单": []}
    cons = {}
    for name, fn, src, has_u in (("rulings", plan_rulings, rulings, lambda x: "u" in x),
                                 ("human", plan_human, humans, lambda x: x.get("u") is not None),
                                 ("items", plan_items, items, lambda x: x.get("u") is not None)):
        todo = [x for x in src if not has_u(x)]
        got, left = fn(led, list(src), same) if fn is not plan_items else fn(led, list(src))
        res[name] = got
        res["清单"] += left
        cons[name] = {"迁前": len(todo), "迁出": len(got), "没迁": len(left)}
        if len(todo) != len(got) + len(left):
            raise AssertionError(f"{name} 不守恒：{cons[name]}")
    res["守恒"] = cons
    res["迁出方式"] = dict(Counter(x["how"] for x in res["rulings"]))
    res["人裁迁出方式"] = dict(Counter(x["how"] for x in res["human"]))
    return res


SUFFIX = "~u"


def _copy(e, *, payload: dict | None = None, anchor_u: int | None = None):
    from ._cv import Event
    d = e.model_dump(mode="json")
    d["id"] = e.id + SUFFIX
    d["batch"] = e.batch + SUFFIX
    if payload is not None:
        d["payload"] = payload
    if anchor_u is not None:
        d["target"]["anchor"] = {**(d["target"].get("anchor") or {}), "u": int(anchor_u)}
    return Event.model_validate(d)


def apply(res: dict, *, ruling_events: dict, human_events: dict, ruling_log, event_log) -> dict:
    """把 `plan` 的迁出真写进本地数据目录（只追加）。→ {裁定, 人裁, 待审条目, 裁定没抄, files}。"""
    from .ruling_write import screen
    from .review import pending_items as P
    files: set[str] = set()
    evs = [_copy(ruling_events[x["cell"]], payload={**x["payload"], "u_migrated": x["how"]}) for x in res["rulings"]]
    ok, bad = screen(evs) if evs else ([], [])
    if ok:
        ruling_log.append(ok)
        files |= {str(ruling_log.batch_path(b)) for b in {e.batch for e in ok}}
    hs = [_copy(human_events[x["id"]], anchor_u=x["u"]) for x in res["human"]]
    if hs:
        event_log.append(hs)
        files |= {str(event_log.batch_path(b)) for b in {e.batch for e in hs}}
    n_items = 0
    by_file: dict[str, list[dict]] = {}
    for x in res["items"]:
        by_file.setdefault(x["_file"], []).append(x)
    for f, xs in by_file.items():
        st = P.ItemStore(f)
        for x in xs:
            r = st.items.get(x["id"])
            if r is not None and r.get("u") is None:
                st.put(r, op="u", by="u-migrate", why="字格永久编号 u 存量迁移", u=int(x["u"]))
        n_items += st.save()
        files.add(f)
    return {"裁定": len(ok), "人裁": len(hs), "待审条目": n_items,
            "裁定没抄": [{"cell": e.payload.get("cell"), "理由": m} for e, m in bad], "files": sorted(files)}
