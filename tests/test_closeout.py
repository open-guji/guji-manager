"""标 main 后收尾：锚点待审格、红线、dev 错位写回、叠改字（不连网、不连库）。"""
import json
from pathlib import Path

import pytest

from guji_manager.closeout import anchors as A
from guji_manager.closeout import redlines, stats, writeback
from guji_manager.review.pending_reason import PendingReason as R
from guji_manager.review.pending_reason import parse, specs
from guji_manager.swap import overlay_edits as OE


def char(*cols):
    """cols: 每列一个字串；页1，列从1起，格 1:列:序。"""
    return {"pages": [{"columns": [{"cells": [{"a": f"1:{ci}:{i}", "c": ch} for i, ch in enumerate(s, 1)]}
                                   for ci, s in enumerate(cols, 1)]}]}


# ---------- 原因码登记（A31 #393：A01–A03，deferred，不算人审率） ----------
def test_new_reasons_registered():
    for r, code in ((R.ANCHOR_MISS, "A01"), (R.ADD_DEL, "A02"), (R.ANCHOR_DRIFT, "A03")):
        sp = specs()[r]
        assert sp.code == code and sp.route.value == "deferred" and sp.reviewer.value == "none"
        assert parse(r.value) is r
    assert specs()[R.UNKNOWN].priority > specs()[R.ANCHOR_DRIFT].priority


# ---------- detail ----------
def test_detail_roundtrip_and_multi_cause():
    it = ("punct", "#3", "3:1:2", "3:1:4", "，", "ANCHOR_MISS｜校验字变了：甲→乙")
    e = A.entry(it)
    d = A.append("A12:lib", [e])
    assert d.startswith("A12:lib" + A.SEP + A.MARK)       # 原 detail 保留在前
    assert A.decode(d) == [e]
    assert A.append(d, [e]) == d                          # 幂等
    e2 = A.entry(("entity", "p1", "3:1:5～3:1:6", "", "某某", "ADD_DEL｜首尾格无对应（删除格）"))
    assert A.decode(A.append(d, [e2])) == [e, e2]
    assert A.decode(None) == [] and A.decode("x") == [] and A.decode("anchor=[oops") == []


def test_cell_of():
    assert A.cell_of("vol04:3:1:2") == "3:1:2"
    assert A.cell_of("3:1:2～3:1:4") == "3:1:2"
    assert A.cell_of("") is None and A.cell_of("～") is None


def test_stamp_keeps_main_reason_and_adds_cells():
    plan = {"cells": [{"cell": "vol20:3:1:4", "pending_reason": "group_abstain", "pending_reason_detail": "g1:x"}]}
    items = [("punct", "#1", "3:1:2", "3:1:4", "，", "ANCHOR_MISS｜x"),
             ("punct", "#2", "5:1:1", "", "。", "ADD_DEL｜旧格无对应（删除格）"),     # 无新格：退回旧格
             ("entity-复核", "e9", "7:1:1～7:1:2", "7:1:1～7:1:2", "某某", "SPAN_REWORD｜同格改字已放行")]
    n = A.stamp(plan, items)
    assert n["appended"] == 1 and n["new"] == 2
    assert plan["cells"][0]["pending_reason_also"] == ["anchor_miss"]        # 其余原因进 also
    by = {x["cell"]: x for x in plan["cells"]}
    assert by["vol20:3:1:4"]["pending_reason"] == "group_abstain"            # 主因不变
    assert A.decode(by["vol20:3:1:4"]["pending_reason_detail"])[0]["i"] == "#1"
    assert by["vol20:5:1:1"]["pending_reason"] == "add_del"                  # 沿用册前缀
    assert by["vol20:7:1:1"]["pending_reason"] == "anchor_miss"
    assert A.stamp(plan, items)["new"] == 2 and len(plan["cells"]) == 3      # 重算幂等：先清后写，不重复计格
    assert plan["cells"][0]["pending_reason_also"] == ["anchor_miss"]
    A.stamp(plan, [])                                                         # 问题消了 → 自然消失
    assert plan["cells"] == [{"cell": "vol20:3:1:4", "pending_reason": "group_abstain", "pending_reason_detail": "g1:x"}]
    A.stamp(plan, items)
    assert len(A.decode(by["vol20:3:1:4"]["pending_reason_detail"])) == 1


