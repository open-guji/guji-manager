"""放行格回库的选格与配置（`ops/lib_backfill.py`）。取图、核验、入库要整套 cv 环境，不在这里测。"""
import collections
import sqlite3

import pytest

from guji_manager.ops import lib_backfill as LB


def _state(counts=None, in_lib=(), evicted=()):
    return {"counts": collections.Counter(counts or {}), "in_lib": set(in_lib), "evicted": set(evicted)}


def _cell(ch, channel="rare_ref", cov=0.9, admit=True):
    return {"admit": admit, "char": ch, "channel": channel, "evidence": {"cov": cov}}


def test_select_only_sparse_chars_from_witnessed_channels():
    cells = {
        "001:1:1:1": _cell("樹", cov=0.80),
        "001:2:1:1": _cell("樹", cov=0.95),
        "001:3:1:1": _cell("之"),                          # 库里已够 3 例
        "001:4:1:1": _cell("鄲", channel="match_ref"),      # 通道不在名单
        "001:5:1:1": _cell("蟲", admit=False),              # 没放行
        "001:6:1:1": _cell("⿰木寸"),                       # 不是单个汉字
        "001:7:1:1": _cell("瘞", channel="witness3"),
    }
    cand, stat = LB.select(cells, _state({"之": 3}), set())
    assert cand == {"樹": ["001:2:1:1", "001:1:1:1"], "瘞": ["001:7:1:1"]}   # 覆盖度高的在前
    assert stat["放行格"] == 6 and stat["不是单个汉字"] == 1


def test_select_skips_in_lib_human_and_evicted_cells():
    cells = {k: _cell("樹") for k in ("001:1:1:1", "001:2:1:1", "001:3:1:1", "001:4:1:1")}
    cand, stat = LB.select(cells, _state(in_lib={"v2:001:1:1:1"}, evicted={"v2:001:3:1:1"}), {"001:2:1:1"})
    assert cand == {"樹": ["001:4:1:1"]}
    assert (stat["已在库"], stat["已有人裁"], stat["曾撤过库"]) == (1, 1, 1)


def test_lib_state_counts_only_live_instances(tmp_path):
    """撤库不删 exemplars 的行：刻例数要连 instances 数，不然撤掉的字会被当成「已有例」而不补。"""
    p = tmp_path / "g.db"
    c = sqlite3.connect(p)
    c.executescript("""
        CREATE TABLE glyphs(glyph_id INTEGER PRIMARY KEY, char TEXT);
        CREATE TABLE instances(instance_id TEXT PRIMARY KEY);
        CREATE TABLE exemplars(glyph_id INTEGER, instance_id TEXT);
        CREATE TABLE admissions(instance_id TEXT);
        CREATE TABLE evictions(instance_id TEXT);
        INSERT INTO glyphs VALUES (1,'樹'),(2,'榭');
        INSERT INTO instances VALUES ('v2:a'),('v2:b');
        INSERT INTO admissions VALUES ('v2:a'),('v2:b');
        INSERT INTO exemplars VALUES (2,'v2:a'),(2,'v2:b'),(1,'v2:gone');
        INSERT INTO evictions VALUES ('v2:gone');
    """)
    c.commit()
    c.close()
    st = LB.lib_state(p)
    assert st["counts"] == {"榭": 2} and st["evicted"] == {"v2:gone"} and st["in_lib"] == {"v2:a", "v2:b"}


