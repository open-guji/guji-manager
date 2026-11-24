"""字格身份账（字格永久编号 u，CV0 T1）：对照、账、init／advance、cell_ref。"""
import json

import pytest

from guji_manager import uid
from guji_manager.cell_ref import UidMissing, cell_of, cell_ref, clear_cache
from guji_manager.uid import source
from guji_manager.uid.ledger import Ledger, make_line, verify
from guji_manager.uid.match import Cell, fresh, match_page

B = "vol31"


def col(page, colno, chars, x=1000, y0=100, h=50, w=40, sub=""):
    """一列竖排格：从上往下，每格高 h。"""
    return [Cell(f"{B}:{page}:{colno}:{i + 1}{sub}", (x, y0 + i * h, x + w, y0 + (i + 1) * h), c)
            for i, c in enumerate(chars)]


class Ctr:
    def __init__(self, n):
        self.n = n

    def __call__(self):
        self.n += 1
        return self.n


def test_fresh_reading_order():
    cells = col(1, 1, "天地玄黃")
    m = fresh(cells, Ctr(0))
    assert list(m.map.values()) == [1, 2, 3, 4]
    assert all(x.get("new") for x in m.lineage)


def test_same_cut_identity():
    old = col(1, 1, "天地玄黃")
    pu = {c.id: i + 1 for i, c in enumerate(old)}
    m = match_page(old, pu, old, Ctr(4))
    assert m.map == pu and m.lineage == [] and m.via["iou"] == 4


def test_insert_char_shifts_slots_keeps_u():
    """列里补一个字：后面整列格号都变，u 跟着框走。"""
    old = col(1, 1, "天玄黃")
    pu = {c.id: i + 1 for i, c in enumerate(old)}
    # 新切分：第 2 格是新补的「地」，原「玄」「黃」挪成第 3、4 格，框不变
    new = [Cell(f"{B}:1:1:1", old[0].box, "天"),
           Cell(f"{B}:1:1:2", (1000, 150, 1040, 175), "地"),
           Cell(f"{B}:1:1:3", old[1].box, "玄"),
           Cell(f"{B}:1:1:4", old[2].box, "黃")]
    # 让旧格框与新格错开：旧「玄」本在 150–200，新「地」只占 150–175，「玄」仍在 150–200 → 给新「玄」一点下移
    new[2] = Cell(f"{B}:1:1:3", (1000, 176, 1040, 226), "玄")
    new[3] = Cell(f"{B}:1:1:4", (1000, 226, 1040, 276), "黃")
    old = [old[0], Cell(old[1].id, (1000, 170, 1040, 222), "玄"), Cell(old[2].id, (1000, 224, 1040, 274), "黃")]
    m = match_page(old, pu, new, Ctr(3))
    assert m.map[f"{B}:1:1:1"] == 1
    assert m.map[f"{B}:1:1:3"] == 2 and m.map[f"{B}:1:1:4"] == 3
    assert m.map[f"{B}:1:1:2"] == 4 and {"u": 4, "new": True} in m.lineage


def test_delete_char_gone():
    old = col(1, 1, "天地玄")
    pu = {c.id: i + 1 for i, c in enumerate(old)}
    new = [old[0], old[2]]
    m = match_page(old, pu, new, Ctr(3))
    assert m.map == {old[0].id: 1, old[2].id: 3}
    assert {"u": 2, "gone": True} in m.lineage


def test_split_half_cells_first_read_keeps_u():
    """一格拆成夹注两半 a/b：先读的 a 沿用原 u，b 发新号记 split_from。"""
    old = [Cell(f"{B}:2:3:5", (1000, 100, 1040, 150), "注")]
    new = [Cell(f"{B}:2:3:5a", (1020, 100, 1040, 150), "小"),
           Cell(f"{B}:2:3:5b", (1000, 100, 1020, 150), "注")]
    m = match_page(old, {old[0].id: 7}, new, Ctr(9))
    assert m.map == {f"{B}:2:3:5a": 7, f"{B}:2:3:5b": 10}
    assert m.lineage == [{"u": 10, "split_from": 7}]
    assert m.via["split"] == 2


def test_merge_keeps_smaller_u():
    old = [Cell(f"{B}:2:3:5a", (1020, 100, 1040, 150), "小"),
           Cell(f"{B}:2:3:5b", (1000, 100, 1020, 150), "注")]
    new = [Cell(f"{B}:2:3:5", (1000, 100, 1040, 150), "注")]
    m = match_page(old, {old[0].id: 12, old[1].id: 8}, new, Ctr(20))
    assert m.map == {f"{B}:2:3:5": 8}
    assert m.lineage == [{"u": 12, "into": 8}]


def test_text_fallback_without_boxes():
    old = [Cell(f"{B}:1:1:{i}", None, c) for i, c in enumerate("天地玄黃", 1)]
    pu = {c.id: i + 10 for i, c in enumerate(old)}
    new = [Cell(f"{B}:1:1:{i}", None, c) for i, c in enumerate("天玄黃", 1)]
    m = match_page(old, pu, new, Ctr(20))
    assert m.map == {f"{B}:1:1:1": 10, f"{B}:1:1:2": 12, f"{B}:1:1:3": 13}
    assert {"u": 11, "gone": True} in m.lineage and m.via["text"] == 3


def test_placeholder_not_text_matched():
    old = [Cell(f"{B}:1:1:1", None, "□")]
    new = [Cell(f"{B}:1:1:1", None, "□")]
    m = match_page(old, {old[0].id: 1}, new, Ctr(1))
    assert m.map == {new[0].id: 2}


# ───────────────────────── 账 ─────────────────────────

