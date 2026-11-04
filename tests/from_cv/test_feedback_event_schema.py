"""人裁事件规范（doc/formats/人裁事件规范.md）落到代码的几条：

- 「后到覆盖」一律按 `replay_key` = (ts, batch, seq)，不按批次名；
- `target.book/page/col/slot` 全空时构造事件就从 key 补（写入口统一；老数据 10-21 已迁）；
- `resolve` 能按 kind/unit 过滤（切线与定字 key 同形）；
- 控制台写入 `client_ts` 一律毫秒；
- `guji events lint` 的几类问题。
"""

from __future__ import annotations

import json

from open_guji_cv.feedback.events import Event, EventLog, EventTarget, make_event, replay_key
from guji_manager.feedback.routes import RouteTable
from open_guji_cv.gold.store import GoldStore
from guji_manager.gold.transfer import rebuild_verdicts


def _cut(batch, seq, ts, y):
    return make_event(batch, seq, "cutline",
                      EventTarget(step="row_segment", unit="boundary", key="vol02:5:8:14"),
                      {"y": y, "y_old": 100, "verdict": "moved"}, ts=ts)


def _confirm(batch, seq, ts, shape, key="vol02:5:8:14"):
    return make_event(batch, seq, "confirm", EventTarget(step="seed_admit", unit="cell", key=key),
                      {"v": "confirm", "shape": shape}, ts=ts)


def test_rebuild_verdicts_replays_in_time_order(tmp_path):
    """`gold rebuild` 与 human_chars 同口径：同一切线后写的赢，不管批次名。"""
    log = EventLog(tmp_path / "feedback")
    log.append([_cut("vol02-cutline", 1, "2026-09-06T00:00:00Z", 90)])
    log.append([_cut("H-cutfix", 1, "2026-10-01T00:00:00Z", 120)])
    store = GoldStore(tmp_path / "feedback" / "verdicts")
    rebuild_verdicts(log, store, table=RouteTable.load(None))
    got = {i.id: i.expected for i in store.list("char-segmentation/touching-cuts")}
    assert got["vol02:5:8:14"]["y"] == 120


def test_lint_reports_known_problems(tmp_path):
    from guji_manager.feedback.lint import lint
    ev = tmp_path / "events"
    ev.mkdir()

    def line(e: Event) -> str:
        return json.dumps(e.model_dump(mode="json"), ensure_ascii=False) + "\n"

    a = _cut("vol01-cutline-split_char", 1, "2026-09-08T05:09:09Z", 90)
    b = _cut("vol01-cutline-split_char", 1, "2026-09-08T05:01:50Z", 70)       # 同 id、内容不同、在别的文件
    bad_v = make_event("x", 1, "confirm", EventTarget(step="seed_admit", unit="cell", key="vol01:1:1:1"),
                       {"shape": "之"})
    sec = make_event("x", 2, "confirm", EventTarget(step="seed_admit", unit="cell", key="vol01:1:1:2"),
                     {"v": "confirm", "shape": "之", "client_ts": 1788741500.4})
    wrong_unit = make_event("x", 3, "cutline", EventTarget(step="row_segment", unit="cell", key="vol01:1:1:3"),
                            {"y": 1})
    (ev / "vol01-cutline-split_char.jsonl").write_text(line(a), encoding="utf-8")
    (ev / "vol01-cutline.jsonl").write_text(line(b), encoding="utf-8")
    mixed_pk = make_event("x", 4, "confirm", EventTarget(step="seed_admit", unit="cell", key="vol01:1:1:4", anchor={
        "product_key": {"step": "seed_admit", "key": "p0001", "fingerprint": "F", "row_segment": "abc"}}),
        {"v": "confirm", "shape": "之"})
    empty = json.loads(line(make_event("x", 5, "confirm", EventTarget(step="seed_admit", unit="cell", key="bxgb:1:1:5"),
                                       {"v": "confirm", "shape": "之"})))
    empty["target"].update(book=None, page=None, col=None, slot=None)
    odd_id = json.loads(line(make_event("x", 6, "band", EventTarget(step="column_warp", unit="column", key="bxgb:1:1"),
                                        {"band": "clean"})))
    odd_id["id"] = "evt_x-all_000006"
    (ev / "x.jsonl").write_text(line(bad_v) + line(sec) + line(wrong_unit) + line(mixed_pk)
                                + json.dumps(empty, ensure_ascii=False) + "\n"
                                + json.dumps(odd_id, ensure_ascii=False) + "\n" + "{坏行\n", encoding="utf-8")
    rep = lint(tmp_path)
    c = rep.counts
    assert c["E-dup-id"] == 1 and c["E-batch-file"] == 1
    assert c["E-payload-v"] == 1 and c["E-client-ts-sec"] == 1 and c["E-unit"] == 1
    assert c["E-product-key"] == 1 and c["E-key-empty"] == 1 and c["E-id-shape"] == 1
    assert c["E-parse"] == 1
    assert rep.n_errors == 9
    assert "E-dup-id" in rep.render()


