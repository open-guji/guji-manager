"""swap 同迁裁定（裁定键长期方案，GM4／CV0 2026-11-24）：换包时按对照表（cell_table）给裁定追加迁移事件。

背景：裁定挂在格号上（精确键没中时靠「格号＋cells_sha＋整理本字」的格锚点找回）。重切后格号变（改号）、
或页产物戳 cells_sha 变（同格号但整页重切），旧裁定就找不回。对照表已经知道「旧格→新格」，这里把它顺手用上：

- kind 为「同格」「改号」且新旧格上的字相同（oc＝nc）：追加一条新事件（新格号＋新 cells_sha＋同字同把握同版本，
  payload 记 `migrated_from`）；旧事件不动，后到覆盖。字变了的格不迁（那是另一个字，旧裁定不作数）。
- 「删」「新增」不迁；没有对照表（没 cell-map）的重切不走这里。
- 新 cells_sha 取新产物的 `page_cells_sha`（取不到就不迁，不写半截锚点）。
- 迁移是数据改动：改完那册要显式 force 重放 seed_admit；`u` 落地后这一整块退役。
"""
from __future__ import annotations
from ..products_io import RULING_STEP

from pathlib import Path
from typing import Callable


def plan(rows: list[dict], book: str, by_cell: dict[str, dict], sha_of: Callable[[int], str | None]) -> list[dict]:
    """→ 清单行 {old, new, 结果, 原因, payload?}；只含库里有裁定的旧格。`sha_of(页)` → 新页产物戳。"""
    out: list[dict] = []
    for r in rows:
        old = r.get("old")
        p = by_cell.get(f"{book}:{old}") if old else None
        if not p:
            continue
        base = {"old": old, "new": r.get("new") or ""}
        kind = r.get("kind")
        if kind not in ("同格", "改号"):
            out.append({**base, "结果": "不迁", "原因": f"旧格{kind}"})
            continue
        if (r.get("oc") or "") != (r.get("nc") or ""):
            out.append({**base, "结果": "不迁", "原因": f"字变了（{r.get('oc')}→{r.get('nc')}）"})
            continue
        new = r["new"]
        try:
            page = int(new.split(":")[0])
        except (ValueError, IndexError):
            out.append({**base, "结果": "不迁", "原因": "新格号读不出页"})
            continue
        sha = sha_of(page)
        if not sha:
            out.append({**base, "结果": "不迁", "原因": "新产物取不到切分戳"})
            continue
        if kind == "同格" and p.get("cells_sha") == sha:
            continue            # 页没动，不用迁
        out.append({**base, "结果": "迁", "原因": kind,
                    "payload": {**p, "cell": f"{book}:{new}", "cells_sha": sha, "migrated_from": f"{book}:{old}"}})
    return out


def migrate(rows: list[dict], book: str, store, batch: str, products: Path, *, write: bool = False) -> list[dict]:
    """对照表 → 迁移事件。`store`＝RulingStore；`products`＝新产物根（读 page_cells_sha）。"""
    from .. import ruling_anchor
    from .. import ruling_hits as RH
    from .._cv import RULING_KIND, EventTarget, make_event
    from ..ruling_write import append_rulings, screen
    by_cell = RH._rulings_by_cell_all(store)
    cache: dict[int, str | None] = {}

    def sha_of(page: int):
        if page not in cache:
            cache[page] = ruling_anchor.page_sha(Path(products), book, page)
        return cache[page]

    res = plan(rows, book, by_cell, sha_of)
    todo = [x for x in res if x["结果"] == "迁"]
    if todo:
        log = store.log
        seq = max((e.seq for e in log.read(batch, raw=True)), default=0)
        evs = []
        for x in todo:
            seq += 1
            evs.append(make_event(batch, seq, RULING_KIND, EventTarget(step=RULING_STEP, unit="cell", key=x["payload"]["cell"], book=book),
                                  x["payload"], actor="model"))
        ok, bad = screen(evs)
        bad_ids = {id(e): m for e, m in bad}
        for x, e in zip(todo, evs):
            if id(e) in bad_ids:
                x["结果"], x["原因"] = "不迁", "cv 写前校验不过：" + bad_ids[id(e)][:120]
        if write and ok:
            append_rulings(log, ok)
    for x in res:
        x.pop("payload", None)
    return res
