"""回库贴错图核查与重入库（2026-11-27，史記 11-26 回库 7,257 例）。

## 为什么

`glyphdb_admit` 取图用事件原键，而字块缓存是现行切分的；事件裁于更早的切分，换过切分的页就取到邻格
（修在 manager #1105：无产物不再按原键取图）。已进库的这批例要按 cv `book_bindings` 重新对一遍。

## 做什么

窗口 `[after, before)` 内进库、证据里带事件 id 的**人裁**刻例，按事件在现行切分上的绑定分三类：

- `keep`     绑到同一格且可用（`valid`／`rebound` 且 bound＝库键）：不动；
- `rebind`   绑到别的格且可用：撤旧例，在绑定的格重取图入库（库键换成新格）；
- `withdraw` 绑定不可用（待审、作废、无锚裁于现行切分之前）：撤库，格由 `evict_review` 闸转待审；
- `no_products` 本机没有该页现行切分产物，算不出：不动（要到有产物的机器上跑）；
- `no_row`   页有产物但绑定表没有这条事件（被后来的裁决顶掉等）：不动，列出来人看。

`plan()` 只读，出 TSV。`apply()` 另起，必须带人的确认说明；撤掉的旧例连图与证据记进 undo 文件，`undo()` 可原样回退。
"""
from __future__ import annotations

import base64
import csv
import json
import sqlite3
from pathlib import Path

COLS = ["instance", "book", "char", "event", "admitted_at", "key", "bound", "status", "action", "new_instance"]


def _window_rows(db, after: str, before: str, books: set[str] | None):
    q = ("SELECT instance_id, char, provenance, evidence, admitted_at FROM admissions "
         " WHERE admitted_at >= ? AND admitted_at < ? AND provenance LIKE 'human%'")
    for iid, ch, _prov, ev, at in db.conn.execute(q, (after, before)):
        try:
            evid = (json.loads(ev) if isinstance(ev, str) else (ev or {})).get("event")
        except Exception:  # noqa: BLE001
            evid = None
        parts = iid.split(":")
        if parts[0] == "v2":
            parts = parts[1:]
        if len(parts) != 4 or not parts[1].isdigit():
            continue
        if books and parts[0] not in books:
            continue
        yield iid, parts[0], int(parts[1]), ch, evid, at


def plan(db, after: str, before: str, books: set[str] | None = None, bindings_of=None,
         has_products=None) -> list[dict]:
    """只读：窗口内人裁刻例逐例分类。`bindings_of(book)` → `{event_id: 绑定行}`，`has_products(book, page)` → bool；
    缺省走 cv（`book_bindings`／`_cells_versions`）。"""
    from .._cv import bindings_usable as usable
    if bindings_of is None or has_products is None:
        from .._cv import ProductStore, _cells_versions, book_bindings
        store = ProductStore()
        if bindings_of is None:
            bindings_of = lambda b: book_bindings(b, store=store)           # noqa: E731
        if has_products is None:
            def has_products(b, p):
                v = _cells_versions(b, p, store)
                return bool(v) and v[-1][0] == "current"
    memo: dict[str, dict] = {}
    out = []
    for iid, book, page, ch, evid, at in sorted(_window_rows(db, after, before, books)):
        r = {"instance": iid, "book": book, "char": ch, "event": evid or "", "admitted_at": at,
             "key": iid[3:] if iid.startswith("v2:") else iid, "bound": "", "status": "", "action": "", "new_instance": ""}
        if not has_products(book, page):
            r["action"] = "no_products"
        else:
            if book not in memo:
                memo[book] = bindings_of(book)
            row = memo[book].get(evid) if evid else None
            if row is None:
                r["action"] = "no_row"
            else:
                r["status"] = row.get("status", "")
                b = usable(row)
                r["bound"] = b or ""
                if b is None:
                    r["action"] = "withdraw"
                elif b == r["key"]:
                    r["action"] = "keep"
                else:
                    r["action"] = "rebind"
                    r["new_instance"] = "v2:" + b
        out.append(r)
    return out