def test_main_reason_priority():
    es = [A.entry(("punct", "#1", "1:1:1", "1:1:1", "，", "ANCHOR_DRIFT｜x")),
          A.entry(("punct", "#2", "1:1:1", "1:1:1", "。", "ADD_DEL｜x"))]
    assert A.main_reason(es) is R.ADD_DEL
    assert A.reason_of("WHAT") is R.ANCHOR_MISS


def test_stats():
    plan = {"cells": [{"cell": "3:1:4", "pending_reason": "group_abstain",
                       "pending_reason_detail": A.append("g", [A.entry(("punct", "#1", "3:1:2", "3:1:4", "，", "ANCHOR_MISS｜x"))])},
                      {"cell": "5:1:1", "pending_reason": "add_del"}, {"cell": "6:1:1", "pending_reason": "lib_missing"}]}
    s = stats.plan_stats(plan)
    assert s["cells"] == 3 and s["anchor_main"] == {"add_del": 1} and s["anchor_any"] == 2
    assert s["by_code"] == {"ANCHOR_MISS": 1} and s["by_layer"] == {"punct": 1}


# ---------- 红线 ----------
def test_redlines():
    ok = redlines.check("vol20", human_total=500, human_lost=5, anchors_moved=91, anchors_left=9)
    assert ok.ok and "红线内" in ok.line()                                     # 1% 与 9% 都不超
    assert not redlines.check("v", human_total=500, human_lost=6, anchors_moved=100, anchors_left=0).ok
    assert not redlines.check("v", human_total=0, human_lost=1, anchors_moved=0, anchors_left=0).ok
    assert not redlines.check("v", human_total=10, human_lost=0, anchors_moved=84, anchors_left=16).ok
    assert redlines.check("v", human_total=10, human_lost=0, anchors_moved=85, anchors_left=15).ok
    assert not redlines.check("v", human_total=0, human_lost=0, anchors_moved=0, anchors_left=0, errors=["boom"]).ok
    assert not redlines.check("v", human_total=0, human_lost=0, anchors_moved=0, anchors_left=0, glyph_verify_ok=False).ok


# ---------- dev 错位写回（三条件） ----------
def test_writeback_three_conditions():
    c = char("甲乙丙丁")                                     # 1:1:1甲 2乙 3丙 4丁
    punct = {"punctuations": [
        {"mark": "，", "pre_char": "乙", "anchor": "1:1:1", "char_offset": 0, "source": "rule:auto"},       # 满足
        {"mark": "。", "pre_char": "丙", "anchor": "1:1:2", "char_offset": 1, "source": "claude:manual"},   # 人工
        {"mark": "、", "pre_char": "丁", "anchor": "1:1:4", "char_offset": 3, "source": "rule:auto"},       # 当前就对
        {"mark": "；", "pre_char": "甲", "anchor": "1:1:3", "char_offset": 2, "source": "rule:auto"},       # 表位字≠pre_char
        {"mark": "！", "pre_char": "丙", "anchor": "1:1:4", "char_offset": 3, "source": "rule:auto"},       # 满足（丁≠丙，表→3）
    ]}
    cellmap = {"1:1:1": "1:1:2", "1:1:2": "1:1:3", "1:1:4": "1:1:3", "1:1:3": "1:1:2"}
    ok, skip = writeback.plan_fixes(punct, c, cellmap)
    assert [f["idx"] for f in ok] == [0, 4]
    why = {s["idx"]: s["why"] for s in skip}
    assert "人裁" in why[1] and "表位置" in why[3] or "≠" in why[3]
    assert writeback.apply_fixes(punct, c, ok) == 2
    assert punct["punctuations"][0]["anchor"] == "1:1:2" and punct["punctuations"][0]["char_offset"] == 1
    assert punct["punctuations"][4]["anchor"] == "1:1:3"
    assert punct["punctuations"][1]["anchor"] == "1:1:2"                      # 人工的没动
    with pytest.raises(ValueError):
        writeback.apply_fixes(punct, c, ok)                                  # 计划过期（锚点已变）
    assert len(writeback.audit_lines("081", ok)) == 2