@pytest.fixture
def fb(tmp_path, monkeypatch):
    monkeypatch.setenv("GUJI_FEEDBACK_DIR", str(tmp_path / "feedback"))
    monkeypatch.setattr("guji_manager.uid.ledger.default_root", lambda: tmp_path / "feedback" / "uid")
    clear_cache()
    yield tmp_path / "feedback" / "uid"
    clear_cache()


def _char_cord(pages):
    char = {"pages": []}
    cord = {"pages": []}
    for pg, cells in pages.items():
        char["pages"].append({"page": pg, "columns": [{"cells": [
            {"a": c.id.split(":", 1)[1], "c": c.c} for c in cells]}]})
        cord["pages"].append({"page": pg, "cells": [
            {"a": c.id.split(":", 1)[1], "box": [c.box[0], c.box[1], c.box[2] - c.box[0], c.box[3] - c.box[1]]}
            for c in cells]})
    return char, cord


def test_init_from_book_text_reading_order(fb):
    char, cord = _char_cord({1: col(1, 1, "天地"), 2: col(2, 1, "玄黃宇")})
    r = uid.init_from_book_text(B, char, cord)
    assert r["cells"] == 5 and r["u_max"] == 5
    led = Ledger.load(B)
    assert led.u_map() == {"1:1:1": 1, "1:1:2": 2, "2:1:1": 3, "2:1:2": 4, "2:1:3": 5}
    assert verify(led) == []
    with pytest.raises(SystemExit):
        uid.init_from_book_text(B, char, cord)       # 已有账不覆盖


def test_init_copies_u_and_retired(fb):
    char, cord = _char_cord({1: col(1, 1, "天地")})
    char["pages"][0]["columns"][0]["cells"][0]["u"] = 5
    char["pages"][0]["columns"][0]["cells"][1]["u"] = 9
    char["u_max"] = 11
    char["u_retired"] = [{"u": 6, "into": 5}, {"u": 11, "gone": True}]
    uid.init_from_book_text(B, char, cord)
    led = Ledger.load(B)
    assert led.u_map() == {"1:1:1": 5, "1:1:2": 9}
    assert led.u_max() == 11 and set(led.retired()) == {6, 11}
    assert verify(led) == []


class FakeStore:
    pass


def test_advance_and_cell_ref(fb, monkeypatch):
    # 旧切分漏切：「玄」格其实压着「地玄」两字
    old = [Cell(f"{B}:1:1:1", (1000, 100, 1040, 150), "天"), Cell(f"{B}:1:1:2", (1000, 150, 1040, 250), "玄"),
           Cell(f"{B}:1:1:3", (1000, 250, 1040, 300), "黃")]
    char, cord = _char_cord({1: old})
    uid.init_from_book_text(B, char, cord)
    assert cell_ref(f"{B}:1:1:2") == 2
    # 重切：补出「地」，后面格号顺移
    newcut = [Cell(f"{B}:1:1:1", (1000, 100, 1040, 150), "天"),
              Cell(f"{B}:1:1:2", (1000, 150, 1040, 200), "地"),
              Cell(f"{B}:1:1:3", (1000, 200, 1040, 250), "玄"),
              Cell(f"{B}:1:1:4", (1000, 250, 1040, 300), "黃")]
    boxes = {c.id: [c.box[0], c.box[1], c.box[2] - c.box[0], c.box[3] - c.box[1]] for c in newcut}
    monkeypatch.setattr(source, "product_pages", lambda store, book: [1])
    monkeypatch.setattr(source, "cells_sha", lambda store, book, pg: "shaA+p1")
    monkeypatch.setattr(source, "from_products",
                        lambda store, book, pg, with_chars=True: source.PageCut(pg, "shaA+p1", newcut, boxes))
    r = uid.advance(B, FakeStore())
    assert r["entered"] == 1 and r["u_max"] == 4
    assert cell_ref(f"{B}:1:1:3") == 2 and cell_ref(f"{B}:1:1:4") == 3 and cell_ref(f"{B}:1:1:2") == 4
    assert cell_of(2, B) == f"{B}:1:1:3"
    # 同一份切分再跑：不动
    assert uid.advance(B, FakeStore())["entered"] == 0
    led = Ledger.load(B)
    assert len(led.lines) == 2 and led.by_sha(1, "shaA+p1") is not None
    prev, cur = led.page_pair(1)
    assert prev["src"] == "init" and cur["cells_sha"] == "shaA+p1"
    assert cur["lineage"] == [{"u": 4, "split_from": 2}]
    assert verify(led) == []
    with pytest.raises(UidMissing):
        cell_ref(f"{B}:1:1:9")


def test_cell_ref_identity_without_ledger(fb):
    assert cell_ref("vol99:1:1:1") == "vol99:1:1:1"
    assert cell_of("vol99:1:1:1a") == "vol99:1:1:1a"


def test_verify_catches_lost_u(fb):
    led = Ledger.load(B)
    led.append([make_line(B, 1, "s1", {f"{B}:1:1:1": 1, f"{B}:1:1:2": 2}),
                make_line(B, 1, "s2", {f"{B}:1:1:1": 1})])            # u=2 没记 gone
    errs = verify(Ledger.load(B))
    assert any("没有去处" in e for e in errs)


def test_ledger_line_is_central_db_event(fb):
    """账文件归中心库 events 表：每行有 id，target 不带 page（不被页表 rev 闸拦）。"""
    from guji_manager.datastore.scope import classify
    assert classify("feedback/uid/vol31.jsonl") == "events"
    d = make_line(B, 3, "s", {f"{B}:3:1:1": 1})
    assert d["id"].startswith("uid-vol31-p0003-") and d["target"] == {"book": B}
    json.dumps(d, ensure_ascii=False)
