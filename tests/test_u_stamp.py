"""字格永久编号 u：写裁定、人裁、待审条目、book-text 导出都盖 u（T2，设计 doc/4-反馈迭代/设计-字格u改挂.md）。

T1 身份账合进来之前，`cell_ref` 恒等返回格号＝册没账；这里用假的 cell_ref 模拟「册有账」。"""
import copy

import pytest

from guji_manager import u_stamp as U
from guji_manager.review import pending_items as P

LEDGER = {"vol31": {"5:2:3": 101, "5:2:4": 102, "5:2:4a": 103, "6:1:1": 200}}


class UidMissing(KeyError):
    pass


def fake_ref(cid: str):
    """册有账查账（查不到抛），没账恒等——同 T1 定的 cell_ref 口径。"""
    book, bare = cid.split(":", 1)
    if book not in LEDGER:
        return cid
    try:
        return LEDGER[book][bare]
    except KeyError:
        raise UidMissing(cid) from None


@pytest.fixture
def ledger(monkeypatch):
    monkeypatch.setattr(U, "_cell_ref", lambda: fake_ref)


def _ruling(cell, **kw):
    from guji_manager._cv import RULING_KIND, EventTarget, make_event
    p = {"group": "O", "prompt_ver": "ctx-m1", "cell": cell, "char": "曰", **kw}
    return make_event("b", 1, RULING_KIND, EventTarget(step="seed_admit", unit="cell", key=cell, book=cell.split(":")[0]),
                      p, actor="model")


def _human(cell, unit="cell"):
    from guji_manager._cv import EventTarget, make_event
    return make_event("h", 1, "confirm", EventTarget(step="seed_admit", unit=unit, key=cell), {"v": "confirm", "shape": "曰"})


def test_full_cell():
    assert U.is_full_cell("vol31:5:2:3") and U.is_full_cell("vol31:5:2:4a") and U.is_full_cell("vol31:1:3:-1")
    assert not U.is_full_cell("5:2:3") and not U.is_full_cell("ctx:abc") and not U.is_full_cell(None)


def test_no_ledger_is_noop():
    """T1 未合时 cell_ref 恒等：一律不盖，事件与以前逐字节同。"""
    ev = _ruling("vol31:5:2:3")
    before = ev.model_dump()
    assert U.stamp_rulings([ev]) == 0 and ev.model_dump() == before
    h = _human("vol31:5:2:3")
    before = h.model_dump()
    assert U.stamp_human([h]) == 0 and h.model_dump() == before
    assert U.u_map("vol31", ["5:2:3"]) == {}


def test_stamp_rulings(ledger):
    evs = [_ruling("vol31:5:2:3"), _ruling("vol31:5:2:4a"), _ruling("vol02:1:1:1"), _ruling("vol31:5:2:4", u=7)]
    assert U.stamp_rulings(evs) == 2
    assert [e.payload.get("u") for e in evs] == [101, 103, None, 7]     # 没账的册不盖；已有 u 的不动
    assert evs[0].payload["cell"] == "vol31:5:2:3"                         # 格号照旧（双写）


def test_stamp_rulings_missing_cell_raises(ledger):
    with pytest.raises(KeyError):
        U.stamp_rulings([_ruling("vol31:9:9:9")])


def test_stamp_human(ledger):
    hs = [_human("vol31:6:1:1"), _human("vol31:6:1:1", unit="page"), _human("vol02:1:1:1")]
    hs[0].target.anchor = {"bbox": [1, 2, 3, 4]}
    assert U.stamp_human(hs) == 1
    assert hs[0].target.anchor == {"bbox": [1, 2, 3, 4], "u": 200}
    assert hs[1].target.anchor is None and hs[2].target.anchor is None
    d = hs[0].model_dump()                                                  # 落盘（pydantic）后 u 还在
    assert d["target"]["anchor"]["u"] == 200


