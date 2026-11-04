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


def test_pre_switch_vision_checks_ignored(tmp_path):
    """换源前的看图判错（锚里没有 source_rev，旧格号）不再让新格号进请审单。"""
    from guji_manager.feedback.vision import VisionLog, vision_checks, vision_flags
    _yaml(tmp_path / "books", "vol04", 3)
    _yaml(tmp_path / "books", "vol09", None)
    fb = tmp_path / "feedback"
    (fb / "vision").mkdir(parents=True)
    old = [_vision_ev("vol04:12:3:5", 1), _vision_ev("vol04:12:3:6", 2, v="unsure"), _vision_ev("vol09:1:1:1", 3)]
    (fb / "vision" / "vision-x.jsonl").write_text(
        "".join(e.model_dump_json() + "\n" for e in old), encoding="utf-8")       # 换源前写下的（写入口现在会拒）
    log = VisionLog(fb)
    assert vision_checks("vol04", log) == {} and vision_flags("vol04", log) == {}
    assert log.dropped == {"vision-x": {"vol04": 2}}                                # 不静默：丢了几条有数
    assert set(vision_flags("vol09", log)) == {"vol09:1:1:1"}                       # 没换源的册照旧
    log.append([_vision_ev("vol04:12:3:5", 4, rev=3)])                              # 换源后（带新 rev）照常生效
    assert set(vision_flags("vol04", log)) == {"vol04:12:3:5"}


def test_import_vision_needs_explicit_source_rev(tmp_path):
    """换过源的册：不给 --source-rev 整批报错（不抛异常、不写）；给了与册 yaml 相同的才写，读口照常认。
    不自动按产物盖 rev——旧格号的老文件重导一遍会被当成新图上的结论。"""
    from guji_manager.feedback.vision import VisionLog, import_vision, vision_flags
    _yaml(tmp_path / "books", "vol04", 3)
    src = tmp_path / "看图结论.jsonl"
    src.write_text(json.dumps({"cell": "vol04:1:1:3", "v": "wrong", "char": "曰", "shown": "日", "judge": "m"})
                   + "\n", encoding="utf-8")
    log = VisionLog(tmp_path / "feedback")
    res = import_vision(src, log, gold=False)
    assert res["written"] == 0 and "--source-rev" in res["errors"][0]
    assert import_vision(src, log, gold=False, source_rev=2)["written"] == 0           # 旧 rev 也不收
    res = import_vision(src, log, gold=False, source_rev=3)
    assert res["errors"] == [] and res["written"] == 1
    assert set(vision_flags("vol04", log)) == {"vol04:1:1:3"}


# ── 3. gold rebuild ─────────────────────────────────────────────────


