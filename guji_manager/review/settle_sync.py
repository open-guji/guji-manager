"""待审条目对账：格已落定，就把还开着的条目标成 resolved，并记下是哪条裁定事件（清理计划 v2 步骤 2.2，11-27）。

背景：条目（`pending_items`）只有 `guji feedback cellvotes write`、`collect` 和手动 `pending resolve` 会标 resolved；
控制台、各书线脚本写裁定时都不碰条目，条目就一直 open，库里 open 数比网站显示数多。网站（Worker `pendinglive.ts`）读时现算
把「已落定」的格藏掉，这里把同一口径真写进库，让两边数一致。

## 口径（只在这里＋`levels.py` 定义，Worker 是镜像）

- 配格：`(书, 册, u)` 三元组。条目的册＝所在文件名（章号 `046`、`01`）；事件的册在 `target.key` 的前缀（`01:11:6:10`、`vol46:…`、
  `004:…`），去 `vol` 前缀、前导 0 后比。**只按 u 配会跨册误配**（u 是册内唯一的，史記 26 册与 38 册都有 u=26933）。
- 事件够不够格：`levels.settles_cell`（kind=confirm、单位 cell、`payload.v` ∈ SETTLED_VS、level 为 human 或 ai；
  「AI 判字、人点按钮确认」算人裁，不改判）。
- **复审格**（条目 `doc.recheck`）：机器或脚本对旧人裁有异议、按设计要人再看。只有**裁定晚于这条复审开出**才关；
  复审开出的时刻＝条目最近一段连续「open 且 recheck」的第一版的 `at`。其他条目有落定裁定就关，不论早晚
  （已裁格不因重出单重开，协调者 11-24 定，和网站现算一致）。
- 同一格有多条够格的事件：记**最晚**的一条（`ts`，同 ts 取 id 大者）。

只动 `state == "open"` 的条目；撤下（withdrawn）、已关（closed）、已裁（resolved）的不碰。

## 入口

- 纯函数 `plan(items, events)`：不读库不写盘，测试用它。
- `load_events(conn, ws, us)`：从中心库取这批 u 的够格事件（读接口就够）。
- `sync_workspace(conn, ws, data, apply)`：扫数据目录 `feedback/lists/pending/*/*.items.jsonl`，对账，`apply` 才追加 resolved 版本。
- `guji pending-settle`（`cli_settle.py`）：命令行；执行方定时用 `GUJI_PENDING_SETTLE_S`（jobs runner）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ..feedback import levels as L
from . import pending_items as P

BY = "settle-sync"


def norm_vol(v: str) -> str:
    """册标签归一：去 `vol` 前缀和前导 0（同 Worker `normVol`）。"""
    v = str(v).lower()
    if v.startswith("vol"):
        v = v[3:]
    return v.lstrip("0") or ("0" if v else "")


def key_is_cell(key, vol: str, cell: str | None) -> bool:
    """事件格键（`<册>:<页>:<列>:<序>`）是不是这一册的这一格（同 Worker `keyIsCell`）。"""
    if not isinstance(key, str) or not cell:
        return False
    if not key.endswith(":" + cell):
        return False
    return norm_vol(key[: len(key) - len(cell) - 1]) == norm_vol(vol)


def recheck_since(history: list[dict]) -> str | None:
    """一条目的全部版本（按文件顺序）→ 这条复审**开出**的时刻；当前不是 open+recheck 返回 None。"""
    since = None
    for r in history:
        on = r.get("state") == "open" and bool((r.get("doc") or {}).get("recheck"))
        if on:
            since = since or r.get("at") or ""
        else:
            since = None
    return since


def _ev_rank(e: dict):
    return (str(e.get("ts") or ""), str(e.get("id") or ""))


def plan(items: Iterable[dict], events: Iterable[dict], histories: dict[str, list[dict]] | None = None) -> list[dict]:
    """要标 resolved 的条目。

    items：条目当前版本（`ItemStore.items.values()`，要有 id、u、cell、state、doc；`vol` 取 `item["vol"]`，缺则看调用方塞的 `_vol`）；
    events：已过 `levels.settles_cell` 的事件摘要 `{id, u, key, ts}`；
    histories：条目 id → 全部版本（复审开出时刻用）；缺省时用当前版本的 `at`。
    返回 `[{item, event, why, recheck}]`，每条目至多一项。"""
    by_u: dict[int, list[dict]] = {}
    for e in events:
        if e.get("u") is not None:
            by_u.setdefault(int(e["u"]), []).append(e)
    out = []
    for it in items:
        if it.get("state") != "open" or it.get("u") is None or not it.get("cell"):
            continue
        vol = it.get("_vol") or it.get("vol") or ""
        hits = [e for e in by_u.get(int(it["u"]), []) if key_is_cell(e.get("key"), vol, it["cell"])]
        if not hits:
            continue
        ev = max(hits, key=_ev_rank)
        rc = bool((it.get("doc") or {}).get("recheck"))
        if rc:
            since = recheck_since((histories or {}).get(it["id"]) or [it]) or it.get("at") or ""
            if str(ev.get("ts") or "") <= since:       # 裁定没有晚于复审开出：这条复审还要人看
                continue
        out.append({"item": it, "event": ev, "recheck": rc,
                    "why": f"对账：同册该格已有落定裁定（{ev['id']}，{ev.get('ts') or '?'}）"})
    return out


# ---- 读库／读盘 ----

_EV_SQL = """SELECT e.id, e.u, e.ts, e.kind, e.actor, e.batch, e.level,
       json_extract(e.target, '$.key') AS k, json_extract(e.target, '$.unit') AS unit,
       json_extract(e.payload, '$.v') AS v, json_extract(e.payload, '$.source') AS source,
       json_extract(e.payload, '$.level') AS plevel
  FROM events e
 WHERE e.ws = ? AND e.stream = 'events' AND e.kind = 'confirm' AND e.u IN (SELECT value FROM json_each(?))
   AND json_extract(e.target, '$.unit') = 'cell'
   AND json_extract(e.payload, '$.v') IN (SELECT value FROM json_each(?))"""


def load_events(conn, ws: str, us: list[int], chunk: int = 1500) -> list[dict]:
    """这批 u 的够格裁定事件（按 `levels.settles_cell` 再过一遍：库里 `level` 列与 manager 口径的已知分歧不在此放行）。"""
    out: list[dict] = []
    us = sorted(set(int(u) for u in us))
    for i in range(0, len(us), chunk):
        rows = conn.execute(_EV_SQL, (ws, json.dumps(us[i:i + chunk]), json.dumps(list(L.SETTLED_VS)))).fetchall()
        for r in rows:
            eid, u, ts, kind, actor, batch, level, key, unit, v, source, plevel = r
            ev = {"kind": kind, "actor": actor, "batch": batch, "target": {"unit": unit, "key": key},
                  "payload": {k: x for k, x in (("v", v), ("source", source), ("level", plevel)) if x is not None}}
            if L.settles_cell(ev):
                out.append({"id": eid, "u": u, "key": key, "ts": ts})
    return out


def read_histories(path: Path) -> dict[str, list[dict]]:
    h: dict[str, list[dict]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                h.setdefault(r["id"], []).append(r)
    return h


def pending_files(data: Path) -> list[Path]:
    root = Path(data) / "feedback" / "lists" / "pending"
    return sorted(root.glob("*/*.items.jsonl")) if root.is_dir() else []


def sync_workspace(conn, ws: str, data: Path, apply: bool = False, by: str = BY) -> dict:
    """扫一个工作区数据目录的全部条目文件，对账。返回 `{files, open, resolved, recheck_kept, rows: [...]}`；
    `apply` 才追加版本（`ItemStore.resolve`），不重导整张单（网站按现算藏掉已落定的格，整张单不必动）。"""
    stores = []
    for f in pending_files(data):
        text_id, chapter = f.parent.name, f.name.split(".", 1)[0]
        s = P.ItemStore.open(data, text_id, chapter)
        stores.append((s, read_histories(f), chapter))
    us = sorted({int(r["u"]) for s, _, _ in stores for r in s.items.values()
                 if r.get("state") == "open" and r.get("u") is not None})
    events = load_events(conn, ws, us) if us else []
    res = {"files": len(stores), "open": 0, "resolved": 0, "recheck_resolved": 0, "recheck_kept": 0, "rows": []}
    for s, hist, chapter in stores:
        opens = [dict(r, _vol=chapter) for r in s.items.values() if r.get("state") == "open"]
        res["open"] += len(opens)
        todo = plan(opens, events, hist)
        res["recheck_kept"] += sum(1 for r in opens if (r.get("doc") or {}).get("recheck")
                                   and r["id"] not in {t["item"]["id"] for t in todo}
                                   and r.get("u") is not None
                                   and any(key_is_cell(e.get("key"), chapter, r["cell"])
                                           for e in events if e["u"] == r["u"]))
        for t in todo:
            it = t["item"]
            res["resolved"] += 1
            res["recheck_resolved"] += t["recheck"]
            res["rows"].append({"book": s.text_id, "vol": chapter, "cell": it["cell"], "u": it["u"], "item": it["id"],
                                "event": t["event"]["id"], "recheck": t["recheck"]})
            if apply:
                s.resolve(it["id"], by=by, event=t["event"]["id"], why=t["why"])
        if apply:
            s.save()
    return res
