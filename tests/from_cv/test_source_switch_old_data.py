# -*- coding: utf-8 -*-
"""换图源后旧格号数据的三处读口（GUJI-748，v0.5.29）：数据全部自己造，不读工作区。

1. 换单门（`republish.votes_gate`）：旧单出在换源前时，旧格号的票经 ~q 迁移事件（`anchor.migrated_from`）
   或格级对照表对到新格再看落没落；无法对位的列清单、写文件，不笼统拦。
2. 看图结论（`feedback/vision/`）：换源前的（锚里没有 source_rev）不进请审单、不让导出标 pending；
   换源后导入的带上产物的 source_rev。
3. `gold rebuild`：换源前的事件不重放；同 id 的旧条目已标 stale 时，新页表的事件另立新条目，不拿旧条目打底。
"""
from __future__ import annotations

from cv_paths import CV_REPO  # cv 仓根（本测试从 cv tests/ 搬来）
import gzip
import importlib.util
import json
from pathlib import Path

import pytest

import open_guji_cv.steps  # noqa: F401  注册产物种类
from open_guji_cv.feedback.events import EventLog, EventTarget, make_event

SCRIPTS = CV_REPO / "scripts" / "zhengli"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"zhengli_{name}_ss", SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rp = _load("republish")


def _yaml(books: Path, book: str, rev: int | None) -> None:
    books.mkdir(parents=True, exist_ok=True)
    (books / f"{book}.yaml").write_text(f"id: {book}\n" + (f"source_rev: {rev}\n" if rev is not None else ""),
                                        encoding="utf-8")


def _cell_ev(key: str, seq: int, *, rev=None, migrated_from: str | None = None, ts="2026-10-20T00:00:00Z",
             payload=None, batch="b", step="seed_admit"):
    book, pg, col, slot = key.split(":")
    anchor = {}
    if rev is not None:
        anchor["source_rev"] = rev
    if migrated_from:
        anchor["migrated_from"] = {"key": migrated_from, "id": f"evt_old_{seq}"}
    e = make_event(batch, seq, "confirm",
                   EventTarget(step=step, unit="cell", key=key, book=book, page=int(pg), col=int(col),
                               slot=int(slot), anchor=anchor or None),
                   payload or {"v": "confirm", "shape": "甲"}, source_format="server")
    return e.model_copy(update={"ts": ts})


# ── 1. 换单门 ────────────────────────────────────────────────────────

def _ws_switched(tmp_path: Path) -> Path:
    """没迁中心库的工作区（数据根就是工作区）：vol06 已换源（source_rev 3）。"""
    ws = tmp_path / "abc123-书"
    _yaml(ws / "books", "vol06", 3)
    log = EventLog(ws / "feedback")
    log.append([
        _cell_ev("vol06:1:1:2", 1, rev="3", migrated_from="vol06:3:1:2", batch="old~q"),   # 换源前已落、迁过来的
        _cell_ev("vol06:1:1:5", 2, rev="3", batch="new"),                                  # 换源后在新格上落的
    ])
    e = _cell_ev("vol06:1:1:6", 9, rev="3", batch="page~q")             # 早先整页迁移脚本：migrated_from 只记旧页号
    e.target.anchor["migrated_from"] = {"book": "vol06", "page": 3, "source": "siku-qiefen-v2"}
    log.append([e])
    return ws


def _table(path: Path) -> Path:
    rows = ["旧格\t新格\t旧字\t新字\t类别\tIoU\t说明",
            "vol06:3:1:2\tvol06:1:1:2\t甲\t甲\t同格\t0.9\t",
            "vol06:3:1:5\tvol06:1:1:5\t乙\t乙\t同格\t0.9\t",
            "vol06:3:1:7\tvol06:1:1:7\t丙\t丙\t改号\t0.8\t",
            "vol06:3:1:8\tvol06:1:1:8\t丁\t丁\t同格\t0.3\t",
            "vol06:3:1:9\t\t戊\t\t删\t0\t新图无此格"]
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n")
    return path


