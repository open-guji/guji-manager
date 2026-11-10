"""换包落 book-text（格号变动按格级对照表）：对照表、逐块图判字、专名两端对上的伸长、守卫。"""
from guji_manager.swap import booktext as bt


def _char(cols):
    """cols: {列号: "字串"}，都在第 1 页；□ 照写。"""
    return {"pages": [{"page": 1, "columns": [
        {"col": k, "cells": [{"a": f"1:{k}:{i + 1}", "c": ch} for i, ch in enumerate(s)]} for k, s in cols.items()]}]}


def _cord(cols, shift=None):
    """每格 10×10 竖排；shift={列: 从第几格（1 起）起往下挪一格}，模拟中间插进一格。"""
    cells = []
    for k, s in cols.items():
        for i, _ in enumerate(s):
            cells.append({"a": f"1:{k}:{i + 1}", "box": [100 - 10 * k, 10 * i, 10, 10]})
    return {"pages": [{"page": 1, "cells": cells}]}


def test_cell_table_insert_shifts_numbers():
    old_c, new_c = _char({1: "論語子集"}), _char({1: "論語孟子集"})
    old_d = {"pages": [{"page": 1, "cells": [{"a": f"1:1:{i + 1}", "box": [90, y, 10, 10]} for i, y in enumerate((0, 10, 30, 40))]}]}
    new_d = _cord({1: "論語孟子集"})
    rows = bt.cell_table(old_c, old_d, new_c, new_d)
    kinds = {(r["old"], r["new"]): r["kind"] for r in rows}
    assert kinds[("1:1:3", "1:1:4")] == "改号"           # 子：格号挪了，块图同一块
    assert kinds[("", "1:1:3")] == "新增"                # 孟：新增格
    assert bt.table_counts(rows)["对上但改字"] == 0


def test_merge_keeps_current_when_new_blank_or_pending_and_reverts_dup():
    old_c = _char({1: "行苞在康煕中"})
    new_c = _char({1: "□苞在康康中"})
    rows = bt.cell_table(old_c, _cord({1: "行苞在康煕中"}), new_c, _cord({1: "□苞在康康中"}))
    rep = bt.merge_chars(old_c, new_c, rows, pending={"1:1:2"})
    got = "".join(x["c"] for x in new_c["pages"][0]["columns"][0]["cells"])
    assert got == "行苞在康煕中"                          # □ 不覆盖现字；改出相邻重复字回退
    assert rep["return_to_blank"] and rep["machine_flaw"]


def test_merge_adopts_machine_change_and_new_admit():
    old_c, new_c = _char({1: "□東巡"}), _char({1: "山東撫"})
    rows = bt.cell_table(old_c, _cord({1: "□東巡"}), new_c, _cord({1: "山東撫"}))
    rep = bt.merge_chars(old_c, new_c, rows)
    assert "".join(x["c"] for x in new_c["pages"][0]["columns"][0]["cells"]) == "山東撫"
    assert rep["new_admit"] and rep["machine_change"]


def test_grow_span_when_cell_inserted_inside_entity():
    new_c = _char({1: "論語孟子集"})
    rows = [dict(old="1:1:1", new="1:1:1", kind="同格"), dict(old="1:1:2", new="1:1:2", kind="同格"),
            dict(old="1:1:3", new="1:1:4", kind="改号"), dict(old="", new="1:1:3", kind="新增")]
    ent = {"entities": [{"id": "e1", "type": "work", "text": "語子", "anchor": {"start": "1:1:2", "end": "1:1:3"},
                         "span": {"start_offset": 1, "end_offset": 3}, "target": {"status": "new_candidate"}}]}
    rep = [("entity", "e1", "1:1:2～1:1:3", "1:1:2～1:1:4", "語子", "ANCHOR_MISS｜新格不连续或长度变了（語孟子）")]
    out = bt._grow_spans(ent, new_c, rows, rep)
    e = ent["entities"][0]
    assert out and e["text"] == "語孟子" and e["anchor"] == {"start": "1:1:2", "end": "1:1:4"}
    assert e["span"] == {"start_offset": 1, "end_offset": 4}


def test_guard_flags_lost_link_and_punct_change():
    e0 = {"entities": [{"id": "e1", "type": "people", "text": "方苞", "target": {"entity_id": "x", "status": "matched"}}]}
    e1 = {"entities": [{"id": "e1", "type": "people", "text": "方苞", "target": {"status": "new_candidate"}}]}
    p0 = {"punctuations": [{"mark": "，", "kind": "point", "source": "claude:A33", "pos": "after"}]}
    p1 = {"punctuations": []}
    assert bt.guard(p0, p0, e0, e0) == []
    probs = bt.guard(p0, p1, e0, e1)
    assert any("挂法" in x for x in probs) and any("标点" in x for x in probs)


