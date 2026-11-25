"""存量迁移提案（T2）：裁定直接迁／宽松迁／清单，人裁按框，待审条目，守恒。只出提案不写库。"""
import json

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
    anc = tmp_path / "fb" / "anchors" / f"{B}.jsonl"
    anc.parent.mkdir(parents=True, exist_ok=True)
    patch = {"event": he.id, "key": cell, "anchor": {"bbox": [1, 2, 3, 4], "source": "backfill:x"}}
    anc.write_text(json.dumps(patch) + "\n" + json.dumps({**patch, "event": "other"}) + "\n")
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
    # ~u 抄件带上原件的补锚档（cv 按事件 id 查框；11-25 全唐文 004 human_unbound），再写一次不重复
    ls = [json.loads(x) for x in anc.read_text().splitlines()]
    assert ls[-1] == {**patch, "event": he.id + "~u"} and len(ls) == 3 and str(anc) in w["files"]
    assert M.copy_anchor_patches(el, [(he.id, he.id + "~u", B)]) == set() and len(anc.read_text().splitlines()) == 3


def test_rescue_and_close(tmp_path):
    led = _led(tmp_path)
    hum = [{"id": "a", "cell": f"{B}:3:1:2", "shape": "坔"},      # 异体（假表）→ 救回本格 u2
           {"id": "b", "cell": f"{B}:3:1:9", "shape": "黃"},      # 格号不在账、列内近邻有唯一「黃」→ u4
           {"id": "c", "cell": f"{B}:3:1:1", "shape": "某"},      # 字不同、找不到 → 转待审
           {"id": "d", "cell": f"{B}:3:1:5", "shape": "某"},      # 字不同、这格已有带 u 的人裁 → 作废
           {"id": "e", "cell": f"{B}:5:1:1"}]                     # 没字、重切过 → 作废
    res = M.plan(led, humans=hum, rulings=[{"cell": f"{B}:9:1:1", "char": "日", "ctx": {}}],
                 items=[{"id": "pi_x", "cell": "9:9:9", "_file": "f.jsonl"}])
    got, rest = M.rescue_human(led, res["清单"], variant=lambda x, y: {x, y} == {"坔", "地"}, taken={5})
    assert {(x["id"], x["u"], x["how"]) for x in got} == {("a", 2, "异体同"), ("b", 4, "列内近邻同字")}
    co = M.close_out(led, rest, human_u={5, 2, 4})
    assert [r["h"]["id"] for r in co["review"]] == ["c"] and co["review"][0]["u"] == 1
    assert {(v["stream"], v["id"]) for v in co["void"]} == {("events", "d"), ("events", "e"), ("rulings", None)}
    assert co["withdraw"] == [{"id": "pi_x", "file": "f.jsonl", "reason": "格号不在现行账里"}]
    # 有人裁要转待审却没给条目文件：写之前就报错（11-25 全唐文 046／082 写了一半才报）
    import pytest
    with pytest.raises(SystemExit, match="什么都没写"):
        M.check_close_inputs(co, None)
    M.check_close_inputs(co, "f.jsonl")
    M.check_close_inputs({"review": [], "void": []}, None)
    M.check_close_inputs(None, None)
    calls = []

    class _Log:
        def append(self, xs):
            calls.append(xs)
    import os
    os.environ["GUJI_FEEDBACK_DIR"] = str(tmp_path / "fb")
    try:
        with pytest.raises(SystemExit):
            M.write_close(B, co, rescued=got, unscreened=[], human_events={}, event_log=_Log(), review_file=None)
    finally:
        del os.environ["GUJI_FEEDBACK_DIR"]
    assert calls == [] and not (tmp_path / "fb").exists()