def test_writeback_old_pre_from_replay():
    """dev 上 pre_char 被「校验字同步」刷成错位处的字：三条件要用换图前的旧 pre_char。"""
    c = char("甲乙丙丁")
    punct = {"punctuations": [{"mark": "，", "pre_char": "丁", "anchor": "1:1:4", "char_offset": 3, "source": "claude:A33"},
                              {"mark": "。", "pre_char": "乙", "anchor": "1:1:2", "char_offset": 1, "source": "claude:A33"}]}
    rows = [["15", "标点", "#0 '，' 前字=丙", "1:1:3", "1:1:3", "1:1:4", "丁", "丙", "丁", "ANCHOR_MISS"],
            ["15", "标点", "#1 '。' 前字=乙", "1:1:2", "1:1:2", "1:1:2", "", "", "", "ANCHOR_MISS"],   # 没错位：同号不收
            ["15", "实体", "e1", "1:1:1～1:1:2", "1:1:2～1:1:3", "1:1:1～1:1:2", "", "", "", "ANCHOR_MISS"],
            ["16", "标点", "#9 '，' 前字=甲", "1:1:1", "1:1:2", "1:1:4", "", "", "", "ANCHOR_MISS"]]
    m, pre, notes = writeback.from_replay(rows, "015")
    assert m == {"1:1:4": "1:1:3"} and pre == {("1:1:4", "，"): "丙"} and notes == []
    assert writeback.plan_fixes(punct, c, m)[0] == []                          # 不给旧值：dev 刷新过的 pre_char=丁，对不上
    ok, skip = writeback.plan_fixes(punct, c, m, pre)
    assert [f["idx"] for f in ok] == [0] and not skip
    writeback.apply_fixes(punct, c, ok)
    assert punct["punctuations"][0]["anchor"] == "1:1:3" and punct["punctuations"][0]["pre_char"] == "丙"
    m2, _p, notes = writeback.from_replay(rows + [["15", "标点", "#2 '，' 前字=乙", "1:1:2", "1:1:2", "1:1:4", "", "", "", ""]], "15")
    assert m2 == {} and len(notes) == 1                                        # 同一 dev 锚点指向两处 → 丢弃交人看


def test_writeback_sample_deterministic():
    fx = [{"idx": i} for i in range(52)]
    s1, s2 = writeback.sample(fx, 30), writeback.sample(fx, 30)
    assert s1 == s2 and len(s1) == 30 and writeback.sample(fx[:5], 30) == fx[:5]


# ---------- 叠改字 ----------
def test_overlay_cases_and_alignment():
    new = char("甲乙丙丁", "戊己庚辛")
    edits = [{"anchor": "9:1:1", "old": "甲", "new": "申"},     # 表 9:1:1→1:1:1，机器没动 → applied
             {"anchor": "9:1:2", "old": "乙", "new": "已"},     # 新格已是「已」→ already
             {"anchor": "9:1:3", "old": "丙", "new": "内"},     # 新格被机器改成「丁」 → overturned
             {"anchor": "9:1:4", "old": "丁", "new": "T"},      # 表无对应 → lost
             ]
    cm = {"9:1:1": "1:1:1", "9:1:2": "1:1:2", "9:1:3": "1:1:3"}
    new["pages"][0]["columns"][0]["cells"][1]["c"] = "已"
    new["pages"][0]["columns"][0]["cells"][2]["c"] = "丁"
    out, rep = OE.overlay(new, edits, cm)
    assert rep.counts() == {"applied": 1, "already": 1, "overturned": 1, "lost": 1}
    assert rep.overturned[0]["machine"] == "丁"
    got = {c["a"]: c["c"] for c in OE._cells(out)}
    assert got["1:1:1"] == "申" and got["1:1:3"] == "内"
    assert new["pages"][0]["columns"][0]["cells"][0]["c"] == "甲"             # 入参不动