def test_u_map(ledger):
    assert U.u_map("vol31", ["5:2:3", "vol31:6:1:1", ""]) == {"5:2:3": 101, "6:1:1": 200}
    assert U.u_map("vol02", ["1:1:1"]) == {}


def test_append_rulings_stamps(ledger, tmp_path):
    from guji_manager.ruling_write import append_rulings

    class _Log:
        def append(self, evs):
            self.got = evs
            return len(evs)
    log = _Log()
    assert append_rulings(log, [_ruling("vol31:5:2:3")]) == 1
    assert log.got[0].payload["u"] == 101


# ── 待审条目 ──

def _store(tmp_path):
    return P.ItemStore.open(tmp_path, "96mid1ogzk", "031")


def _cells(*xs):
    return [{"cell": c, "review": "pending", "why": [w]} for c, w in xs]


def test_reconcile_by_u_survives_renumber_and_image_change(tmp_path):
    """重切：格号变了、图块指纹也变了——按 u 仍认上同一条目（以前会关旧开新）。"""
    s = _store(tmp_path)
    P.reconcile(s, _cells(("5:2:3", "lib_low"), ("5:2:4", "ref_gap")), src="r1",
                fps={"5:2:3": "f1", "5:2:4": "f2"}, us={"5:2:3": 101, "5:2:4": 102})
    ids = {x["u"]: x["id"] for x in s.items.values()}
    r = P.reconcile(s, _cells(("5:2:4", "lib_low"), ("5:2:5", "ref_gap")), src="r2",
                    fps={"5:2:4": "g1", "5:2:5": "g2"}, us={"5:2:4": 101, "5:2:5": 102})
    assert r["开"] == [] and r["关"] == []
    assert s.items[ids[101]]["cell"] == "5:2:4" and s.items[ids[102]]["cell"] == "5:2:5"
    assert sorted(r["挪格"]) == ["5:2:3→5:2:4", "5:2:4→5:2:5"]


def test_reconcile_u_blocks_wrong_cell_match(tmp_path):
    """格号相同但 u 不同（补了一个字，后面整列挪了）：不能按格号认成同一条。"""
    s = _store(tmp_path)
    P.reconcile(s, _cells(("5:2:3", "lib_low"),), src="r1", us={"5:2:3": 101})
    r = P.reconcile(s, _cells(("5:2:3", "lib_low"),), src="r2", us={"5:2:3": 150})
    assert r["开"] == ["5:2:3"] and r["关"] == ["5:2:3"]


def test_reconcile_backfills_u_and_exports(tmp_path):
    s = _store(tmp_path)
    P.reconcile(s, _cells(("5:2:3", "lib_low"),), src="r1")                   # 没账时开的条目
    assert "u" not in next(iter(s.items.values()))
    r = P.reconcile(s, _cells(("5:2:3", "lib_low"),), src="r2", us={"5:2:3": 101})
    it = next(iter(s.items.values()))
    assert it["u"] == 101 and it["ver"] == 2 and r["开"] == []
    doc = P.export_sheet(s, {"rev": "x"})
    assert doc["cells"][0]["u"] == 101 and doc["cells"][0]["cell"] == "5:2:3"
    # 导出的单（带 u）再 reconcile：认单上的 u，doc 不因多了 u 而判「改」
    r = P.reconcile(s, copy.deepcopy(doc["cells"]), src="r3")
    assert r["不变"] == 1 and r["改"] == []


def test_reconcile_without_u_unchanged(tmp_path):
    """没给 us、单上也没 u：与以前完全一样（条目里不出现 u 键）。"""
    s = _store(tmp_path)
    P.reconcile(s, _cells(("1:1:1", "a"),), src="r1", fps={"1:1:1": "f1"})
    assert all("u" not in x for x in s.items.values())
    assert all("u" not in c for c in P.export_sheet(s)["cells"])


def test_add_with_u(tmp_path):
    s = _store(tmp_path)
    r = s.add("vol31:5:2:3", {"why": ["x"]}, by="t", src="human:t", u=101)
    assert r["u"] == 101 and r["cell"] == "5:2:3"
