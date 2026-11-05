"""局部改号表（A22 `格号旧到新.tsv`：只列动了的格）改键：表里没列的格不动，`?` 挤出的停放，改号互相交错不撞主键。"""
import sqlite3

import pytest

from guji_manager.ops import cell_rekey as ck

TSV = ("册\t页\t列\t旧格\tsub\t新格\n"
       "vol01\t3\t4\t1\t\t-1\n"
       "vol01\t3\t4\t2\t\t1\n"
       "vol01\t3\t4\t3\t\t2\n"
       "vol01\t3\t4\t21\t\t删\n"
       "vol01\t3\t5\t8\ta\t7\n"
       "vol01\t3\t5\t8\tb\t7\n"
       "vol02\t9\t1\t1\t\t-1\n")


def _db(path):
    c = sqlite3.connect(path)
    c.executescript("""
    CREATE TABLE sources(source_id TEXT, pipeline_version TEXT);
    CREATE TABLE instances(instance_id TEXT PRIMARY KEY, source_id TEXT, label TEXT, page TEXT, col INT, idx INT,
                           bbox TEXT, updated_at TEXT);
    CREATE TABLE derived(instance_id TEXT);
    CREATE TABLE exemplars(instance_id TEXT, added_at TEXT);
    CREATE TABLE admissions(instance_id TEXT, provenance TEXT, evidence TEXT);
    CREATE TABLE cluster_members(instance_id TEXT);
    CREATE TABLE approx_labels(instance_id TEXT);
    CREATE TABLE pairs(inst_a TEXT, inst_b TEXT);
    CREATE TABLE evictions(instance_id TEXT, char TEXT, reason TEXT, at TEXT);
    """)
    rows = [("vol01:3:4:1", "甲"), ("v2:vol01:3:4:2", "乙"), ("vol01:3:4:3", "丙"), ("vol01:3:4:4", "丁"),  # 4 没列：不动
            ("vol01:3:4:21", "戊"), ("vol01:3:5:8a", "己"), ("vol01:3:5:8b", "庚"), ("vol03:3:4:1", "辛")]
    for iid, ch in rows:
        c.execute("INSERT INTO instances VALUES (?,?,?,?,?,?,?,?)", (iid, "s", ch, "3", 4, 1, "[1,2]", "t0"))
        c.execute("INSERT INTO admissions VALUES (?,?,?)", (iid, "human" if ch == "甲" else "align", None))
        c.execute("INSERT INTO exemplars VALUES (?,?)", (iid, "t0"))
    c.commit()
    c.close()


@pytest.fixture()
def table(tmp_path):
    p = tmp_path / "shift.tsv"
    p.write_text(TSV, encoding="utf-8")
    return p


def test_load_shift_table(table):
    assert ck.is_shift_table(table)
    cm = ck.load_shift_table(table, "vol01")
    assert cm.partial and cm.move["vol01:3:4:2"] == "vol01:3:4:1"
    assert cm.move["vol01:3:5:8a"] == "vol01:3:5:7a" and cm.move["vol01:3:5:8b"] == "vol01:3:5:7b"
    assert "vol01:3:4:21" in cm.deleted
    assert cm.lookup("vol01:3:4:4") == ("keep", None)
    with pytest.raises(ValueError):
        ck.load_shift_table(table, "vol99")


def test_dry_run_leaves_unlisted(table, tmp_path):
    db = tmp_path / "g.db"
    _db(db)
    cm = ck.load_shift_table(table, "vol01")
    res = ck.rekey_glyph_db(db, cm, "r1", dry_run=True, note="raise-box-1076")
    acts = {r["old"]: (r["action"], r["new"]) for r in res["rows"]}
    assert "vol01:3:4:4" not in acts and "vol03:3:4:1" not in acts       # 没列的、别册的不碰
    assert acts["vol01:3:4:1"] == ("rekey", "vol01:3:4:-1")
    assert acts["v2:vol01:3:4:2"] == ("rekey", "v2:vol01:3:4:1")          # v2 前缀保留
    assert acts["vol01:3:4:21"][0] == "park" and ":" not in acts["vol01:3:4:21"][1].split("~", 1)[0][2:]
    assert res["summary"]["human"] == 1


def test_apply_interleaved_and_verify(table, tmp_path):
    db = tmp_path / "g.db"
    _db(db)
    cm = ck.load_shift_table(table, "vol01")
    ck.rekey_glyph_db(db, cm, "r1", note="raise-box-1076")
    c = sqlite3.connect(db)
    ids = {r[0]: r[1] for r in c.execute("SELECT instance_id,label FROM instances")}
    assert ids["vol01:3:4:-1"] == "甲" and ids["v2:vol01:3:4:1"] == "乙" and ids["vol01:3:4:2"] == "丙"
    assert ids["vol01:3:4:4"] == "丁" and ids["vol03:3:4:1"] == "辛"
    assert ids["vol01:3:5:7a"] == "己" and ids["vol01:3:5:7b"] == "庚"
    assert c.execute("SELECT idx FROM instances WHERE instance_id='vol01:3:4:-1'").fetchone()[0] == -1
    # 没动的实例：exemplars.added_at 不被碰（否则库指纹全变）
    assert c.execute("SELECT added_at FROM exemplars WHERE instance_id='vol01:3:4:4'").fetchone()[0] == "t0"
    assert c.execute("SELECT count(*) FROM evictions WHERE reason LIKE 'rekey:raise-box-1076:%'").fetchone()[0] == 6
    c.close()
    with pytest.raises(SystemExit):           # 同一册同一批次不能改两遍
        ck.rekey_glyph_db(db, cm, "r1", note="raise-box-1076")


def test_collision_with_unmoved_instance_refused(tmp_path):
    p = tmp_path / "t.tsv"
    p.write_text("册\t页\t列\t旧格\tsub\t新格\nvol01\t3\t4\t5\t\t4\n", encoding="utf-8")
    db = tmp_path / "g.db"
    _db(db)                                   # 库里已有没动的 vol01:3:4:4
    c = sqlite3.connect(db)
    c.execute("INSERT INTO instances VALUES ('vol01:3:4:5','s','壬','3',4,5,NULL,'t0')")
    c.commit()
    with pytest.raises(SystemExit):
        ck.plan_glyph_db(c, ck.load_shift_table(p, "vol01"), "r1")
