"""存量迁移提案：给一册已有的裁定、人裁、待审条目配上字格永久编号 u（T2，设计 doc/4-反馈迭代/设计-字格u改挂.md §二.7）。

**只出提案和清单，不写库**。真写（追加事件、推库）放在试点那一步，问过 Sheldon 再做。

口径（总方案「T2」一节、GM4 意见⑤）：

- **裁定**（每格最新一条，没有 u 的）：
  - 直接迁：裁定记的 `cells_sha`（格锚点，#899 回填）＝账上该页某一行的 `cells_sha`，u 取那一行的 map；
  - 宽松证明：没记 `cells_sha` 或对不上时，用账上该页**现行**切分的字（账行 `chars`）核裁定窗口——
    格号前后各 2 字与裁定 `ctx.left` 末 2 字、`ctx.right` 首 2 字比（逐字按本书归一表 `charnorm.same`；页首页尾只比账行有字的一侧）：
    **两侧都同**，或**一侧同且裁定字＝账上这格的字**（manager 拿不到候选，用现行文本的字代替 cv 的「字在候选」），过了取现行 u；
    裁定没记窗口（`ctx` 空，src-2 私用码记录等）：裁定字＝账上字迁（字同）；没字可比且账上各行这格同一个 u 迁（各版同格）；其余清单；
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

import json
from collections import Counter
from pathlib import Path

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
            # 没记窗口（src-2 私用码记录等）：裁定字＝账上字就迁；没字可比时账上该页各行这格都是同一个 u 也迁
            have = (cur.get("chars") or {}).get(cell, "")
            mine = p.get("char") or ""
            u = int(cur["map"][cell])
            if mine and have:
                if same(mine, have):
                    out.append({"cell": cell, "u": u, "how": "字同", "payload": {**p, "u": u}})
                else:
                    left.append({"类别": "裁定", "键": cell, "理由": f"没记窗口，裁定「{mine}」，账上这格是「{have}」"})
                continue
            if all(cell in d["map"] and int(d["map"][cell]) == u for d in led.lines if int(d["page"]) == pg):
                out.append({"cell": cell, "u": u, "how": "各版同格", "payload": {**p, "u": u}})
            else:
                left.append({"类别": "裁定", "键": cell, "理由": "没记窗口、没字可比，且这格重切过"})
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
            left.append({"类别": "人裁", "键": cell, "理由": "格号不在现行账里", "_h": h, "_why": "not_in_ledger"})
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
                left.append({"类别": "人裁", "键": cell, "理由": f"人裁「{'／'.join(dict.fromkeys(mine))}」，账上这格是「{have}」",
                             "_h": h, "_why": "char_diff"})
            continue
        lines = [d for d in led.lines if int(d["page"]) == pg]
        if all(cell in d["map"] and int(d["map"][cell]) == u for d in lines):
            out.append({"id": h["id"], "cell": cell, "u": u, "how": "各版同格"})
            continue
        left.append({"类别": "人裁", "键": cell, "理由": "没字可比，且这格重切过", "_h": h, "_why": "no_char_recut"})
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
            left.append({"类别": "待审条目", "键": f"{r['id']}（{r['cell']}）", "理由": "格号不在现行账里",
                         "_id": r["id"], "_file": r.get("_file")})
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


def copy_anchor_patches(event_log, copies) -> set[str]:
    """人裁 ``~u`` 抄件也要带上原件的补锚档（``feedback/anchors/<册>.jsonl``，按事件 id 查）：cv 绑定按 ``ev.id`` 查补锚档，
    抄件 id 多了 ``~u`` 就查不到框，老裁决判 unanchored、人裁绑不上（11-25 全唐文 vj1 004 册 2,036 格 human_unbound）。
    ``copies``＝[(原件 id, 抄件 id, 册)]；抄件已有的不重写（只追加）。→ 写过的文件。"""
    root = Path(event_log.events_dir).parent / "anchors"
    by_book: dict[str, dict[str, str]] = {}
    for old, new, book in copies:
        by_book.setdefault(str(book), {})[old] = new
    files: set[str] = set()
    for book, m in sorted(by_book.items()):
        f = root / f"{book}.jsonl"
        if not f.exists():
            continue
        raw = f.read_text(encoding="utf-8")
        lines = [json.loads(x) for x in raw.splitlines() if x.strip()]
        have = {d.get("event") for d in lines}
        last = {d["event"]: d for d in lines if d.get("event") in m and m[d["event"]] not in have}  # cv 读档后者覆盖：取最后一行
        add = [{**d, "event": m[e]} for e, d in last.items()]
        if add:
            with open(f, "a", encoding="utf-8") as fh:
                if raw and not raw.endswith("\n"):
                    fh.write("\n")
                fh.writelines(json.dumps(d, ensure_ascii=False, separators=(",", ":")) + "\n" for d in add)
            files.add(str(f))
    return files


def anchor_patch_ids(fb_root, book: str) -> set[str]:
    """``feedback/anchors/<册>.jsonl`` 里有补锚档的事件 id。"""
    f = Path(fb_root) / "anchors" / f"{book}.jsonl"
    if not f.exists():
        return set()
    return {json.loads(x).get("event") for x in f.read_text(encoding="utf-8").splitlines() if x.strip()}


def missing_anchor_copies(copies, patched: set[str]) -> list:
    """``~u`` 抄件缺补锚档：抄件自己没框（``target.anchor.bbox``）、补锚档里没有抄件 id、原件却有 → cv 绑不上（应为 0）。"""
    out = []
    for e in copies:
        if not str(e.id).endswith(SUFFIX) or (e.target.anchor or {}).get("bbox") or e.id in patched:
            continue
        if e.id[:-len(SUFFIX)] in patched:
            out.append(e)
    return out


def boxless_copies(copies, patched: set[str]) -> list:
    """``~u`` 人裁抄件既没框（``target.anchor.bbox``）也没补锚档：cv 只能按 ts／格号老规则认格，常认不上（应为 0）。"""
    return [e for e in copies if str(e.id).endswith(SUFFIX) and not (e.target.anchor or {}).get("bbox")
            and e.id not in patched]


ANCHOR_SPACE = "raw_page_px@top-right"     # 同 cv feedback.anchor.SPACE（Step3 quad_page 的外接框）


def u_anchor_fill(book: str, copies, led, store) -> tuple[list[dict], list[dict]]:
    """给无框无档的 ``~u`` 人裁抄件按身份账出补锚档行：u 在本页现行账行里的格 → 现行切分里这一格的框
    （cv ``bindings._cells_versions``＋``_cell_index``，同 cv 绑定口径）。账行 cells_sha 要等于现行产物戳，否则不补。
    → (补锚档行, 补不了的 [{event, key, u, why}])。不写文件。"""
    from ._cv import _cell_index, _cells_versions
    from .uid.source import page_cells_sha
    memo: dict[int, tuple] = {}
    out, bad = [], []
    for e in copies:
        a = e.target.anchor or {}
        u = a.get("u")
        key = str(e.target.key)
        parts = key.split(":")
        if u is None or len(parts) != 4:
            bad.append({"event": e.id, "key": key, "u": u, "why": "没 u 或格号不是 册:页:列:格"})
            continue
        page = int(parts[1])
        if page not in memo:
            sha = page_cells_sha(book, page, store)
            line = led.by_sha(page, sha) if sha else None
            if line is None:
                memo[page] = (None, "账里没有本页现行切分（先 guji uid sync）")
            else:
                vs = _cells_versions(book, page, store)
                cur = vs[-1] if vs and vs[-1][0] == "current" else None
                memo[page] = ({int(v): k for k, v in line["map"].items()}, _cell_index(cur[3]) if cur else {}, sha) \
                    if cur else (None, "本页没有现行切分产物")
        m = memo[page]
        if m[0] is None:
            bad.append({"event": e.id, "key": key, "u": u, "why": m[1]})
            continue
        inv, idx, sha = m
        cell = inv.get(int(u))
        if cell is None:
            bad.append({"event": e.id, "key": key, "u": u, "why": "u 不在本页现行账行（作废或拆并了）"})
            continue
        _, _, col, rest = cell.split(":")
        slot = rest.rstrip("abcdefghijklmnopqrstuvwxyz")
        hit = idx.get((int(col), int(slot), rest[len(slot):]))
        if not hit:
            bad.append({"event": e.id, "key": key, "u": u, "why": f"现行切分里没有 {cell} 的框"})
            continue
        out.append({"event": e.id, "key": key, "ts": e.ts, "shape": (e.payload or {}).get("shape"),
                    "anchor": {"v": 1, "space": ANCHOR_SPACE, "bbox": [round(float(x), 2) for x in hit[0]],
                               "source": "backfill:u", "cells_sha": sha},
                    "evidence": {"method": "u", "u": int(u), "at": cell.split(":", 2)[2]}})
    return out, bad


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
        files |= copy_anchor_patches(event_log, [(e.id[:-len(SUFFIX)], e.id, e.target.book or e.target.key.split(":")[0])
                                            for e in hs])
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


# ── 收口（2026-11-25，主导线程「u 彻底收尾」）：清单上的再救一批，其余作废记档或转待审 ──────────────────────────────

NEAR = 3          # 列内近邻：同页同列、前后各这么多格以内


def _col_of(cell: str) -> str | None:
    p = cell.split(":")
    return ":".join(p[:3]) if len(p) == 4 else None


def _neighbors(cur: dict, cell: str) -> list[str]:
    """现行账行里与 cell 同页同列、读序前后 NEAR 格以内的格号，按离得近排。cell 不在账里时按格位数字找最近的位置。"""
    col = _col_of(cell)
    if col is None:
        return []
    keys = [k for k in cur["map"] if _col_of(k) == col]
    if not keys:
        return []
    if cell in keys:
        i = keys.index(cell)
    else:
        def pos(k):
            try:
                return int(k.split(":")[3].rstrip("ab"))
            except ValueError:
                return 0
        try:
            want = int(cell.split(":")[3].rstrip("ab"))
        except ValueError:
            return []
        i = min(range(len(keys)), key=lambda j: abs(pos(keys[j]) - want))
        keys.insert(i, cell)
    out = []
    for d in range(1, NEAR + 1):
        for j in (i - d, i + d):
            if 0 <= j < len(keys) and keys[j] != cell:
                out.append(keys[j])
    if cell not in cur["map"]:
        keys.remove(cell)
    return out


def rescue_human(led: Ledger, left: list[dict], same=None, variant=None, taken: set | None = None) -> tuple[list[dict], list[dict]]:
    """清单上的人裁再救一批。→ (迁出 [{id, cell, u, how}], 仍没迁)。

    ⑤ 异体同：人裁字与账上这格的字是高置信异体（cv `variant_group`，如 愼／慎、說／説）→ 迁这格；
    ⑥ 列内近邻同字：同页同列前后 NEAR 格内，账上字＝人裁字（归一表或异体）的格**只有一个** → 迁那格（切分挪过一两格、
       九月旧格号＝列内顺序号的都靠这条）；那格的 u 已被别的人裁占了不算。"""
    same = same or (lambda a, b: a == b)
    variant = variant or (lambda a, b: False)
    taken = set(taken or ())

    def eq(a, b):
        return bool(a) and bool(b) and (same(a, b) or variant(a, b))
    out, rest = [], []
    for x in left:
        h = x.get("_h")
        if h is None:
            rest.append(x)
            continue
        cell = h["cell"]
        pg = _page_of(cell)
        cur = led.page(pg) if pg is not None else None
        mine = [c for c in (h.get("shape"), h.get("reading")) if c]
        if cur is None or not mine:
            rest.append(x)
            continue
        chars = cur.get("chars") or {}
        if cell in cur["map"] and any(variant(m, chars.get(cell, "")) for m in mine):
            u = int(cur["map"][cell])
            if u not in taken:
                out.append({"id": h["id"], "cell": cell, "u": u, "how": "异体同"})
                taken.add(u)
                continue
        hits = [k for k in _neighbors(cur, cell) if any(eq(m, chars.get(k, "")) for m in mine)
                and int(cur["map"][k]) not in taken]
        if len(hits) == 1:
            u = int(cur["map"][hits[0]])
            out.append({"id": h["id"], "cell": cell, "u": u, "how": "列内近邻同字", "now": hits[0]})
            taken.add(u)
            continue
        rest.append(x)
    return out, rest


def close_out(led: Ledger, left: list[dict], *, human_u: set | None = None) -> dict:
    """救不回来的清单怎么收：→ {void: [{stream, id, key, reason}], review: [{cell, u, h, detail}], withdraw: [{id, file}]}。

    - 裁定：一律作废（窗口对不上＝上下文变了，需要时文意重跑会重判；格号不在账＝格已没了）；旧提示词版本的另在 `apply` 后记；
    - 人裁「没字可比，且这格重切过」：判的是旧切分（切坏／非字等），切分已改 → 作废；
    - 人裁格号不在现行账、列内也找不到同字 → 作废（九月旧格号或格已删）；
    - 人裁字≠账上字、这格现在没有带 u 的人裁 → 转待审条目（pending_reason=recheck，让人对着现行切分重看）；已有带 u 的新人裁 → 作废；
    - 待审条目格号不在现行账 → 撤下（withdrawn，不删）。"""
    human_u = set(human_u or ())
    void, review, withdraw = [], [], []
    for x in left:
        cat = x["类别"]
        if cat == "裁定":
            void.append({"stream": "rulings", "id": None, "key": x["键"], "reason": x["理由"]})
        elif cat == "待审条目":
            withdraw.append({"id": x["_id"], "file": x.get("_file"), "reason": x["理由"]})
        else:
            h, why = x["_h"], x.get("_why")
            cell = h["cell"]
            if why == "char_diff":
                cur = led.page(_page_of(cell))
                u = int(cur["map"][cell])
                if u in human_u:
                    void.append({"stream": "events", "id": h["id"], "key": cell, "reason": x["理由"] + "；这格已有带 u 的人裁"})
                else:
                    review.append({"cell": cell, "u": u, "h": h, "now": (cur.get("chars") or {}).get(cell),
                                   "detail": f"u 迁移挂不上：{x['理由']}（切分变过，原人裁可能判的是挪走的那格），请对着现行切分重看"})
            else:
                void.append({"stream": "events", "id": h["id"], "key": cell,
                             "reason": x["理由"] + ("" if why == "no_char_recut" else "，列内近邻也找不到同字")})
    return {"void": void, "review": review, "withdraw": withdraw}


def void_path(event_log) -> "Path":
    from pathlib import Path
    return Path(event_log.events_dir).parent / "lists" / "u_void"


def check_close_inputs(co: dict | None, review_file: str | None) -> None:
    """收口要写之前先核输入：有人裁要转待审就必须有条目文件。放在任何写入（``apply``、``write_close``）之前调，
    免得 ~u 抄件、作废记档写了一半才报错（11-25 全唐文 046／082）。"""
    if co is not None and co.get("review") and not review_file:
        raise SystemExit(f"✗ 有 {len(co['review'])} 条人裁要转待审，但没给条目文件（--items 或 --review-items，"
                         "如 <数据目录>/feedback/lists/pending/<书>/<册>.items.jsonl，没有会新建）；什么都没写")


def write_close(book: str, co: dict, *, rescued: list[dict], unscreened: list[dict], human_events: dict, event_log,
                review_file: str | None) -> dict:
    """收口真写（只追加）：救回的人裁抄 `~u` 件；作废的记进 `feedback/lists/u_void/<册>.jsonl`（原事件不动）；
    转待审的开条目；撤下的条目 op=withdraw。→ {人裁救回, 作废, 转待审, 撤下, files}。"""
    check_close_inputs(co, review_file)
    import json
    from pathlib import Path
    from .review import pending_items as P
    files: set[str] = set()
    vp = void_path(event_log) / f"{book}.jsonl"
    seen = set()                       # 重跑不重复记：已记过的 (stream, id, key)
    if vp.exists():
        for line in vp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                seen.add((d.get("stream"), d.get("id"), d.get("key")))
    co = {**co, "void": [v for v in co["void"] if (v["stream"], v["id"], v["key"]) not in seen],
          "review": [r for r in co["review"] if ("events", r["h"]["id"], r["cell"]) not in seen]}
    unscreened = [x for x in unscreened if ("rulings", None, x.get("cell")) not in seen]
    hs = [_copy(human_events[x["id"]], anchor_u=x["u"]) for x in rescued]
    if hs:
        event_log.append(hs)
        files |= {str(event_log.batch_path(b)) for b in {e.batch for e in hs}}
        files |= copy_anchor_patches(event_log, [(e.id[:-len(SUFFIX)], e.id, e.target.book or e.target.key.split(":")[0])
                                            for e in hs])
    at = P.now()
    rows = [{"kind": "u_void", "book": book, **v, "at": at, "by": "u-migrate"} for v in co["void"]]
    rows += [{"kind": "u_void", "book": book, "stream": "rulings", "id": None, "key": x.get("cell"),
              "reason": f"旧提示词版本，seed_admit 不认（{x.get('理由')}）", "at": at, "by": "u-migrate"} for x in unscreened]
    n_void = len(rows)
    rows += [{"kind": "u_review", "book": book, "stream": "events", "id": r["h"]["id"], "key": r["cell"], "u": r["u"],
              "reason": r["detail"], "at": at, "by": "u-migrate"} for r in co["review"]]
    if rows:
        vp.parent.mkdir(parents=True, exist_ok=True)
        with open(vp, "a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        files.add(str(vp))
    n_rev = n_wd = 0
    if co["review"]:
        if not review_file:
            raise SystemExit("✗ 有人裁要转待审，但没给条目文件（--review-items）")
        rf = Path(review_file)
        st = P.ItemStore(rf, text_id=rf.parent.name, chapter=rf.name.split(".")[0])
        for r in co["review"]:
            h = r["h"]
            doc = {"pending_reason": "recheck", "recheck": True, "detail": r["detail"],
                   "note": r["detail"], "prior": {"human": h.get("shape") or h.get("reading"), "event": h["id"]}}
            add_recheck(st, P.norm_cell(r["cell"]), doc, u=r["u"], now_char=r.get("now"),
                        by="u-migrate", src="script:u-closeout")
            n_rev += 1
        st.save()
        files.add(str(rf))
    by_file: dict[str, list[dict]] = {}
    for w in co["withdraw"]:
        if w.get("file"):
            by_file.setdefault(w["file"], []).append(w)
    for f, ws in by_file.items():
        st = P.ItemStore(Path(f))
        for w in ws:
            r = st.items.get(w["id"])
            if r is not None and r.get("state") not in ("withdrawn", "closed"):
                st.withdraw(w["id"], by="u-migrate", why=f"u 迁移：{w['reason']}")
                n_wd += 1
        st.save()
        files.add(f)
    return {"人裁救回": len(hs), "作废": n_void, "转待审": n_rev, "撤下": n_wd, "files": sorted(files)}


# ── 全库自检（11-25，GM2 核出「有账册每格最新人裁没 u、也没作废／转待审」8,226 格：
#    根因是 migrate-plan 读事件走了 cv 的页表 rev 闸，换图源前的旧事件（cv 本就不采信）没进清单）──

NOT_HUMAN_SOURCES = ("auto", "llm", "vision", "knn_infer")


def is_human_cell(e, human_vs, counts_as_human) -> bool:
    """GM2 口径：confirm、unit=cell、payload.v ∈ HUMAN_VS、算人裁、payload.source 不是 auto／llm／vision／knn_infer。"""
    t = e.target
    p = e.payload or {}
    return (e.kind == "confirm" and t.unit == "cell" and p.get("v") in human_vs and counts_as_human(e)
            and str(p.get("source") or "") not in NOT_HUMAN_SOURCES)


def latest_by_key(evs, pre: str) -> dict:
    """每格最新一条（按 ts、批次、序号；`~u` 抄件 ts 同原件、批次名在后，所以排在原件之后）。"""
    out: dict = {}
    for e in sorted((e for e in evs if str(e.target.key).startswith(pre)), key=lambda e: (e.ts, e.batch, e.seq)):
        out[e.target.key] = e
    return out


def void_seen(event_log, book: str) -> set:
    """u_void 里记过的人裁事件 id（作废和转待审都算有去向）。"""
    import json
    vp = void_path(event_log) / f"{book}.jsonl"
    seen = set()
    if vp.exists():
        for line in vp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                if d.get("stream") == "events" and d.get("id"):
                    seen.add(d["id"])
    return seen


def unaccounted(latest: dict, seen: set) -> list:
    """每格最新人裁没 u、也没记作废／转待审的 → [Event]。全库收尾后应为空。"""
    return [e for k, e in sorted(latest.items())
            if not isinstance((e.target.anchor or {}).get("u"), int) and e.id not in seen]


# ── 转待审条目整理（11-25 QTW：同格一条、带候选字）──────────────────────────────────────────

CLOSEOUT_SRC = ("script:u-closeout", "script:u-closeout-web")
_NOT_CHAR = {"", "□", "〓", "■", "unrec", "unk", "?", "？"}


def _is_char(c) -> bool:
    return isinstance(c, str) and len(c) == 1 and c not in _NOT_CHAR


def _join(a, b, sep="／"):
    xs = []
    for v in (a, b):
        for x in (v.split(sep) if isinstance(v, str) else ([] if v is None else [v])):
            if x not in xs and x != "":
                xs.append(x)
    return sep.join(str(x) for x in xs) if all(isinstance(x, str) for x in xs) else xs[0] if xs else None


def merge_docs(a: dict, b: dict) -> dict:
    """两条转待审条目的 doc 合成一条：prior 各键合并（人裁字、票字、事件同时留），detail／note 用「；」接，alt 取并集。"""
    out = {**a, **{k: v for k, v in b.items() if k not in ("prior", "detail", "note", "alt")}}
    pa, pb = a.get("prior") or {}, b.get("prior") or {}
    out["prior"] = {k: _join(pa.get(k), pb.get(k)) for k in dict.fromkeys([*pa, *pb])}
    for k in ("detail", "note"):
        v = _join(a.get(k), b.get(k), sep="；")
        if v:
            out[k] = v
    alt = list(a.get("alt") or [])
    for x in b.get("alt") or []:
        if x.get("c") not in {y.get("c") for y in alt}:
            alt.append(x)
    if alt:
        out["alt"] = alt
    return out


def recheck_alt(doc: dict, now_char: str | None = None) -> list[dict]:
    """候选字：现行字、旧人裁字、票字（去重，非字占位不算）；已有的 alt 保留在前。"""
    alt = list(doc.get("alt") or [])
    have = {x.get("c") for x in alt}
    p = doc.get("prior") or {}
    for c, src in [(now_char, "now"), *[(x, "human") for x in str(p.get("human") or "").split("／")],
                   *[(x, "vote") for x in str(p.get("vote") or "").split("／")]]:
        if _is_char(c) and c not in have:
            alt.append({"c": c, "p": c, "src": src})
            have.add(c)
    return alt


def add_recheck(st, cell: str, doc: dict, *, u: int | None, now_char: str | None, by: str, src: str):
    """开一条转待审条目：这格已有活条目（open／resolved）就并进去（prior、候选合并），不另开；带候选字。"""
    live = [r for r in st.find(cell) if r["cell"] == cell and r["state"] in ("open", "resolved")]
    if live:
        r = live[0]
        merged = merge_docs(r.get("doc") or {}, doc)
        merged["alt"] = recheck_alt(merged, now_char)
        return st.put(r, op="add", by=by, why="u 迁移挂不上（并入）", doc=merged, state="open",
                      **({"u": u} if u is not None and r.get("u") is None else {}))
    doc = {**doc, "alt": recheck_alt(doc, now_char)}
    return st.add(cell, doc, by=by, src=src, why="u 迁移挂不上", u=u)


def tidy_recheck(st, chars: dict[str, str] | None = None, by: str = "u-migrate") -> dict:
    """就地整理已写出的转待审条目：同格多条（人裁一条＋网页票一条等）并成一条（留最早的，其余撤下、写明并入谁），
    并补候选字（现行字＋旧人裁字＋票字）。``chars``：{格号(不带册): 现行字}。→ {并掉, 补候选}。"""
    chars = chars or {}
    by_cell: dict[str, list[dict]] = {}
    for r in st.items.values():
        if r["state"] in ("open", "resolved"):
            by_cell.setdefault(r["cell"], []).append(r)
    merged = filled = 0
    for cell, rs in by_cell.items():
        ours = [r for r in rs if str(r.get("src") or "") in CLOSEOUT_SRC]
        if not ours:
            continue
        rs = sorted(rs, key=lambda r: (str(r.get("src") or "") in CLOSEOUT_SRC, r.get("at") or "", r["id"]))
        keep, rest = rs[0], rs[1:]
        doc = keep.get("doc") or {}
        for r in rest:
            doc = merge_docs(doc, r.get("doc") or {})
            st.put(r, op="withdraw", by=by, why=f"同格并入 {keep['id']}（u 迁移收口）", state="withdrawn")
            merged += 1
        alt = recheck_alt(doc, chars.get(cell))
        u = keep.get("u") if keep.get("u") is not None else next((r.get("u") for r in rest if r.get("u") is not None), None)
        if rest or alt != (keep.get("doc") or {}).get("alt") or (u is not None and keep.get("u") is None):
            if alt != (keep.get("doc") or {}).get("alt"):
                filled += 1
            st.put(keep, op="edit", by=by, why="u 迁移收口：同格合并、补候选字", doc={**doc, "alt": alt},
                   **({"u": u} if u is not None and keep.get("u") is None else {}))
    return {"并掉": merged, "补候选": filled}
