"""字格永久编号 u 第二批（T2）：用真的字格身份账（T1 `uid.ledger`）核导出、裁定核对、票、格级表。"""
import pytest

from guji_manager import cell_ref as CR
from guji_manager import u_stamp as U
from guji_manager import u_table as T
from guji_manager.feedback import web_votes as W
from guji_manager.uid.ledger import Ledger, make_line

B = "vol31"


@pytest.fixture
def led(tmp_path, monkeypatch):
    root = tmp_path / "feedback" / "uid"
    monkeypatch.setenv("GUJI_FEEDBACK_DIR", str(tmp_path / "feedback"))
    monkeypatch.setattr("guji_manager.uid.ledger.default_root", lambda: root)
    CR.clear_cache()
    lg = Ledger.load(B)
    # 第 5 页切过两次：第二次在列首补了一格（u4 新），原 5:2:1..3 依次挪到 5:2:2..4；u3 被并进 u2，u9 删掉
    lg.append([
        make_line(B, 5, "s1", {f"{B}:5:2:1": 1, f"{B}:5:2:2": 2, f"{B}:5:2:3": 3, f"{B}:5:2:4": 9},
                  chars={f"{B}:5:2:1": "欽", f"{B}:5:2:2": "定", f"{B}:5:2:3": "四", f"{B}:5:2:4": "庫"},
                  boxes={f"{B}:5:2:1": [0, 0, 10, 10]}),
        make_line(B, 5, "s2", {f"{B}:5:2:1": 10, f"{B}:5:2:2": 1, f"{B}:5:2:3": 2},
                  chars={f"{B}:5:2:1": "傳", f"{B}:5:2:2": "欽", f"{B}:5:2:3": "定"},
                  boxes={f"{B}:5:2:2": [0, 0, 10, 10]},
                  lineage=[{"u": 10, "new": True}, {"u": 3, "into": 2}, {"u": 9, "gone": True}]),
        make_line(B, 6, "t1", {f"{B}:6:1:1": 20}),
    ])
    yield lg
    CR.clear_cache()


def test_batch_ref_and_u_map(led):
    ref = U._cell_ref()
    assert ref(f"{B}:5:2:2") == 1 and ref("vol02:1:1:1") == "vol02:1:1:1"
    with pytest.raises(KeyError):
        ref(f"{B}:5:2:9")
    assert U.u_map(B, ["5:2:1", "6:1:1"]) == {"5:2:1": 10, "6:1:1": 20}


def test_export_uids(led):
    x = U.export_uids(B)
    assert x["u_max"] == 20 and x["map"]["5:2:2"] == 1
    assert x["u_retired"] == [{"u": 3, "into": 2}, {"u": 9, "gone": True}]
    assert U.export_uids("vol02") is None


def test_current_cell_follows_u(led):
    assert U.current_cell({"cell": f"{B}:5:2:1", "u": 1}) == f"{B}:5:2:2"      # 写时在 5:2:1，现在挪到 5:2:2
    assert U.current_cell({"cell": f"{B}:5:2:3", "u": 3}) is None              # 并掉了
    assert U.current_cell({"cell": f"{B}:5:2:1"}) == f"{B}:5:2:1"              # 没 u 照旧
    assert U.current_cell({"cell": "vol02:1:1:1", "u": 5}) == "vol02:1:1:1"    # 没账照旧


def test_rulings_follow_u(led):
    from guji_manager.ruling_hits import _follow_u
    p = {"cell": f"{B}:5:2:1", "u": 1, "char": "欽"}
    assert _follow_u(p) == {**p, "cell": f"{B}:5:2:2", "cell_at_write": f"{B}:5:2:1"}
    assert _follow_u({"cell": f"{B}:5:2:4", "u": 9}) == {}
    q = {"cell": f"{B}:6:1:1", "u": 20}
    assert _follow_u(q) is q


def test_votes_by_u(led):
    votes = [{"book": "s", "rev": "r1", "a": "5:2:1", "u": 1, "voter": "x", "choice": "char", "char": "欽", "ts": 1},
             {"book": "s", "rev": "r0", "a": "5:2:3", "u": "1", "voter": "y", "choice": "char", "char": "欽", "ts": 2},
             {"book": "s", "rev": "r1", "a": "5:2:3", "u": 3, "voter": "z", "choice": "char", "char": "四", "ts": 3},
             {"book": "s", "rev": "r1", "a": "6:1:1", "voter": "x", "choice": "char", "char": "經", "ts": 4}]
    vs, drop = W.latest_votes(votes, "s", "r1")
    assert len(vs) == 3 and drop == {"别的书或别的 rev": 1}
    vs, _ = W.latest_votes(votes, "s", "r1", u_any_rev=True)
    assert len(vs) == 4
    checked = []
    t = W.triage(vs, B, {}, check=lambda a: checked.append(a) or None)
    by = {d.a: d for d in t.drafts}
    assert by["5:2:2"].payload == {"v": "confirm", "shape": "欽"} and len(by["5:2:2"].votes) == 2   # 两票按 u 合到现格
    assert by["5:2:3"].kind == "moved" and "u3" in by["5:2:3"].held                                 # 并掉的 u
    assert checked == ["6:1:1"]                                    # 按 u 认的不再对框，没 u 的照旧对