def test_structure_changed():
    assert bt.structure_changed(_char({1: "ab"}), _char({1: "abc"}))
    assert not bt.structure_changed(_char({1: "ab"}), _char({1: "xy"}))


def test_break_follows_heading_over_added_cells():
    new_c = _char({1: "甲乙丙丁戊"})
    rows = [dict(old="1:1:1", new="1:1:1", kind="同格"), dict(old="", new="1:1:2", kind="新增"),
            dict(old="", new="1:1:3", kind="新增"), dict(old="1:1:2", new="1:1:4", kind="改号"),
            dict(old="1:1:3", new="1:1:5", kind="改号")]
    p = {"punctuations": [{"anchor": "1:1:1", "kind": "break", "pos": "after", "pre_char": "甲", "char_offset": 0},
                          {"anchor": "1:1:4", "kind": "heading", "pos": "before", "char_offset": 3}]}
    out = bt._breaks_follow_headings(p, new_c, rows)
    b = p["punctuations"][0]
    assert out == [("1:1:1", "1:1:3")] and b["anchor"] == "1:1:3" and b["pre_char"] == "丙" and b["char_offset"] == 2


def test_protected_cells_and_ledger():
    old_c = _char({1: "刪行苞"})
    human = {"1:1:1": "删", "1:1:2": "行"}            # 1:1:1 原先就不同（异体），1:1:2 有效
    edits = [{"anchor": "1:1:3", "old": "芭", "new": "苞"}]
    prot, pre = bt.protected_cells(old_c, human, edits)
    assert prot == {"1:1:2": "行", "1:1:3": "苞"} and pre == [("1:1:1", "人裁", "删", "刪")]
    rows = [dict(old="1:1:1", new="1:1:1", kind="同格"), dict(old="1:1:2", new="", kind="删"),
            dict(old="1:1:3", new="1:1:2", kind="改号")]
    new_c = _char({1: "刪苞"})
    pn, probs = bt.human_ledger(rows, prot, new_c)
    assert pn == {"1:1:2": "苞"} and len(probs) == 1 and "1:1:2" in probs[0]   # 有人裁的格被删：报


def test_merge_keeps_human_and_flags_conflict():
    old_c, new_c = _char({1: "方苞在"}), _char({1: "方芭在"})
    rows = bt.cell_table(old_c, _cord({1: "方苞在"}), new_c, _cord({1: "方芭在"}))
    rep = bt.merge_chars(old_c, new_c, rows, protected={"1:1:2": "苞"})
    assert "".join(x["c"] for x in new_c["pages"][0]["columns"][0]["cells"]) == "方苞在"
    assert rep["protected_conflict"] == [("1:1:2", "苞", "芭", "苞")]
    assert bt.ledger_check(new_c, {"1:1:2": "苞"}) == []


def test_require_human_stops_1x_when_events_missing(tmp_path, monkeypatch):
    import json
    import subprocess
    repo = tmp_path / "bt"
    vdir = repo / "Book" / "default"
    vdir.mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "scripts" / "original_version.py").write_text(
        "import json\ndef dump_json(p, d):\n    open(p, 'w', encoding='utf-8').write(json.dumps(d, ensure_ascii=False))\n",
        encoding="utf-8")
    c = _char({1: "方苞"})
    d = _cord({1: "方苞"})
    for t, x in (("char", c), ("cord", d), ("punct", {"punctuations": []}), ("entity", {"entities": []})):
        (vdir / f"001.{t}.json").write_text(json.dumps(x, ensure_ascii=False), encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=t", "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "x"], check=True)
    monkeypatch.setattr(bt, "load_human", lambda book: None)
    calls = {}

    class _RA:
        def load_cells(self, p):
            return p

    def _run(ra, ch, nc, p, e, cells):
        calls["n"] = calls.get("n", 0) + 1
        return {"punct": p, "entity": e, "report": [], "moved": 0, "left": 0}
    from guji_manager.closeout import remap_lib
    monkeypatch.setattr(remap_lib, "load_ra", lambda repo: _RA())
    monkeypatch.setattr(remap_lib, "run", _run)
    r0 = bt.remap_in_repo(repo, vdir, "001", out_dir=tmp_path / "o")
    assert r0["ok"] and r0["notes"]
    r1 = bt.remap_in_repo(repo, vdir, "001", out_dir=tmp_path / "o", require_human=True)
    assert not r1["ok"] and any("1.x" in x for x in r1["problems"])