def write_tsv(rows: list[dict], path: str | Path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLS, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def read_tsv(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def summary(rows: list[dict]) -> str:
    c: dict[str, int] = {}
    for r in rows:
        c[r["action"]] = c.get(r["action"], 0) + 1
    return "，".join(f"{k} {v}" for k, v in sorted(c.items())) or "无"


def _snapshot(db, iid: str) -> dict | None:
    r = db.conn.execute("SELECT a.char, a.provenance, a.evidence, a.admitted_at, i.patch_png, i.page, i.col, i.idx "
                        "FROM admissions a JOIN instances i USING(instance_id) WHERE a.instance_id=?", (iid,)).fetchone()
    if r is None:
        return None
    ch, prov, ev, at, png, page, col, idx = r
    return {"instance": iid, "char": ch, "provenance": prov, "evidence": ev, "admitted_at": at,
            "png": base64.b64encode(bytes(png)).decode(), "page": page, "col": col, "idx": idx}


def apply(db, rows: list[dict], confirmed_by: str, undo_path: str | Path, cache=None, batch: str = "rebind-audit",
          include_rebind: bool = False) -> dict:
    """真写。`confirmed_by` 必填（谁确认的，记进撤库原因与 undo）。只处理 action 为 rebind／withdraw 的行。
    撤掉的旧例（含图）记进 `undo_path`（jsonl，追加）。重入库取图失败（缓存没有）的 rebind 行不撤旧例。

    缺省**只执行 withdraw**（CV0 11-27：SJ 给无框旧人裁补带锚 confirm，rebind 类由新事件正常回库，免得重复入库）。
    `include_rebind=True` 才处理 rebind，且新格已在库里的跳过（`rebind_skip_exists`），不撤旧例。"""
    if not (confirmed_by or "").strip():
        raise ValueError("apply 必须说明谁确认的（--confirmed-by）")
    import cv2
    import numpy as np
    from .._cv import binarize_page, evict_instance, resolve_patch_key
    if cache is None:
        from .._cv import ImageCache
        cache = ImageCache()
    res = {"withdrawn": 0, "rebound": 0, "rebind_no_image": 0, "rebind_exists": 0, "rebind_skip_exists": 0, "missing": 0}
    reason = f"{batch}:{confirmed_by}"
    with open(undo_path, "a", encoding="utf-8") as uf:
        for r in rows:
            act = r["action"]
            if act not in ("rebind", "withdraw") or (act == "rebind" and not include_rebind):
                continue
            if act == "rebind" and db.conn.execute("SELECT 1 FROM admissions WHERE instance_id=?",
                                                    (r["new_instance"],)).fetchone():
                res["rebind_skip_exists"] += 1
                continue
            snap = _snapshot(db, r["instance"])
            if snap is None:
                res["missing"] += 1
                continue
            new_png = None
            if act == "rebind":
                try:
                    _b, pg, col, slot = r["bound"].split(":")
                    sub = slot[-1] if slot[-1] in "ab" else ""
                    slot_n = slot[:-1] if sub else slot
                    ckey = f"p{int(pg):04d}c{int(col):02d}s{int(slot_n)}{sub}"
                    path = cache.get(r["book"], "char_patch", resolve_patch_key(r["book"], ckey))
                    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE) if path else None
                except Exception:  # noqa: BLE001
                    img = None
                if img is None:
                    res["rebind_no_image"] += 1
                    continue
                new_png = cv2.imencode(".png", binarize_page(img, edge_margin=0))[1].tobytes()
            uf.write(json.dumps({**snap, "action": act, "new_instance": r["new_instance"]}, ensure_ascii=False) + "\n")
            uf.flush()
            evict_instance(db, r["instance"], reason=reason)
            res["withdrawn"] += act == "withdraw"
            if act == "rebind":
                ev = json.loads(snap["evidence"]) if isinstance(snap["evidence"], str) else dict(snap["evidence"] or {})
                ev["rebind_from"] = r["instance"]
                _b, pg, col, slot = r["bound"].split(":")
                sn = slot[:-1] if slot[-1] in "ab" else slot
                ok = db.admit_instance(r["new_instance"], snap["char"], new_png, provenance=snap["provenance"],
                                       shape=snap["char"], evidence=ev, page=pg, col=int(col), idx=int(sn))
                res["rebound" if ok else "rebind_exists"] += 1
    db.conn.commit()
    return res


def undo(db, undo_path: str | Path) -> dict:
    """按 undo 文件原样回退：撤掉 rebind 出来的新例，旧例连图带证据放回。"""
    from .._cv import evict_instance
    n = {"restored": 0, "new_evicted": 0}
    for line in Path(undo_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        s = json.loads(line)
        if s["action"] == "rebind" and s.get("new_instance"):
            evict_instance(db, s["new_instance"], reason="rebind-audit-undo")
            n["new_evicted"] += 1
        db.conn.execute("DELETE FROM evictions WHERE instance_id=?", (s["instance"],))
        ev = json.loads(s["evidence"]) if isinstance(s["evidence"], str) else s["evidence"]
        if db.admit_instance(s["instance"], s["char"], base64.b64decode(s["png"]), provenance=s["provenance"],
                             shape=s["char"], evidence=ev, page=s["page"], col=s["col"], idx=s["idx"]):
            n["restored"] += 1
    db.conn.commit()
    return n