def test_overlay_verify_catches_misalignment():
    a = char("甲乙丙")
    b = char("甲乙")
    with pytest.raises(OE.AlignmentError):
        OE.verify(a, b, set())
    c = char("甲X丙")
    with pytest.raises(OE.AlignmentError):
        OE.verify(a, c, set())
    OE.verify(a, c, {"1:1:2"})


# ---------- CLI 与 remap_data 联调（有 book-text 检出才跑） ----------
BT = Path("/home/user/open-guji/book-text")


@pytest.mark.skipif(not (BT / "scripts/book-text/remap_anchors.py").is_file(), reason="无 book-text 检出")
def test_remap_lib_smoke():
    from guji_manager.closeout import remap_lib
    try:
        ra = remap_lib.load_ra(BT)
    except SystemExit:
        pytest.skip("检出里的 remap_anchors 还没有 remap_data")
    rows = [{"旧格": f"vol1:1:1:{i}", "新格": f"vol1:1:1:{i}", "旧字": c, "新字": c, "类别": "同格", "IoU": "0.9"}
            for i, c in enumerate("甲乙丙", 1)]
    rows.append({"旧格": "vol1:1:1:4", "新格": "", "旧字": "丁", "新字": "", "类别": "删", "IoU": ""})
    c = char("甲乙丙")
    punct = {"punctuations": [{"mark": "，", "pre_char": "乙", "anchor": "1:1:2", "char_offset": 1},
                              {"mark": "。", "pre_char": "丁", "anchor": "1:1:4", "char_offset": 3}]}
    r = remap_lib.run(ra, "001", c, punct, None, rows)
    assert r["moved"] == 1 and r["left"] == 1
    assert punct["punctuations"][1]["anchor"] == "1:1:4"                      # 入参没被改
    plan = {"cells": []}
    n = A.stamp(plan, r["report"])
    assert n["add_del"] == 1 and plan["cells"][0]["pending_reason"] == "add_del"


def test_cli_redline_and_stats(tmp_path, capsys):
    from guji_manager import commands
    p = tmp_path / "vol20.json"
    p.write_text(json.dumps({"cells": [{"cell": "3:1:1", "pending_reason": "anchor_miss"}]}), encoding="utf-8")
    commands.run(["closeout", "stats", str(p)])
    assert "vol20" in capsys.readouterr().out
    cmd = commands.COMMANDS["closeout"][1]
    ap = __import__("argparse").ArgumentParser()
    commands.COMMANDS["closeout"][0](ap.add_subparsers())
    assert cmd(ap.parse_args(["closeout", "redline", "vol20", "--human-total", "100", "--human-lost", "5"])) == 1
    assert cmd(ap.parse_args(["closeout", "redline", "vol20", "--human-total", "100", "--human-lost", "1"])) == 0


# ---------- 现算（方案 8.9） ----------
from guji_manager.closeout import derive as D  # noqa: E402


