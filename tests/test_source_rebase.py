# -*- coding: utf-8 -*-
"""`feedback/source_rebase.py`：页号格号不变的换图源后，人裁事件的锚按页表 from_rev.H 换算。事件与页表全在测试里造。"""
from __future__ import annotations

import json

import pytest

from guji_manager.feedback import source_rebase as R

H = [[2, 0, 10], [0, 2, 20], [0, 0, 1]]          # 旧页 200×300 → 新页 500×700：×2 加平移


def table(rev, pages, from_rev=None):
    rows = []
    for page, sha in pages.items():
        row = {"seq": f"{page:04d}", "page": page, "w": 500, "h": 700, "sha256": sha}
        if from_rev:
            row["from_rev"] = {"rev": from_rev[0], "sha256": from_rev[1][page], "w": 200, "h": 300, "H": H}
        rows.append(row)
    return {"rev": rev, "pages": rows}


OLD2 = table(2, {1: "a1", 2: "a2"})
OLD3 = table(3, {1: "a1", 2: "a2"})                           # 页图 sha 和 r002 逐页相同（殿本 vol51 等 13 册）
NEW4 = table(4, {1: "n1", 2: "n2"}, from_rev=(3, {1: "a1", 2: "a2"}))
TABLES = {2: OLD2, 3: OLD3, 4: NEW4}


def get_table(rev):
    return TABLES.get(rev)


def ev(i, key="vol05:1:2:3", kind="confirm", rev=3, anchor=True, page=1, seq=1, **extra):
    a = None
    if anchor:
        a = {"v": 1, "space": "raw_page_px@top-right", "bbox": [20, 10, 60, 50],
             "quad": [[20, 10], [60, 10], [60, 50], [20, 50]], "content_sha": "abc", "source_rev": rev, **extra.pop("anchor_extra", {})}
    return {"id": i, "ts": f"2026-11-0{seq}T00:00:00Z", "batch": "H-t", "seq": seq, "actor": "user", "kind": kind,
            "target": {"step": "seed_admit", "unit": "cell", "key": key, "book": "vol05", "page": page, "anchor": a},
            "payload": {"v": "confirm", **extra}}


def test_rebase_converts_box_quad_and_rev():
    res = R.rebase_events([ev("e1")], "vol05", 4, get_table)
    assert len(res.events) == 1 and not res.pending
    d = res.events[0]
    assert d["id"] == "e1~r" and d["batch"] == "H-t~r" and d["ts"] == "2026-11-01T00:00:00Z" and d["seq"] == 1
    a = d["target"]["anchor"]
    # 右上原点：x_tl = 200−x_tr，新 x_tl = 2·x_tl+10，新 x_tr = 500−新 x_tl；y 直接 2y+20
    assert a["bbox"] == [130.0, 40.0, 210.0, 120.0]
    assert a["quad"] == [[130.0, 40.0], [210.0, 40.0], [210.0, 120.0], [130.0, 120.0]]
    assert a["source_rev"] == 4 and a["migrated_from"] == {"id": "e1", "source_rev": 3}
    assert a["content_sha"] == "abc" and a["space"] == "raw_page_px@top-right"   # 其余键原样
    assert d["target"]["key"] == "vol05:1:2:3" and d["target"]["page"] == 1      # 格号页号不变
    assert res.id_map == {"e1": "e1~r"} and res.n_with_evidence == 1


def test_source_rev_type_is_kept():
    res = R.rebase_events([ev("e1", rev="3")], "vol05", 4, get_table)
    assert res.events[0]["target"]["anchor"]["source_rev"] == "4"


def test_pinned_rev2_with_same_page_images_passes():
    res = R.rebase_events([ev("e1", rev=2)], "vol05", 4, get_table)
    assert len(res.events) == 1 and res.events[0]["target"]["anchor"]["migrated_from"]["source_rev"] == 2


def test_skips_and_counts():
    evs = [ev("a", kind="ctx_ruling"), ev("b", anchor=False), ev("c", rev=4),
           {**ev("d"), "target": {**ev("d")["target"], "anchor": {"bbox": [1, 2, 3, 4]}}}, ev("ok")]
    res = R.rebase_events(evs, "vol05", 4, get_table)
    assert [d["id"] for d in res.events] == ["ok~r"]
    assert sum(res.skipped.values()) == 4 and not res.pending
    assert res.n_in == 5


def test_other_book_events_are_ignored():
    other = ev("x", key="vol06:1:1:1")
    other["target"]["book"] = "vol06"
    res = R.rebase_events([other, ev("e1")], "vol05", 4, get_table)
    assert res.n_in == 1 and len(res.events) == 1


def test_pending_reasons():
    tables = {**TABLES, 3: table(3, {1: "zzz", 2: "a2"})}                       # r003 第 1 页的图和 from_rev 对不上
    evs = [ev("p1", rev=3), ev("p2", page=9), ev("p3", rev=1), ev("p4", page=2, anchor_extra={"space": "raw_page_px@top-left"}),
           ev("p5", rev="x"), ev("ok", page=2)]
    res = R.rebase_events(evs, "vol05", 4, tables.get)
    assert [d["id"] for d in res.events] == ["ok~r"]
    got = {p.reason for p in res.pending}
    assert got == {"旧页图和新页表 from_rev 对不上", "新页表没有这一页的换算", "取不到旧页表这一页",
                   "锚的坐标系不是右上原点", "source_rev 不是整数"}
    res.check()


def test_no_box_anchor_counts_and_overrides_are_remapped():
    plain = ev("w1", seq=1)
    plain["target"]["anchor"] = {"source_rev": 3}
    second = ev("w2", seq=2, overrides="w1")
    third = ev("w3", seq=3, overrides="gone")
    res = R.rebase_events([plain, second, third], "vol05", 4, get_table)
    byid = {d["id"]: d for d in res.events}
    assert res.n_no_box == 1 and byid["w1~r"]["target"]["anchor"]["source_rev"] == 4
    assert byid["w2~r"]["payload"]["overrides"] == "w1~r"
    assert "overrides" not in byid["w3~r"]["payload"]


def test_missing_new_table_raises():
    with pytest.raises(ValueError):
        R.rebase_events([ev("e1")], "vol05", 7, get_table)


def test_write_report(tmp_path):
    res = R.rebase_events([ev("e1"), ev("e2", page=9)], "vol05", 4, get_table)
    R.write_report(res, tmp_path / "out", extra={"事件来源": "测试"})
    out = tmp_path / "out"
    lines = (out / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["id"] == "e1~r"
    assert "e1\te1~r" in (out / "id_map.tsv").read_text(encoding="utf-8")
    assert "新页表没有这一页的换算" in (out / "pending.tsv").read_text(encoding="utf-8")
    rep = (out / "report.md").read_text(encoding="utf-8")
    assert "输入 2 = 迁出 1 + 不迁 0 + 待办 1（核对通过）" in rep and "事件来源：测试" in rep
