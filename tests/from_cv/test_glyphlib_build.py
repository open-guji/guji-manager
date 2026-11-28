# -*- coding: utf-8 -*-
"""共享刻例库（ops.glyphlib，共享方案 S5）：按门槛精选、刻例图逐字节照搬、id 加来源前缀、借进别的书记成借来的人裁。

自造字形库，不碰真书数据。
"""
from __future__ import annotations

import hashlib
import json
import random
import sqlite3

import cv2
import pytest

from open_guji_cv.clustering.synth import degrade, synthetic_glyph


def _png(seed: int) -> bytes:
    g = degrade(synthetic_glyph(random.Random(100 + seed)), random.Random(seed), wear=0.3)
    ok, buf = cv2.imencode(".png", 255 - (g * 255).astype("uint8"))
    assert ok
    return buf.tobytes()


def _confirm(key: str, shape: str, batch: str, seq: int) -> str:
    return json.dumps({"id": f"evt_{batch}_{seq}", "batch": batch, "seq": seq, "kind": "confirm",
                       "payload": {"v": "confirm", "shape": shape, "reading": shape},
                       "target": {"key": key, "unit": "cell"}}, ensure_ascii=False)


@pytest.fixture()
def src_ws(tmp_path, monkeypatch):
    """迁过的来源书：甲 4 例（确认 3/2/2/1 个批次）、乙 1 例（2 批，但体检标了异常）、丙 1 例（2 批，近似字）、丁 1 例非人裁。"""
    from open_guji_cv.clustering.glyph_db import GlyphDB, export_store
    from open_guji_cv.core.workspace import central_data_dir
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home"))
    for k in ("GUJI_WORKSPACE", "GUJI_GLYPH_DB", "GUJI_GLYPH_STORE"):
        monkeypatch.delenv(k, raising=False)
    ws = tmp_path / "src"
    ws.mkdir()
    (ws / "workspace.yaml").write_text("id: srcbook\n", encoding="utf-8")
    (ws / ".central.json").write_text('{"ws": "srcbook", "branch": "main"}', encoding="utf-8")
    data = central_data_dir("srcbook")
    db = GlyphDB(tmp_path / "seed.sqlite")
    cells = [("甲", "human", 1), ("甲", "human", 2), ("甲", "human", 3), ("甲", "human", 4),
             ("乙", "human", 5), ("丙", "human", 6), ("丁", "align", 7)]
    try:
        for ch, prov, i in cells:
            assert db.admit_instance(f"vol01:1:{i}:1", ch, _png(i), provenance=prov, edition_tag="srced",
                                     page="1", col=i, idx=1)
        db.conn.execute("INSERT INTO approx_labels (instance_id, label, created_at) VALUES (?,?,?)",
                        ("vol01:1:6:1", "丙", "t"))
        db.conn.commit()
        export_store(db, data / "output" / "glyph_store")
    finally:
        db.close()
    ev = data / "feedback" / "events"
    ev.mkdir(parents=True)
    lines = []
    for i, batches in ((1, ["a", "b", "c"]), (2, ["a", "b"]), (3, ["a", "d", "d"]), (4, ["a"]),
                       (5, ["a", "b"]), (6, ["a", "b"])):
        ch = cells[i - 1][0]
        lines += [_confirm(f"vol01:1:{i}:1", ch, b, n) for n, b in enumerate(batches)]
    lines.append(json.dumps({"id": "evt_audit_1", "batch": "audit", "seq": 1, "kind": "glyph_audit",
                             "payload": {"instance_id": "vol01:1:5:1", "v": "evict", "flags": []},
                             "target": {"key": "vol01:1:5:1"}}))
    (ev / "h.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ws, data


def test_select_applies_thresholds(src_ws):
    from guji_manager.ops.glyphlib import select
    _, data = src_ws
    picked, stats = select(data / "output/glyph_store", data / "feedback/events", min_batches=2, per_char=2)
    assert [(p["instance_id"], p["batches"]) for p in picked] == [("vol01:1:1:1", 3), ("vol01:1:2:1", 2)]
    assert stats["human"] == 6 and stats["audit_or_approx"] == 2 and stats["too_few_confirms"] == 1
    picked, _ = select(data / "output/glyph_store", data / "feedback/events", min_batches=1, per_char=3)
    assert [p["instance_id"] for p in picked] == ["vol01:1:1:1", "vol01:1:2:1", "vol01:1:3:1"]  # 同一批次重复只算一次


def test_build_copies_patches_and_borrows_as_borrowed_human(src_ws, tmp_path):
    from open_guji_cv.clustering.glyph_db import rebuild_from_store
    from open_guji_cv.core.workspace import central_data_dir
    from guji_manager.ops.glyphlib import build
    ws, data = src_ws
    res = build(ws, "glyphlib-tst-v1", min_batches=2, per_char=3, actor="t", note="试")
    assert res["edition"] == "glyphlib-tst" and res["instances"] == 3 and res["chars"] == 1
    lib = central_data_dir("glyphlib-tst-v1")
    store = lib / "output/glyph_store"
    src_png = {hashlib.sha256(p.read_bytes()).hexdigest() for p in (data / "output/glyph_store/patches").glob("*.png")}
    lib_png = {hashlib.sha256(p.read_bytes()).hexdigest() for p in (store / "patches").glob("*.png")}
    assert len(lib_png) == 3 and lib_png <= src_png                     # 图逐字节照搬，R2 不另存
    inst = [json.loads(x) for f in (store / "instances").glob("*.jsonl") for x in f.read_text("utf-8").splitlines()]
    assert sorted(r["instance_id"] for r in inst) == ["srcbook:vol01:1:1:1", "srcbook:vol01:1:2:1",
                                                      "srcbook:vol01:1:3:1"]
    assert {r["source_id"] for r in inst} == {"srcbook.vol01"}
    ev = [json.loads(x) for x in (lib / "feedback/promote.jsonl").read_text("utf-8").splitlines()]
    assert len(ev) == 3 and ev[0]["kind"] == "promote" and ev[0]["payload"]["from_ws"] == "srcbook"

    db = tmp_path / "borrower.sqlite"                                   # 别的书借它：记成借来的人裁，不当本书铁证
    # 借的书这里拿 srcbook 自己的库当本书：cv #2032 起缺省按本书前缀跳过自己的例，这里传空 self_ids 看借法本身
    rebuild_from_store(data / "output/glyph_store", db, extra_stores=[store], self_ids=())
    c = sqlite3.connect(db)
    try:
        st = dict(c.execute("SELECT label_status, COUNT(*) FROM instances WHERE instance_id LIKE 'srcbook:%' "
                            "GROUP BY 1").fetchall())
    finally:
        c.close()
    assert st == {"borrowed_human": 3}

    db2 = tmp_path / "self.sqlite"                                      # 缺省：本书（工作区名 srcbook）自己的例不再借进来
    rebuild_from_store(data / "output/glyph_store", db2, extra_stores=[store])
    c = sqlite3.connect(db2)
    try:
        assert c.execute("SELECT COUNT(*) FROM instances WHERE instance_id LIKE 'srcbook:%'").fetchone()[0] == 0
    finally:
        c.close()


def test_build_refuses_bad_name_and_empty_selection(src_ws):
    from guji_manager.ops.glyphlib import build
    ws, _ = src_ws
    with pytest.raises(SystemExit, match="glyphlib-"):
        build(ws, "qkp-v1")
    with pytest.raises(SystemExit, match="一张刻例都没选出"):
        build(ws, "glyphlib-tst-v1", min_batches=9)


def test_edition_of():
    from guji_manager.ops.glyphlib import edition_of
    assert edition_of("glyphlib-qkp-v1") == "glyphlib-qkp" and edition_of("glyphlib-qkp-v12") == "glyphlib-qkp"
    assert edition_of("glyphlib-odd") == "glyphlib-odd"


def _src2(tmp_path, ws_id: str, chars, *, auto=(), day="2026-11-20"):
    """第二本来源书：chars 是人裁（各 2 批确认），auto 是放行格回库例（证据带 backfill、verify）。"""
    from open_guji_cv.clustering.glyph_db import GlyphDB, export_store
    from open_guji_cv.core.workspace import central_data_dir
    ws = tmp_path / ws_id
    ws.mkdir()
    (ws / "workspace.yaml").write_text(f"id: {ws_id}\n", encoding="utf-8")
    (ws / ".central.json").write_text(json.dumps({"ws": ws_id, "branch": "main"}), encoding="utf-8")
    data = central_data_dir(ws_id)
    db = GlyphDB(tmp_path / f"{ws_id}.sqlite")
    db.conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('book_edition', ?)", (ws_id,))
    lines = []
    try:
        for i, ch in enumerate(chars, 1):     # 同 vol01:1:i:1 号：与第一本书撞号也不怕，库里带来源前缀
            assert db.admit_instance(f"vol01:1:{i}:1", ch, _png(50 + i), provenance="human", page="1", col=i, idx=1)
            lines += [_confirm(f"vol01:1:{i}:1", ch, b, n) for n, b in enumerate(["a", "b"])]
        for j, ch in enumerate(auto, 1):
            assert db.admit_instance(f"v2:01:2:{j}:1", ch, _png(80 + j), provenance="auto", page="2", col=j, idx=1,
                                     evidence={"backfill": True, "batch": "bf1", "verify": {"tpl_top1": ch}})
        db.conn.execute("UPDATE admissions SET admitted_at=?", (day,))
        db.conn.commit()
        export_store(db, data / "output" / "glyph_store")
    finally:
        db.close()
    ev = data / "feedback" / "events"
    ev.mkdir(parents=True)
    (ev / "h.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ws, data


class _FakeEmb:
    """不跑模型：auto 例核验看字是否在 ok 里；向量按实例号造，号相邻的算很像。"""
    def __init__(self, ok=None):
        self.ok = ok

    def verify(self, path, ch):
        return {"ok": self.ok is None or ch in self.ok, "tpl_top1": ch, "tpl_margin": 0.1}

    def emb(self, paths):
        import numpy as np
        out = []
        for p in paths:
            k = sum(map(ord, str(p))) % 7
            v = np.zeros(8, dtype=np.float32)
            v[k] = 1.0
            out.append(v)
        return out


def test_build_multi_source_auto_and_suspect(src_ws, tmp_path):
    from open_guji_cv.core.workspace import central_data_dir
    from guji_manager.ops.glyphlib import build
    ws1, _ = src_ws
    ws2, _ = _src2(tmp_path, "book2", ["甲", "戊"], auto=["戊", "己", "庚"], day="2026-11-26")
    res = build([ws1, ws2], "glyphlib-tst-v2", min_batches=2, per_char=3, with_auto=True,
                embedder=_FakeEmb(ok={"戊", "己"}), suspect={"book2": {"since": "2026-11-26"}})
    assert res["from"] == ["srcbook", "book2"]
    assert res["select"]["book2"]["auto"]["reverify_failed"] == 1         # 庚 字体核验不过
    assert res["picked_by_kind"] == {"human": 4, "auto": 2}              # 甲 3（书一占满）、戊 1 人裁；戊 己 回库
    assert res["select"]["book2"]["suspect"]["marked"] == 4 and res["suspect_in_lib"] == 3
    store = central_data_dir("glyphlib-tst-v2") / "output/glyph_store"
    inst = {json.loads(x)["instance_id"]: json.loads(x) for f in (store / "instances").glob("*.jsonl")
            for x in f.read_text("utf-8").splitlines()}
    assert "book2:v2:01:2:1:1" in inst and inst["book2:v2:01:2:1:1"]["label_status"] == "auto"   # 不冒充人裁
    assert "book2:vol01:1:1:1" not in inst                                # 甲 已由书一占满 3 张
    adm = {json.loads(x)["instance_id"]: json.loads(json.loads(x)["evidence"])
           for x in (store / "admissions.jsonl").read_text("utf-8").splitlines()}
    assert adm["book2:v2:01:2:2:1"]["suspect"].startswith("入库于") and adm["srcbook:vol01:1:1:1"].get("suspect") is None


def test_build_drop_suspect(src_ws, tmp_path):
    from guji_manager.ops.glyphlib import build
    ws1, _ = src_ws
    ws2, _ = _src2(tmp_path, "book3", ["戊"], auto=["己"], day="2026-11-26")
    res = build([ws1, ws2], "glyphlib-tst-v3", per_char=3, with_auto=True, embedder=_FakeEmb(),
                suspect={"book3": {"since": "2026-11-26"}}, drop_suspect=True)
    assert res["suspect_in_lib"] == 0 and res["picked_by_source"] == {"srcbook": 3}


def test_pick_per_char_diverse_drops_near_duplicates():
    import numpy as np
    from guji_manager.ops.glyphlib import pick_per_char
    vec = {"a": [1, 0], "b": [1, 0], "c": [0, 1]}
    xs = [{"char": "甲", "instance_id": k, "src_ws": "w", "batches": 2 if k != "c" else 0, "auto": k == "c"}
          for k in "abc"]
    emb_of = lambda ps: [np.asarray(vec[p["instance_id"]], dtype=np.float32) for p in ps]  # noqa: E731
    got, st = pick_per_char(xs, 3, emb_of=emb_of)
    assert [p["instance_id"] for p in got] == ["a", "c"] and st["dup"] == 1
    got, _ = pick_per_char(xs, 2)
    assert [p["instance_id"] for p in got] == ["a", "b"]


def test_build_source_without_source_row(src_ws, tmp_path):
    """借库书第一次回库后，本书真源的 sources.jsonl 可能是空的（同名来源 v2 是借来那本的）：照样装得进组库（汉书 11-28）。"""
    from open_guji_cv.core.workspace import central_data_dir
    from guji_manager.ops.glyphlib import build
    ws1, _ = src_ws
    ws2, data2 = _src2(tmp_path, "book4", [], auto=["戊", "己"])
    (data2 / "output/glyph_store/sources.jsonl").write_text("", encoding="utf-8")
    res = build([ws1, ws2], "glyphlib-tst-v4", per_char=3, with_auto=True, embedder=_FakeEmb())
    assert res["picked_by_source"] == {"srcbook": 3, "book4": 2}
    store = central_data_dir("glyphlib-tst-v4") / "output/glyph_store"
    assert len(list((store / "patches").glob("book4_*.png"))) == 2