def test_derive_a01_a02_and_resolution():
    c = {"pages": [{"columns": [{"cells": [{"a": f"1:1:{i}", "c": ch} for i, ch in enumerate("甲乙。丙丁戊己。庚辛", 1)]}]}]}
    punct = {"punctuations": [
        {"mark": "。", "pre_char": "乙", "anchor": "1:1:2", "char_offset": 1},       # 有效
        {"mark": "。", "pre_char": "己", "anchor": "1:1:7", "char_offset": 6},       # 有效（句末）
        {"mark": "，", "pre_char": "丁", "anchor": "1:1:6", "char_offset": 5},       # 无效：格上是「戊」？ 1:1:6=戊 → 校验字不符
        {"mark": "，", "pre_char": "辛", "anchor": "1:1:30", "char_offset": 29}]}    # 无效：格不存在
    ent = {"entities": [{"id": "e1", "text": "丙丁", "anchor": {"start": "1:1:4", "end": "1:1:5"}}]}
    items = D.invalid_anchors(c, punct, ent)
    assert [(i[1], i[3]) for i in items] == [("#2", "1:1:6"), ("#3", "1:1:10")]    # 不存在的格 → 同页最近格
    rows = [{"旧格": "vol1:1:1:4", "新格": "vol1:1:1:4", "类别": "同格"},
            {"旧格": "vol1:1:1:5", "新格": "", "类别": "删"}]
    assert D.add_del_sites(rows) == {"1:1:4"}                                  # 删格 :5 的前邻 :4
    out = D.derive(c, punct, ent, rows)
    codes = {i[1]: A.split_code(i[5])[0] for i in out}
    assert codes == {"#2": "ADD_DEL", "#3": "ANCHOR_MISS"}                     # #2 在第二句（丙…己）里；#3 在句外
    # 点校重挂后：把 #2 挂回有效格 → 下次现算自然没了
    punct["punctuations"][2].update(anchor="1:1:5", pre_char="丁")
    punct["punctuations"][3].update(anchor="1:1:10", pre_char="辛")
    assert D.derive(c, punct, ent, rows) == []


def test_parse_drift():
    msg = "081.char.json 3:1:2（， comma claude:x）：旧字「甲」→现「乙」，对齐后应在 3:1:3"
    it = D.parse_drift(msg)
    assert it[2] == "3:1:2" and A.split_code(it[5])[0] == "ANCHOR_DRIFT" and it[5].endswith("3:1:3")
    assert D.parse_drift("乱七八糟") is None


def test_subcell_ids_do_not_crash():
    """夹注半格格号带 a／b 后缀（如 88:6:19b），增删格邻格、最近格都要认得。"""
    from guji_manager.closeout.derive import add_del_sites, _nearest
    rows = [{"类别": "同格", "旧格": "vol01:88:6:18b", "新格": "vol01:88:6:17b"},
            {"类别": "删", "旧格": "vol01:88:6:19b", "新格": ""},
            {"类别": "同格", "旧格": "vol01:88:6:20b", "新格": "vol01:88:6:18b"}]
    assert add_del_sites(rows) == {"88:6:17b", "88:6:18b"}
    slots = [("88:6:17a", "甲"), ("88:6:17b", "乙"), ("88:6:18", "丙")]
    assert _nearest(slots, {}, "88:6:19b") == "88:6:18"


def test_stamp_pending(tmp_path):
    from guji_manager.closeout import plan as P
    c = {"pages": [{"columns": [{"cells": [{"a": f"1:1:{i}", "c": ch} for i, ch in enumerate("甲乙丙", 1)]}]}]}
    (tmp_path / "001.char.json").write_text(json.dumps(c), encoding="utf-8")
    (tmp_path / "001.punct.json").write_text(json.dumps({"punctuations": [
        {"mark": "，", "pre_char": "乙", "anchor": "1:1:2"}, {"mark": "。", "pre_char": "丁", "anchor": "1:1:9"}]}), encoding="utf-8")
    pend = tmp_path / "001.pending.json"
    pend.write_text(json.dumps({"cells": [{"cell": "1:1:3", "pending_reason": "group_abstain"}]}), encoding="utf-8")
    n = P.stamp_pending(pend, tmp_path / "001.char.json", tmp_path, "001")
    assert n["items"] == 1 and n["new"] == 0 and n["appended"] == 1                  # 无效锚点的落点正是单上已有的 1:1:3
    cell = json.loads(pend.read_text(encoding="utf-8"))["cells"][0]
    assert cell["pending_reason"] == "group_abstain" and cell["pending_reason_also"] == ["anchor_miss"]
    assert P.stamp_pending(tmp_path / "none.json", tmp_path / "001.char.json", tmp_path, "001") == {}
    assert P.stamp_pending(pend, tmp_path / "001.char.json", tmp_path, "002") == {}   # 无伴生层