def test_guard_other_fields_count_and_shortened():
    old_c = _char({1: "梁國治在"})
    e0 = {"entities": [{"id": "e1", "type": "people", "text": "梁國治", "anchor": {"start": "1:1:1", "end": "1:1:3"},
                        "group": "g1", "decomposition": [{"text": "梁"}], "target": {"entity_id": "x", "status": "matched"}}]}
    short = {"entities": [{**e0["entities"][0], "text": "國治"}]}
    assert any("切短" in p for p in bt.guard(None, None, e0, short, old_c, []))
    rows = [dict(old="1:1:1", new="", kind="删")]
    assert bt.guard(None, None, e0, short, old_c, rows) == []          # 少的那格是被删的：放行
    nodec = {"entities": [{k: v for k, v in e0["entities"][0].items() if k != "decomposition"}]}
    assert any("字段" in p for p in bt.guard(None, None, e0, nodec))
    dup = {"entities": e0["entities"] * 2}
    assert any("条数" in p for p in bt.guard(None, None, e0, dup))

def test_rekey_gate_orphan_and_ok(tmp_path):
    import sqlite3
    from guji_manager.swap.booktext import rekey_gate
    db = tmp_path / "g.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE instances(instance_id TEXT, source_id TEXT, label TEXT)")
    c.executemany("INSERT INTO instances VALUES(?,?,?)", [("v2:vol04:1:1:1", "s", "甲"), ("v2:vol04:1:1:2", "s", "乙"), ("v2:vol05:1:1:1", "s", "丙")])
    c.commit(); c.close()
    rows = [dict(old="1:1:1", new="1:1:1", kind="同格", oc="", nc="", iou=1, note=""),
            dict(old="1:1:2", new="", kind="删", oc="", nc="", iou=0, note="")]
    g = rekey_gate(db, rows, 4)
    assert not g["ok"] and g["orphan"] == ["v2:vol04:1:1:2"] and g["n_inst"] == 2
    rows[1] = dict(old="1:1:2", new="1:1:2", kind="同格", oc="", nc="", iou=1, note="")
    assert rekey_gate(db, rows, 4)["ok"]


def test_finish_redirect_and_unanchored(tmp_path):
    from guji_manager.swap import finish as F
    t1 = [{"旧格": "vol01:1:1:1", "新格": "vol01:1:1:2", "类别": "改号"}, {"旧格": "vol01:1:1:2", "新格": "", "类别": "删"},
          {"旧格": "vol01:1:1:3", "新格": "vol01:1:1:3", "类别": "同格"}]
    t2 = [{"旧格": "vol01:1:1:2", "新格": "vol01:1:1:5", "类别": "改号"}]
    red = F.redirect_map([t1, t2])
    assert red["vol01:1:1:1"] == "vol01:1:1:5" and red["vol01:1:1:2"] == "vol01:1:1:5" and "vol01:1:1:3" not in red
    rows = [dict(old="1:1:1", new="1:1:2", kind="改号"), dict(old="1:1:2", new="", kind="删"), dict(old="1:1:3", new="1:1:3", kind="同格")]
    lines, gone = F.unanchored_human(rows, {"1:1:1": "甲", "1:1:2": "乙", "1:1:3": "丙", "9:9:9": "丁"}, 1)
    assert len(lines) == 1 and lines[0].startswith("vol01:1:1:2\t") and lines[0].endswith("\t甲")
    assert gone == [("1:1:2", "乙"), ("9:9:9", "丁")]
    rep = F.finish(tmp_path, "vol01", rows, {"1:1:1": "甲"}, run="abc")
    assert rep["recheck"]["n"] == 1 and (tmp_path / "reports/_swap/metrics.jsonl").exists()

def test_copy_cord_plain_and_via_cv(tmp_path):
    src = tmp_path / "001.cord.json"
    src.write_text('{"pages": []}', encoding="utf-8")
    assert bt._copy_cord(src, tmp_path / "a.json", None) is None and (tmp_path / "a.json").read_text(encoding="utf-8") == '{"pages": []}'
    cv = tmp_path / "cv"
    (cv / "scripts" / "zhengli").mkdir(parents=True)
    (cv / "scripts" / "zhengli" / "republish.py").write_text(
        "import sys\ndef copy_cord_for_site(s, d):\n    sys.exit('页表对不上')\n", encoding="utf-8")
    why = bt._copy_cord(src, tmp_path / "b.json", cv)
    assert why and "页表对不上" in why and not (tmp_path / "b.json").exists()


def test_drop_stored_table_keeps_earlier_tables(tmp_path):
    rev = tmp_path / "lineage" / "revisions"
    rev.mkdir(parents=True)
    old, new = rev / "vol01-aaa.tsv", rev / "vol01-bbb.tsv"
    old.write_text("x"), new.write_text("y")
    bt.drop_stored_table(new)
    assert old.exists() and not new.exists()
    bt.drop_stored_table(old)                 # 最后一张删完：空目录一并收掉
    assert not (tmp_path / "lineage").exists()