def test_lib_state_skips_borrowed(tmp_path):
    """借来的刻例不算本书已有例：借库的新书，本书没有的字要能补。"""
    p = tmp_path / "g.db"
    c = sqlite3.connect(p)
    c.executescript("""
        CREATE TABLE glyphs(glyph_id INTEGER PRIMARY KEY, char TEXT);
        CREATE TABLE instances(instance_id TEXT PRIMARY KEY);
        CREATE TABLE exemplars(glyph_id INTEGER, instance_id TEXT);
        CREATE TABLE admissions(instance_id TEXT);
        CREATE TABLE evictions(instance_id TEXT);
        CREATE TABLE borrowed(instance_id TEXT PRIMARY KEY, store TEXT);
        INSERT INTO glyphs VALUES (1,'樹'),(2,'榭');
        INSERT INTO instances VALUES ('v2:own'),('v2:b1'),('v2:b2'),('v2:b3');
        INSERT INTO admissions VALUES ('v2:own');
        INSERT INTO exemplars VALUES (2,'v2:own'),(1,'v2:b1'),(1,'v2:b2'),(1,'v2:b3');
        INSERT INTO borrowed VALUES ('v2:b1','x'),('v2:b2','x'),('v2:b3','x');
    """)
    c.commit()
    c.close()
    assert LB.lib_state(p)["counts"] == {"榭": 1}