def test_check_u_helpers(tmp_path):
    from types import SimpleNamespace as NS
    from guji_manager.feedback.web_votes import HUMAN_VS
    v = next(iter(HUMAN_VS))

    def ev(i, key, ts, batch, u=None, src=None, kind="confirm"):
        return NS(id=i, kind=kind, ts=ts, batch=batch, seq=1,
                  target=NS(unit="cell", key=key, anchor={"u": u} if u is not None else {}),
                  payload={"v": v, **({"source": src} if src else {})})
    evs = [ev("a", f"{B}:1:1:1", "t1", "X"), ev("a~u", f"{B}:1:1:1", "t1", "X~u", u=3),   # 抄件排在原件后
           ev("b", f"{B}:1:1:2", "t1", "Y"),                                                # 没 u、没记档 → 漏
           ev("c", f"{B}:1:1:3", "t2", "Z"),                                                # 没 u、记过作废
           ev("d", f"{B}:1:1:4", "t2", "Z", src="llm")]                                     # 不算人裁
    hum = [e for e in evs if M.is_human_cell(e, HUMAN_VS, lambda e: True)]
    assert [e.id for e in hum] == ["a", "a~u", "b", "c"]
    latest = M.latest_by_key(hum, f"{B}:")
    assert latest[f"{B}:1:1:1"].id == "a~u"
    assert [e.id for e in M.unaccounted(latest, {"c"})] == ["b"]
    # 第二项：~u 抄件缺补锚档（原件有档、抄件没框也没档）
    assert [e.id for e in M.missing_anchor_copies(hum, {"a"})] == ["a~u"]
    assert M.missing_anchor_copies(hum, {"a", "a~u"}) == [] and M.missing_anchor_copies(hum, set()) == []
    anc = tmp_path / "anchors" / f"{B}.jsonl"
    anc.parent.mkdir()
    anc.write_text(json.dumps({"event": "a"}) + "\n")
    assert M.anchor_patch_ids(tmp_path, B) == {"a"} and M.anchor_patch_ids(tmp_path, "zz") == set()


def test_tidy_recheck(tmp_path):
    from guji_manager.review import pending_items as P
    st = P.ItemStore(tmp_path / "x" / "001.items.jsonl")
    st.add("80:6:3", {"pending_reason": "recheck", "prior": {"human": "偁", "event": "e1"}, "detail": "人裁"},
           by="a", src="script:u-closeout", u=5)
    st.put(None, op="open", by="T5", id="pi_b", cell="80:6:3", fp="", state="open", src="script:u-closeout-web",
           doc={"pending_reason": "recheck", "prior": {"vote": "稱"}, "detail": "票"}, u=5, at="9999")
    st.save()
    st = P.ItemStore(tmp_path / "x" / "001.items.jsonl")
    assert M.tidy_recheck(st, {"80:6:3": "□"}) == {"并掉": 1, "补候选": 1}
    st.save()
    st = P.ItemStore(tmp_path / "x" / "001.items.jsonl")
    live = [r for r in st.items.values() if r["state"] == "open"]
    assert len(live) == 1
    d = live[0]["doc"]
    assert d["prior"] == {"human": "偁", "event": "e1", "vote": "稱"} and [x["c"] for x in d["alt"]] == ["偁", "稱"]
    assert M.tidy_recheck(st, {"80:6:3": "□"}) == {"并掉": 0, "补候选": 0}      # 重跑不动
    # 新开时同格已有活条目：并进去
    M.add_recheck(st, "80:6:3", {"prior": {"human": "稱"}}, u=5, now_char="偁", by="a", src="script:u-closeout")
    assert len([r for r in st.items.values() if r["state"] == "open"]) == 1


def test_u_anchor_fill(tmp_path, monkeypatch):
    """无框无档的 ~u 抄件：按账取 u 在现行切分的格框出补锚档；账行与现行戳不符、u 不在现行账行的不补。"""
    from types import SimpleNamespace as NS
    from guji_manager import _cv
    from guji_manager.uid import source
    led = _led(tmp_path)                                      # 第 3 页 S1：3:1:1..5 → u1..5
    monkeypatch.setattr(source, "page_cells_sha", lambda b, p, st: {3: "S1", 4: "OTHER"}.get(p))
    monkeypatch.setattr(_cv, "_cells_versions", lambda b, p, st: [("current", 0.0, 9e9, "cells")], raising=False)
    monkeypatch.setattr(_cv, "_cell_index", lambda c: {(1, 4, ""): ([10, 20, 30, 40], "char")}, raising=False)

    def ev(i, key, u):
        return NS(id=i, ts="t", target=NS(key=key, anchor={"source_rev": "r", "u": u}), payload={"shape": "黃"})
    lines, bad = M.u_anchor_fill(B, [ev("a~u", f"{B}:3:1:2", 4), ev("b~u", f"{B}:3:1:3", 99),
                                     ev("c~u", f"{B}:4:1:1", 1)], led, store=None)
    assert [d["event"] for d in lines] == ["a~u"]
    assert lines[0]["anchor"]["bbox"] == [10, 20, 30, 40] and lines[0]["evidence"] == {"method": "u", "u": 4, "at": "1:4"}
    assert {x["event"]: x["why"][:4] for x in bad} == {"b~u": "u 不在", "c~u": "账里没有"}
    copies = [NS(id="a~u", target=NS(anchor={"u": 4})), NS(id="x~u", target=NS(anchor={"bbox": [1]})),
              NS(id="y~u", target=NS(anchor={"u": 1})), NS(id="z", target=NS(anchor={}))]
    assert [e.id for e in M.boxless_copies(copies, {"y~u"})] == ["a~u"]
