"""存量迁移提案（T2）：裁定直接迁／宽松迁／清单，人裁按框，待审条目，守恒。只出提案不写库。"""
from guji_manager import u_migrate as M
from guji_manager.uid.ledger import Ledger, make_line

B = "vol28"


def _led(tmp_path):
    lg = Ledger.load(B, tmp_path)
    keys = [f"{B}:3:1:{i}" for i in range(1, 6)]
    lg.append([
        make_line(B, 3, "S1", {k: i + 1 for i, k in enumerate(keys)}, chars=dict(zip(keys, "天地玄黃宇")),
                  boxes={keys[2]: [0, 0, 10, 10]}),
        make_line(B, 3, "S2", {k: i + 1 for i, k in enumerate(keys)}, chars=dict(zip(keys, "天地玄黃宇")),
                  boxes={keys[2]: [0, 0, 10, 10]}),
        make_line(B, 4, "T1", {f"{B}:4:1:1": 6}),
        make_line(B, 5, "R1+x", {f"{B}:5:1:1": 7, f"{B}:5:1:2": 8}),
        make_line(B, 5, "R2+y", {f"{B}:5:1:1": 9, f"{B}:5:1:2": 8},
                  lineage=[{"u": 7, "gone": True}]),
    ])
    return lg


def test_plan(tmp_path):
    led = _led(tmp_path)
    rul = [
        {"cell": f"{B}:3:1:2", "cells_sha": "S1", "char": "地", "ctx": {"left": "x", "right": "y"}},     # 直接（旧切分的 sha 也认）
        {"cell": f"{B}:3:1:3", "char": "玄", "ctx": {"left": "某天地", "right": "黃宇某"}},                  # 宽松
        {"cell": f"{B}:3:1:4", "char": "黃", "ctx": {"left": "地地", "right": "宇"}},                       # 一侧同＋字同：宽松
        {"cell": f"{B}:3:1:5", "char": "某", "ctx": {"left": "地黃", "right": ""}},                        # 一侧同、字不同：不迁
        {"cell": f"{B}:3:1:1", "char": "天", "ctx": {"left": "前頁", "right": "地玄"}},                     # 页首：只比右侧
        {"cell": f"{B}:4:1:1", "char": "洪", "ctx": {"left": "", "right": ""}},                            # 账行没记字
        {"cell": f"{B}:9:1:1", "char": "日", "ctx": {}},                                                   # 账上没这页
        {"cell": f"{B}:3:1:5", "char": "宇", "u": 5, "ctx": {}},                                           # 已有 u：不算
        {"cell": f"{B}:3:1:1", "char": "某"},                                                              # 没窗口、字不同：清单
        {"cell": f"{B}:3:1:2", "char": "地"},                                                              # 没窗口、字同：迁
    ]
    hum = [{"id": "h1", "cell": f"{B}:3:1:3", "shape": "玄"},
           {"id": "h2", "cell": f"{B}:3:1:3", "shape": "元"},
           {"id": "h3", "cell": f"{B}:4:1:1"},
           {"id": "h4", "cell": f"{B}:3:1:4"},
           {"id": "h5", "cell": f"{B}:3:1:3", "shape": "元", "reading": "玄"},                          # 字形≠、读作＝账上字：迁
           {"id": "h6", "cell": f"{B}:5:1:2"},                                                       # 没字、各版同 u：迁
           {"id": "h7", "cell": f"{B}:5:1:1"},                                                       # 没字、这格重切过：清单
           {"id": "h8", "cell": f"{B}:5:1:1", "cells_sha": {"row_segment": "R2"}}]                   # 锚同切分：取那行的 u                           # 字形≠、读作＝账上字：迁
    items = [{"id": "pi_a", "cell": "3:1:2"}, {"id": "pi_b", "cell": "7:1:1"}, {"id": "pi_c", "cell": "3:1:1", "u": 1}]
    r = M.plan(led, rulings=rul, humans=hum, items=items)
    got = sorted((x["cell"], x["u"], x["how"]) for x in r["rulings"])
    assert got == [(f"{B}:3:1:1", 1, "宽松"), (f"{B}:3:1:2", 2, "字同"), (f"{B}:3:1:2", 2, "直接"), (f"{B}:3:1:3", 3, "宽松"), (f"{B}:3:1:4", 4, "宽松")]
    assert all(x["payload"]["u"] == x["u"] for x in r["rulings"])
    assert {x["id"]: x["u"] for x in r["human"]} == {"h1": 3, "h3": 6, "h4": 4, "h5": 3, "h6": 8, "h8": 9}
    assert [x["id"] for x in r["items"]] == ["pi_a"]
    assert r["守恒"] == {"rulings": {"迁前": 9, "迁出": 5, "没迁": 4}, "human": {"迁前": 8, "迁出": 6, "没迁": 2},
                         "items": {"迁前": 2, "迁出": 1, "没迁": 1}}
    why = {(x["类别"], x["键"]): x["理由"] for x in r["清单"]}
    assert "窗口对不上" in why[("裁定", f"{B}:3:1:5")] and "没记字" in why[("裁定", f"{B}:4:1:1")]
    assert why[("人裁", f"{B}:3:1:3")] == "人裁「元」，账上这格是「玄」"
    assert why[("人裁", f"{B}:5:1:1")] == "没字可比，且这格重切过"


