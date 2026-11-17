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


def test_config(tmp_path):
    assert LB.config(tmp_path) is None
    y = tmp_path / "workspace.yaml"
    y.write_text("glyph_lib:\n  auto_backfill: true\n", encoding="utf-8")
    assert LB.config(tmp_path) == {"channels": LB.CHANNELS, "cap": LB.CAP}
    y.write_text("glyph_lib:\n  auto_backfill: {cap: 5, channels: [rare_ref]}\n", encoding="utf-8")
    assert LB.config(tmp_path) == {"channels": ("rare_ref",), "cap": 5}
    y.write_text("glyph_lib:\n  auto_backfill: {caps: 5}\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        LB.config(tmp_path)