def test_votes_no_ledger_unchanged(led):
    vs = [{"book": "s", "rev": "r1", "a": "1:1:1", "u": 7, "voter": "x", "choice": "char", "char": "甲"}]
    checked = []
    t = W.triage(vs, "vol02", {}, check=lambda a: checked.append(a) or None)
    assert checked == ["1:1:1"] and t.drafts[0].a == "1:1:1"


def test_latest_human_follows_u(led):
    from guji_manager._cv import EventTarget, make_event
    e = make_event("h", 1, "confirm", EventTarget(step="seed_admit", unit="cell", key=f"{B}:5:2:1", anchor={"u": 1}),
                   {"v": "confirm", "shape": "欽"})
    g = make_event("h", 2, "confirm", EventTarget(step="seed_admit", unit="cell", key=f"{B}:5:2:4", anchor={"u": 9}),
                   {"v": "confirm", "shape": "庫"})
    assert set(W.latest_human([e, g])) == {f"{B}:5:2:2"}


def test_table_from_ledger(led):
    rows = T.table_rows(led)
    by = {(r["旧格"], r["新格"]): r for r in rows}
    assert by[(f"{B}:5:2:1", f"{B}:5:2:2")]["类别"] == "改号" and by[(f"{B}:5:2:1", f"{B}:5:2:2")]["新字"] == "欽"
    assert by[(f"{B}:5:2:1", f"{B}:5:2:2")]["IoU"] == "1.000"
    assert by[(f"{B}:5:2:2", f"{B}:5:2:3")]["类别"] == "改号"
    assert by[(f"{B}:5:2:3", "")]["类别"] == "删" and "并入 u2" in by[(f"{B}:5:2:3", "")]["说明"]
    assert by[(f"{B}:5:2:4", "")]["说明"] == "u9 格没了"
    assert by[("", f"{B}:5:2:1")]["类别"] == "新增"
    assert all(r["旧格"] != f"{B}:6:1:1" for r in rows)            # 只入过一次账的页不出
    # 下游照旧能读：ops.cell_rekey 的格级表读法
    from guji_manager.ops.cell_rekey import load_cell_map
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "t.tsv"
        p.write_text(T.to_tsv(rows), encoding="utf-8")
        cm = load_cell_map(p)
    assert cm.book == B and cm.move[f"{B}:5:2:1"] == f"{B}:5:2:2" and f"{B}:5:2:3" in cm.deleted


def test_swap_table_by_u():
    from guji_manager.swap.booktext import cell_table
    def ch(cells, **top):
        return {**top, "pages": [{"page": 5, "columns": [{"col": 2, "cells": cells}]}]}
    old = ch([{"a": "5:2:1", "c": "欽", "u": 1}, {"a": "5:2:2", "c": "定", "u": 2}, {"a": "5:2:3", "c": "四", "u": 3}])
    new = ch([{"a": "5:2:1", "c": "傳", "u": 10}, {"a": "5:2:2", "c": "欽", "u": 1}, {"a": "5:2:3", "c": "宝", "u": 2}],
             u_max=10, u_retired=[{"u": 3, "into": 2}])
    rows = cell_table(old, {"pages": []}, new, {"pages": []})
    by = {(r["old"], r["new"]): r for r in rows}
    assert by[("5:2:1", "5:2:2")]["kind"] == "改号" and by[("5:2:2", "5:2:3")]["note"] == "按u；改字"
    assert by[("5:2:3", "")]["kind"] == "删" and "并入 u2" in by[("5:2:3", "")]["note"]
    assert by[("", "5:2:1")]["kind"] == "新增"
    # 一边没 u：照旧走框配对（这里没框，全是删／新增也说明没走 u）
    old2 = ch([{"a": "5:2:1", "c": "欽"}])
    assert all(r["note"] != "按u" for r in cell_table(old2, {"pages": []}, new, {"pages": []}))