def test_config(tmp_path):
    assert LB.config(tmp_path) == {"channels": LB.CHANNELS, "cap": LB.CAP}      # 缺省开
    y = tmp_path / "workspace.yaml"
    y.write_text("glyph_lib:\n  auto_backfill: false\n", encoding="utf-8")
    assert LB.config(tmp_path) is None
    y.write_text("glyph_lib:\n  auto_backfill: true\n", encoding="utf-8")
    assert LB.config(tmp_path) == {"channels": LB.CHANNELS, "cap": LB.CAP}
    y.write_text("glyph_lib:\n  auto_backfill: {cap: 5, channels: [rare_ref]}\n", encoding="utf-8")
    assert LB.config(tmp_path) == {"channels": ("rare_ref",), "cap": 5}
    y.write_text("glyph_lib:\n  auto_backfill: {caps: 5}\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        LB.config(tmp_path)


def test_apply_problem_guards(tmp_path, monkeypatch):
    """入库前核：部分副本、glyph.db 比账本旧都拒（2026-11-18）。不是中心库工作区的不查。"""
    import json
    from guji_manager.datastore import workcopy as W
    from guji_manager.ops import central_glyph as CG
    monkeypatch.delenv("GUJI_GLYPH_DB", raising=False)
    monkeypatch.setattr(CG, "_db_path", lambda ws: tmp_path / "glyph.db")
    ws = tmp_path / "ws"
    ws.mkdir()
    assert LB.apply_problem(ws) is None                               # 没有 .central.json
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home"))
    (ws / ".central.json").write_text(json.dumps({"ws": "t", "branch": "main"}), encoding="utf-8")
    data = W.data_dir(ws)
    data.mkdir(parents=True)
    W.write_state(data, ws="t", rev=1, base={})
    assert LB.apply_problem(ws) is None
    W.write_state(data, ws="t", rev=1, base={}, exclude=["feedback/lists/proofing/"])
    assert "部分副本" in LB.apply_problem(ws)
    W.write_state(data, ws="t", rev=1, base={}, **{W.GLYPH_DB_STALE: True})
    assert "比字形账本旧" in LB.apply_problem(ws)


# ---- 抢首位核验（cv #1679 BackfillProbe.steal_check，2026-11-18 史記 r80） ----

def test_steal_drop_only_harm_without_help():
    sim = {"harm": {"蒍": ["01:1:1:1", "01:2:1:1"], "揄": ["01:3:1:1"], "<爲>": ["01:4:1:1"], "庾": []},
           "help": {"揄": ["01:5:1:1"]}}
    # 揄 有害也有帮→留；<爲> 不是这批新字→不管；庾 没害→留
    assert LB.steal_drop(sim, {"蒍", "揄", "庾"}) == {"蒍": ["01:1:1:1", "01:2:1:1"]}
    assert LB.steal_drop({}, {"蒍"}) == {}


def test_config_steal_keys(tmp_path):
    y = tmp_path / "workspace.yaml"
    y.write_text("glyph_lib:\n  auto_backfill: {steal_check: false, steal_cells_max: 0}\n", encoding="utf-8")
    assert LB.config(tmp_path) == {"channels": LB.CHANNELS, "cap": LB.CAP, "steal_check": False, "steal_cells_max": 0}


class _Ctx:
    """假 RunContext：字块图一律给一张小黑块；kNN 参数取不到走缺省。"""
    def __init__(self, missing=()):
        self.missing = set(missing)

    def image(self, kind, key):
        import numpy as np
        if key in self.missing:
            return None
        a = np.full((40, 40), 255, np.uint8)
        a[10:30, 10:30] = 0
        return a


def _picks(*pairs):
    import cv2
    import numpy as np
    png = cv2.imencode(".png", np.zeros((40, 40), np.uint8))[1].tobytes()
    return [(ch, k, png, {"channel": "rare_ref"}, {"tpl_top1": ch}) for ch, k in pairs]


def test_steal_gate_samples_cells_and_skips_new(monkeypatch):
    pytest.importorskip("cv2")
    monkeypatch.setattr(LB, "_norm", lambda img: img)
    monkeypatch.setattr(LB, "_knn_params", lambda ctx: {"knn_k": 15, "per_char": 3, "per_char_top": 10})
    from guji_manager import _cv
    monkeypatch.setattr(_cv, "binarize_page", lambda img, edge_margin=0: img, raising=False)
    seen = {}

    class Probe:
        def __init__(self, db, **kw):
            seen["kw"] = kw

        def steal_check(self, new_items, cells):
            seen["new"] = [k for k, _c, _n in new_items]
            seen["cells"] = [k for k, _c, _n in cells]
            return {"harm": {"蒍": [cells[0][0]]}, "help": {}, "checked": len(cells), "cells": len(cells)}

    sa = {f"01:{i}:1:1": {"admit": True, "char": "為"} for i in range(10)}
    sa["01:99:1:1"] = {"admit": True, "char": "蒍"}          # 本批新例自己：不当回放格
    sa["01:98:1:1"] = {"admit": False, "char": "之"}         # 没放行
    cs = {k: {"patch_key": k} for k in sa}
    drop, info = LB.steal_gate("01", _picks(("蒍", "01:99:1:1")), sa, cs, _Ctx(), "g.db", cells_max=4, probe_cls=Probe)
    assert seen["new"] == ["01:99:1:1"] and len(seen["cells"]) == 4 and "01:99:1:1" not in seen["cells"]
    assert seen["kw"] == {"knn_k": 15, "per_char": 3, "per_char_top": 10}
    assert drop == {"蒍": [seen["cells"][0]]} and info["sampled"] and info["dropped"] == ["蒍"]
    assert "img_s" in info and "sim_s" in info


def test_steal_gate_old_cv_is_loud(monkeypatch):
    from guji_manager import _cv

    real = _cv.__getattr__

    def boom(name):
        if name == "BackfillProbe":
            raise ModuleNotFoundError("No module named 'open_guji_cv.clustering.backfill_probe'")
        if name == "binarize_page":
            return lambda img, edge_margin=0: img
        return real(name)
    monkeypatch.setattr(_cv, "__getattr__", boom)
    said = []
    drop, info = LB.steal_gate("01", _picks(("蒍", "01:9:1:1")), {}, {}, _Ctx(), "g.db", say=said.append)
    assert drop == {} and "没做抢首位核验" in info["skipped"] and said
    rep = {"stat": {}, "picks": 1, "chars": 1, "steal_check": [info]}
    assert "⚠ 01 没做抢首位核验" in LB.summary(rep)
    assert "抢首位核验已关" in LB.summary({"stat": {}, "picks": 1, "chars": 1, "steal_check": None})


def test_backfill_probe_registered():
    """闸靠 `from .._cv import BackfillProbe`：没登记会永远走「cv 太旧」那条路、闸从不生效（OCR WIP 里漏了）。"""
    from guji_manager import _cv
    assert _cv._FALLBACK["BackfillProbe"] == ("clustering.backfill_probe", "BackfillProbe")