def _votes():
    v = lambda a, choice="char", ch="甲": {"book": "abc123", "rev": "006-r5", "a": a, "choice": choice,
                                          "char": ch, "voter": "u1", "ts": 1792000000000}
    return [v("3:1:2"), v("3:1:5"), v("3:1:6"), v("3:1:7"), v("3:1:8"), v("3:1:9"), v("4:1:1"), v("5:1:1", "unsure")]


OLD_SHEET = {"rev": "006-r5", "routed_as_of": "2026-10-24T03:29:13Z"}       # 换源前出的单，还没记 source_rev


# ── 2. 看图结论 ──────────────────────────────────────────────────────

def _vision_ev(key, seq, v="wrong", rev=None):
    from guji_manager.feedback.vision import _STEP
    book, pg, col, slot = key.split(":")
    return make_event("vision-x", seq, "vision_check",
                      EventTarget(step=_STEP, unit="cell", key=key, book=book, page=int(pg), col=int(col),
                                  slot=int(slot), anchor=None if rev is None else {"source_rev": rev}),
                      {"source": "vision", "judge": "m", "v": v, "char": "曰", "shown": "日"}, actor="model")


# ── 3. gold rebuild ─────────────────────────────────────────────────

def test_rebuild_does_not_revive_pre_switch_verdicts(tmp_path):
    from guji_manager.feedback.routes import RouteTable
    from open_guji_cv.gold.store import GoldStore
    from guji_manager.gold.transfer import rebuild_verdicts
    _yaml(tmp_path / "books", "vol01", 3)
    log = EventLog(tmp_path / "feedback")
    log.events_dir.mkdir(parents=True)
    old = [_cell_ev("vol01:5:3:4", 1, payload={"v": "seg_defect", "quality": "truncated"}, step="cell_shrink"),
           _cell_ev("vol01:9:1:1", 2, payload={"v": "seg_defect", "quality": "truncated"}, step="cell_shrink")]
    (log.events_dir / "old.jsonl").write_text("".join(e.model_dump_json() + "\n" for e in old), encoding="utf-8")
    store = GoldStore(tmp_path / "verdicts")
    table = RouteTable.load(log.root / "routes.yaml")
    shard = table.plan(old)["gold_add"][0][1].shard
    # 换源前重放出来、后来标了 stale 的两条（同 10-27 apply.py）
    from open_guji_cv.gold.item import Anchor, GoldItem
    store.upsert(shard, [GoldItem(id=e.target.key, anchor=Anchor(book="vol01", page=e.target.page, col=e.target.col,
                                                                   slot=e.target.slot),
                                  expected={"quality": "truncated", "note": "旧图"}, source_events=[e.id])
                         for e in old], "旧")
    store.mark_stale(shard, [e.target.key for e in old], "GUJI-748 换源")
    # 换源后：迁移事件落在新格 vol01:5:3:4（与旧格同号）
    new = _cell_ev("vol01:5:3:4", 3, rev="3", migrated_from="vol01:7:3:4", batch="m~q",
                   payload={"v": "seg_defect", "quality": "clean"}, step="cell_shrink")
    log.append([new])
    out = rebuild_verdicts(log, store, table)
    assert out["events"] == 1 and out["dropped_by_source_rev"] == {"vol01": 2}
    items = {i.id: i for i in store.list(shard)}
    assert items["vol01:9:1:1"].status == "stale"                                  # 旧裁决不复活
    it = items["vol01:5:3:4"]
    assert it.status == "active" and it.expected == {"quality": "clean"}           # 不拿旧条目打底（note 不漏进来）
    assert it.source_events == [new.id] and it.anchor.source_rev == 3
    assert any("换源" in h.why or "页表" in h.change for h in it.history)
    # 再重放一遍：幂等
    rebuild_verdicts(log, store, table)
    again = {i.id: i for i in store.list(shard)}
    assert again["vol01:5:3:4"].expected == {"quality": "clean"} and again["vol01:9:1:1"].status == "stale"