def test_apply_appends_only(tmp_path):
    """真写：裁定、人裁抄一条带 u（id/批次加 ~u，ts/seq 不变），原文件不动；待审条目追加补 u 的一版。"""
    from guji_manager._cv import RULING_KIND, EventLog, EventTarget, RulingLog, make_event
    from guji_manager.review import pending_items as P
    led = _led(tmp_path / "uid")
    rl, el = RulingLog(tmp_path / "fb"), EventLog(tmp_path / "fb")
    cell = f"{B}:3:1:3"
    rp = {"source": "llm", "group": "O", "prompt_ver": "ctx-m1", "char": "玄", "other": False, "conf": "high", "why": "",
          "model": "m", "cell": cell, "tok": {}, "ctx": {"left": "天地", "right": "黃宇", "hash": "h"}, "subclass": "Z"}
    re_ = make_event("r1", 7, RULING_KIND, EventTarget(step="seed_admit", unit="cell", key=cell, book=B), rp, actor="model")
    rl.append([re_])
    he = make_event("h1", 3, "confirm", EventTarget(step="seed_admit", unit="cell", key=cell, anchor={"source_rev": "r"}),
                    {"v": "confirm", "shape": "玄"})
    el.append([he])
    items = tmp_path / "031.items.jsonl"
    st = P.ItemStore(items)
    st.add("3:1:3", {"why": ["x"]}, by="t", src="human:t")
    st.save()
    st = P.ItemStore(items)
    it = [{**r, "_file": str(items)} for r in st.items.values()]
    before_r, before_h = rl.batch_path("r1").read_text(), el.batch_path("h1").read_text()
    res = M.plan(led, rulings=[rp], humans=[{"id": he.id, "cell": cell, "shape": "玄"}], items=it)
    w = M.apply(res, ruling_events={cell: re_}, human_events={he.id: he}, ruling_log=rl, event_log=el)
    assert (w["裁定"], w["人裁"], w["待审条目"]) == (1, 1, 1)
    assert rl.batch_path("r1").read_text() == before_r and el.batch_path("h1").read_text() == before_h
    nr = list(rl.read("r1~u", raw=True))[0]
    assert nr.payload["u"] == 3 and nr.ts == re_.ts and nr.seq == 7 and nr.id == re_.id + "~u"
    nh = list(el.read("h1~u"))[0]
    assert nh.target.anchor == {"source_rev": "r", "u": 3} and nh.ts == he.ts
    assert next(iter(P.ItemStore(items).items.values()))["u"] == 3
