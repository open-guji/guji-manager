"""待审原因判定（review/reasons.py）：造格子，核每条规则与先后、判不出给 unknown、写回待审单。"""
import json

from guji_manager.review.pending_reason import PendingReason as R
from guji_manager.review.reasons import Cell, build_context, classify, reasons_for_pending, stamp, detail_of


def _cls(cells, lib=None, var=None):
    ctx = build_context(cells, lib_n=lib, are_variants=var)
    return [classify(c, ctx) for c in cells]


def test_unknown_when_no_rule_hits():
    assert _cls([Cell(id="v:1:1:1", char="甲", ref="甲")]) == [R.LIB_UNRECOGNIZED]
    assert _cls([Cell(id="v:1:1:1", char=None, ref=None, doubts=["foo"])], ) == [R.REF_GAP]
    c = Cell(id="v:1:1:1", char="甲", ref="甲")
    ctx = build_context([c])
    # 去掉兜底规则也只会落到 unknown，不会报错
    from guji_manager.review import reasons
    saved = reasons.RULES.pop(R.LIB_UNRECOGNIZED)
    try:
        assert classify(c, ctx) is R.UNKNOWN
    finally:
        reasons.RULES[R.LIB_UNRECOGNIZED] = saved


def test_review_states_first():
    c = Cell(id="v:1:1:1", char="已", ref="己", doubts=["occluded"], recheck=True, note="机器改判「□」→「已」，推翻人裁，请核")
    assert _cls([c]) == [R.MACHINE_CHANGED]
    old = Cell(id="v:1:1:4", char="已", ref="己", recheck=True, note="机器改判「□」→「已」，无人裁，请核")
    assert _cls([old]) == [R.RECHECK]      # 11-05 前老单的无人裁复审格不算 X03
    c2 = Cell(id="v:1:1:2", char="甲", ref="甲", recheck=True, note="旧裁 山，新票 由")
    assert _cls([c2]) == [R.RECHECK]
    assert _cls([Cell(id="v:1:1:3", char="甲", ref="甲", doubts=["src_code_conflict"])]) == [R.RULING_CONFLICT]


def test_weak_page_needs_low_column_agreement():
    """弱证据格只在本列大多对不上时算整页对不上（史記 02:106 半色调页：列一致率 0.7–1，对位对、只是认不准）。"""
    halftone = [Cell(id=f"v:5:{i % 8 + 1}:{i}", char="甲", ref="乙", col_agree=0.8) for i in range(12)]
    assert R.SEG_PAGE_UNALIGNED not in set(_cls(halftone))
    shifted = [Cell(id=f"v:6:1:{i}", char="甲", ref="乙", col_agree=0.1) for i in range(12)]
    assert set(_cls(shifted)) == {R.SEG_PAGE_UNALIGNED}
    unknown = [Cell(id=f"v:7:1:{i}", char="甲", ref="乙") for i in range(12)]   # 没有列一致率（单上补的格）照旧
    assert set(_cls(unknown)) == {R.SEG_PAGE_UNALIGNED}


def test_occluded_split_by_ref():
    a = Cell(id="v:1:1:1", char="甲", ref="甲", doubts=["occluded"])
    b = Cell(id="v:1:1:2", char="甲", ref="〓", doubts=["occluded"])
    assert _cls([a, b]) == [R.OCCLUDED_WITH_REF, R.OCCLUDED_NO_REF]


def test_occluded_jys_ref_goes_to_hard_pair():
    """D01 深挖（A24 11-08）：遮挡格、整理本字是己已巳日曰之一 → H01（印泥下库首位是噪声、机器字 None，原先永远落 D01）；其余遮挡格照旧分 D01／D02。"""
    a = Cell(id="v:1:1:1", char=None, ref="巳", cands=[["唐", 0.8]], doubts=["occluded"])
    b = Cell(id="v:1:1:2", char=None, ref="曰", doubts=["occluded"], evidence={"occluded": {"density": 30.0}})
    c = Cell(id="v:1:1:3", char=None, ref="官", cands=[["宮", 0.99]], doubts=["occluded"])
    d = Cell(id="v:1:1:4", char=None, ref="〓", doubts=["occluded"])
    e = Cell(id="v:1:1:5", char="甲", ref="巳", doubts=["occluded"])      # 机器字不在组内：不当极难形近
    assert _cls([a, b, c, d, e]) == [R.HARD_PAIR, R.HARD_PAIR, R.OCCLUDED_WITH_REF, R.OCCLUDED_NO_REF, R.OCCLUDED_WITH_REF]


def test_page_and_column_unaligned():
    page = [Cell(id=f"v:2:{i // 20 + 1}:{i % 20 + 1}", char="甲", ref=None) for i in range(10)]
    assert set(_cls(page)) == {R.SEG_PAGE_UNALIGNED}
    col = [Cell(id=f"v:3:4:{i}", char="甲", ref=None) for i in range(5)]
    assert set(_cls(col)) == {R.SEG_COL_UNALIGNED}


def test_hard_pair_before_group():
    c = Cell(id="v:1:1:1", char="日", ref="曰", evidence={"group": {"id": "ry", "solvers": []}})
    assert _cls([c]) == [R.HARD_PAIR]


def test_group_kinds():
    g = lambda **k: Cell(id="v:1:1:1", char="傅", ref="傳", evidence={"group": {"id": "fc", **k}})
    assert _cls([g(solvers=[{"char": None}])]) == [R.GROUP_ABSTAIN]
    assert _cls([g(solvers=[{"char": "傅"}, {"char": "傳"}])]) == [R.GROUP_CONFLICT]
    assert _cls([g(solvers=[{"char": "傅"}], why="ref_dissent")]) == [R.GROUP_REF_DISSENT]
    assert _cls([g(solvers=[{"char": "傅"}], decision="demote")]) == [R.GROUP_DEMOTED]
    assert _cls([g(solvers=[{"char": "傅"}])]) == [R.GROUP_ABSTAIN]   # Z05 已停用：并入 Z01


def test_group_kinds_by_evidence_1107():
    """A24 Z 类梳理 11-07：只按解法给出了什么分，场景写 detail。"""
    g = lambda ref="傳", doubts=(), **k: Cell(id="v:1:1:1", char="傅", ref=ref, doubts=list(doubts),
                                             evidence={"group": {"id": "fc", **k}})
    # 联合判只有一个字（共字组没表态）→ Z07，不是打架；两个字照旧 Z02
    assert _cls([g(mode="joint", decision="review", why="joint", solvers=[{"char": "傅"}, {"solver": "yz:ctx", "char": None}])]) \
        == [R.GROUP_UNCONFIRMED]
    assert _cls([g(mode="joint", decision="review", why="joint", solvers=[{"char": "傅"}, {"char": "傳"}])]) == [R.GROUP_CONFLICT]
    # 复核：没字 Z01、两字 Z02、一字 Z03、整理本是组里另一形 Z04
    assert _cls([g(mode="review", decision="demote", why="abstain", solvers=[{"char": None}])]) == [R.GROUP_ABSTAIN]
    assert _cls([g(mode="review", decision="demote", why="conflict", solvers=[{"char": "傅"}, {"char": "傳"}])]) == [R.GROUP_CONFLICT]
    assert _cls([g(mode="review", decision="demote", why="agree", solvers=[{"char": "傅"}])]) == [R.GROUP_DEMOTED]
    assert _cls([g(mode="review", decision="demote", why="agree", solvers=[{"char": "傅"}],
                   doubts=["group_flow_ref_dissent"])]) == [R.GROUP_REF_DISSENT]
    # 参校本〓：不是「与参校本不同」，落 R01
    assert _cls([g(ref="〓", mode="lift", decision="review", why="coord_dissent", solvers=[{"char": "卿"}])]) == [R.REF_LACUNA]
    # 复核 keep 而解法全弃权：字组没意见，不落 Z01
    assert _cls([g(mode="review", decision="keep", why="abstain", solvers=[{"char": None}])])[0] is not R.GROUP_ABSTAIN


def test_group_detail_scene_and_form_open():
    c = Cell(id="v:1:1:1", char="傅", ref="傳", evidence={"group": {"id": "fc", "mode": "review", "decision": "demote",
                                                                  "why": "agree", "solvers": [{"char": "傅"}]}})
    assert detail_of(R.GROUP_DEMOTED, c) == "fc:review"
    fo = Cell(id="v:1:1:1", char=None, ref="歲", doubts=["form_open"], evidence={"group": {"id": "sui", "solvers": []}})
    assert _cls([fo]) == [R.VARIANT_FORM_OPEN]
    from guji_manager.review.pending_reason import parse, specs
    assert parse("group_form_open") is R.VARIANT_FORM_OPEN and specs()[R.VARIANT_FORM_OPEN].code == "V02"
    assert specs()[R.GROUP_UNCONFIRMED].code == "Z07"


def test_group_settled_is_not_weak():
    """字组已放／保持／暂归一的格还在待审，是后面的闸拦的：不落 Z05，按后面的原因落（A24 Z05 深挖 11-06）。"""
    g = lambda dec, why="agree", **k: Cell(id="v:1:1:1", char="宫", ref="宮", evidence={"group": {
        "id": "guan", "decision": dec, "why": why, "solvers": [{"char": "宫"}]}}, **k)
    # 影子闸 shadow_veto → L05 乱码闸
    assert _cls([g("admit", doubts=["shadow_veto"])]) == [R.GARBLE_GATE]
    # 其余：字组放了字、整理本是另一写法，库认不出等后面的原因
    assert _cls([g("keep")])[0] is not R.GROUP_ABSTAIN
    assert _cls([g("provisional")])[0] is not R.GROUP_ABSTAIN
    # 复核降审、没定字的照旧
    assert _cls([g("demote")]) == [R.GROUP_DEMOTED]
    assert _cls([g("review", why="weak")]) == [R.GROUP_UNCONFIRMED]   # Z07（11-07）
    # 整理本缺位（ref_missing／solo_weak）不是字组的事，落后面的原因
    ref_gap = lambda why: Cell(id="v:1:1:1", char="宫", ref=None, evidence={"group": {
        "id": "guan", "decision": "review", "why": why, "solvers": [{"char": "宫"}]}})
    assert R.GROUP_ABSTAIN not in _cls([ref_gap("ref_missing")]) and R.GROUP_ABSTAIN not in _cls([ref_gap("solo_weak")])


def test_lib_and_ref_rules():
    lib = {"乙": 1, "甲": 50}.get
    lib_n = lambda ch: lib(ch) or 0
    cells = [
        Cell(id="v:1:1:1", char="甲", ref="〓"),
        Cell(id="v:1:1:2", char="甲", ref="丙", doubts=["库里没有这个字"]),
        Cell(id="v:1:1:3", char="甲", ref="甲", doubts=["ctx_garble_shape"]),
        Cell(id="v:1:1:4", char="乙", ref="乙"),
        Cell(id="v:1:1:5", char="甲", ref="乙"),
        Cell(id="v:1:1:6", char="丁", ref="甲", ref_op="replace"),
        Cell(id="v:1:1:7", char="丁", ref="甲"),
        Cell(id="v:1:1:8", char="丁", ref="甲", evidence={"guard": "conflict"}),
    ]
    assert _cls(cells, lib=lib_n) == [R.REF_LACUNA, R.LIB_MISSING, R.GARBLE_GATE, R.LIB_SPARSE_DISSENT,
                                      R.LIB_SPARSE_DISSENT, R.REF_OCR_DIFF, R.REF_FINAL_DIFF, R.NEAR_FORM_GUARD]


def test_sparse_needs_lib_counts():
    """没给库样本数就不判「刻例太少」，不猜。"""
    assert _cls([Cell(id="v:1:1:1", char="乙", ref="乙")]) == [R.LIB_UNRECOGNIZED]


def test_variant_pair():
    var = lambda a, b: {a, b} == {"衞", "衛"}
    c = Cell(id="v:1:1:1", char="衞", ref="衛", cands=[["衞", 0.9]])
    assert _cls([c], lib=lambda ch: 50, var=var) == [R.VARIANT_PAIR]


def _page(tmp_path, book, page, chars, align=None, gm=None):
    root = tmp_path / book
    for layer, body in (("seed_admit", {"columns": [{"chars": chars}]}), ("align_ref", align or {"chars": []}),
                        ("glyph_match", gm or {"columns": []})):
        (root / layer).mkdir(parents=True, exist_ok=True)
        (root / layer / f"p{page:04d}.json").write_text(json.dumps({layer: body}), encoding="utf-8")


def test_reasons_for_pending_and_stamp(tmp_path):
    _page(tmp_path, "vol9", 1,
          [{"id": "vol9:1:1:1", "admit": False, "char": "甲", "doubts": ["occluded"], "evidence": {}},
           {"id": "vol9:1:1:2", "admit": True, "char": "乙"}],
          align={"chars": [{"id": "vol9:1:1:1", "align_char": "甲", "align_op": "equal"}]})
    doc = {"cells": [{"cell": "1:1:1", "why": ["occluded"]},
                     {"cell": "7:7:7", "why": [], "recheck": True, "note": "机器改判「□」→「甲」，推翻人裁，请核"},
                     {"cell": "8:8:8", "why": []}]}
    res = reasons_for_pending(doc, tmp_path, "vol9", are_variants=lambda a, b: False)
    n = stamp(doc, res)
    got = {c["cell"]: c["pending_reason"] for c in doc["cells"]}
    assert got == {"1:1:1": "occluded_with_ref", "7:7:7": "machine_changed", "8:8:8": "ref_gap"}
    assert sum(n.values()) == 3
    assert all("pending_reason" in c for c in doc["cells"])


def test_seg_kind_detail():
    """切坏细分作 seg_defect 的 detail（SJ 第 8 轮，11-04）：单上 seg_kind 优先，其次 evidence；不认的值不带。"""
    from guji_manager.review.reasons import detail_of
    ctx = build_context([])
    a = Cell(id="v:1:1:1", char="甲", doubts=["seg_defect"], seg_kind="merged")
    b = Cell(id="v:1:1:2", char="乙", doubts=["seg_defect"], evidence={"seg_kind": "frame_residue"})
    c = Cell(id="v:1:1:3", char="丙", doubts=["seg_defect"], seg_kind="bogus")
    for x in (a, b, c):
        assert classify(x, ctx) is R.SEG_DEFECT
    assert [detail_of(R.SEG_DEFECT, x) for x in (a, b, c)] == ["merged", "frame_residue", ""]


def test_seg_kind_from_pending_list(tmp_path):
    doc = {"cells": [{"cell": "1:1:1", "why": ["seg_defect"], "seg_kind": "clipped"}]}
    res = reasons_for_pending(doc, tmp_path, "vol9", are_variants=lambda a, b: False)
    assert res["1:1:1"] == (R.SEG_DEFECT, "clipped")


def test_seg_selfcheck_src(tmp_path):
    """出单同字对照自检放上单的已放行格（单上 src=seg_selfcheck，B1③）：原因 seg_defect，detail 带固定前缀；
    产物里这格的 doubts 没有 seg_defect 也照样归它。没有 src 的格（只带 seg_kind 当证据）不改原因。"""
    doc = {"cells": [{"cell": "1:1:1", "seg_kind": "clipped", "src": "seg_selfcheck"},
                     {"cell": "1:1:2", "seg_kind": "frame_residue", "ref": {"c": "甲"}}]}
    res = reasons_for_pending(doc, tmp_path, "vol9", are_variants=lambda a, b: False)
    assert res["1:1:1"] == (R.SEG_DEFECT, "同字对照自检：clipped")
    assert res["1:1:2"][0] is not R.SEG_DEFECT


def test_jiazhu_uneven_is_seg_defect():
    """史記夹注两行分法不均（doubt 码 jiazhu_uneven，cv#1011）归 seg_defect，细分 jiazhu_uneven。"""
    from guji_manager.review.reasons import detail_of
    c = Cell(id="v:1:2:3a", char="甲", ref="甲", doubts=["jiazhu_uneven"])
    assert _cls([c]) == [R.SEG_DEFECT]
    assert detail_of(R.SEG_DEFECT, c) == "jiazhu_uneven"
    c2 = Cell(id="v:1:2:4", char="甲", ref="甲", evidence={"seg_kind": "jiazhu_uneven"}, doubts=["seg_defect"])
    assert detail_of(R.SEG_DEFECT, c2) == "jiazhu_uneven"


def test_lib_missing_detail_split():
    """lib_missing 细分（A23，11-04）：整理本无字／本书借库都没有／借库有本书没有／本书已有，写成「细分:字」。"""
    from guji_manager.review.reasons import detail_of, lib_missing_kind
    split = {"以": (0, 40), "松": (0, 0), "人": (12, 30)}
    ctx = build_context([], lib_split=lambda ch: split.get(ch, (0, 0)))
    cells = {"以": Cell(id="v:1:1:1", char="取", ref="以", doubts=["库里没有这个字"]),
             "松": Cell(id="v:1:1:2", char="林", ref="松", doubts=["库里没有这个字"]),
             "人": Cell(id="v:1:1:3", char="入", ref="人", doubts=["库里没有这个字"]),
             "∅": Cell(id="v:1:1:4", char="和", ref=None, doubts=["库里没有这个字"])}
    for k, c in cells.items():
        # 11-07：整理本这一位没字（ref_blank）不是「库里没有它」，不归 L01，落 R02；没给 lib_own 时其余仍按 5a 判 diff 归 L01
        assert classify(c, ctx) is (R.REF_GAP if k == "∅" else R.LIB_MISSING)
    assert {k: detail_of(R.LIB_MISSING, c, ctx) for k, c in cells.items()} == {
        "以": "own_zero_borrow_has:以", "松": "all_zero:松", "人": "own_has:人", "∅": "ref_blank:"}
    no_lib = build_context([])
    assert detail_of(R.LIB_MISSING, cells["以"], no_lib) == "以"          # 没给库不分，照旧只写整理本字
    assert detail_of(R.LIB_MISSING, cells["以"]) == "以"
    assert lib_missing_kind(cells["∅"], no_lib) == "ref_blank"


def test_lib_split_counts_own_vs_borrowed(tmp_path):
    import random
    import sqlite3

    import cv2

    from open_guji_cv.clustering.glyph_db import GlyphDB
    from open_guji_cv.clustering.synth import degrade, synthetic_glyph
    from guji_manager.review.reasons import lib_split_counts

    def png(seed):
        g = degrade(synthetic_glyph(random.Random(700 + seed)), random.Random(seed), wear=0.3)
        return cv2.imencode(".png", 255 - (g * 255).astype("uint8"))[1].tobytes()
    p = tmp_path / "g.db"
    db = GlyphDB(p)
    try:
        for i, (iid, ch) in enumerate([("o:1", "以"), ("b:1", "以"), ("b:2", "以"), ("b:3", "人")]):
            db.admit_instance(iid, ch, png(i), provenance="human", edition_tag="ted", page="1", col=i, idx=1)
        db.conn.commit()
    finally:
        db.close()
    with sqlite3.connect(p) as c:
        c.execute("CREATE TABLE borrowed (instance_id TEXT PRIMARY KEY, store TEXT)")
        c.executemany("INSERT INTO borrowed VALUES (?, 'x')", [("b:1",), ("b:2",), ("b:3",)])
    f = lib_split_counts(p)
    assert f("以") == (1, 2) and f("人") == (0, 1) and f("松") == (0, 0)
    assert lib_split_counts(tmp_path / "none.db") is None


def test_glyph_pending_only_for_registered_codes():
    """待收字：只有私用码表登记为「已判定待收」的码位才记 glyph_pending；没登记的仍是 ref_lacuna；detail 只写「来源:码位」。"""
    from guji_manager.review.reasons import build_context, classify, detail_of
    reg = {"siku-qiefen-v2:U+F1001"}
    a = Cell(id="v:1:1:1", char="丁", ref="〓", pua_code="siku-qiefen-v2:U+F1001")
    b = Cell(id="v:1:1:2", char="丁", ref="〓", pua_code="siku-qiefen-v2:U+F1002")
    c = Cell(id="v:1:1:3", char="丁", ref="〓", pua_code="daizhige:U+F1001")   # 同码位别的来源不算
    d = Cell(id="v:1:1:4", char="丁", ref="〓")
    ctx = build_context([a, b, c, d], glyph_pending=reg)
    assert [classify(x, ctx) for x in (a, b, c, d)] == [R.GLYPH_PENDING, R.REF_LACUNA, R.REF_LACUNA, R.REF_LACUNA]
    assert detail_of(R.GLYPH_PENDING, a, ctx) == "siku-qiefen-v2:U+F1001"
    assert classify(a, build_context([a])) is R.REF_LACUNA            # 没给登记表＝一个都不算
    s = R.GLYPH_PENDING.spec
    assert (s.code, s.route.value, s.reviewer.value, s.priority) == ("R03", "deferred", "none", 49)


def test_glyph_pending_flows_through_pending_sheet(tmp_path):
    """单上的 pua_code ＋ 登记表 → reasons_for_pending 记 glyph_pending；不给登记表仍是 ref_lacuna。"""
    from guji_manager.review.reasons import reasons_for_pending
    doc = {"cells": [{"cell": "bk:1:1:1:1", "ref": {"c": "〓"}, "pua_code": "daizhige:U+E123"},
                     {"cell": "bk:1:1:1:2", "ref": {"c": "〓"}, "pua_code": "daizhige:U+E124"}]}
    r = reasons_for_pending(doc, tmp_path, "bk", glyph_pending={"daizhige:U+E123"})
    assert r["bk:1:1:1:1"] == (R.GLYPH_PENDING, "daizhige:U+E123")
    assert r["bk:1:1:1:2"][0] is R.REF_LACUNA
    assert reasons_for_pending(doc, tmp_path, "bk")["bk:1:1:1:1"][0] is R.REF_LACUNA


def test_glyph_pending_resolved_from_ref_window(tmp_path):
    """出单时：整理本缺字格按前后文窗口回查私用码，码在登记表里记 glyph_pending；回查不到／没登记仍 ref_lacuna。"""
    import json as _j
    from guji_manager.review.reasons import reasons_for_pending
    book, pg = "bk", tmp_path / "bk"
    for d in ("seed_admit", "align_ref"):
        (pg / d).mkdir(parents=True)
    ids = [f"bk:1:1:{i}:{i}" for i in range(1, 9)]
    ids = [f"bk:1:1:{i}" for i in range(1, 9)]
    refs = list("天地玄〓黄宇宙洪")
    seed = {"seed_admit": {"columns": [{"chars": [{"id": i, "char": "丁", "admit": False, "doubts": []} for i in ids]}]}}
    align = {"align_ref": {"chars": [{"id": i, "align_char": c, "align_op": "equal"} for i, c in zip(ids, refs)]}}
    (pg / "seed_admit" / "p0001.json").write_text(_j.dumps(seed), encoding="utf-8")
    (pg / "align_ref" / "p0001.json").write_text(_j.dumps(align), encoding="utf-8")
    doc = {"cells": [{"cell": ids[3]}]}
    seen = []

    def resolve(left, right):
        seen.append((left, right))
        return "daizhige:U+EA96"
    from collections import Counter
    st = Counter()
    r = reasons_for_pending(doc, tmp_path, book, glyph_pending={"daizhige:U+EA96"}, pua_resolve=resolve, stats=st)
    assert st["glyph_pending_by_window"] == 1
    assert seen == [("天地玄", "黄宇宙洪")]
    assert r[ids[3]] == (R.GLYPH_PENDING, "daizhige:U+EA96")
    assert reasons_for_pending(doc, tmp_path, book, glyph_pending={"daizhige:U+EB10"}, pua_resolve=resolve)[ids[3]][0] is R.REF_LACUNA
    assert reasons_for_pending(doc, tmp_path, book, glyph_pending={"daizhige:U+EA96"}, pua_resolve=lambda a, b: None)[ids[3]][0] is R.REF_LACUNA
    assert reasons_for_pending(doc, tmp_path, book, glyph_pending=frozenset(), pua_resolve=resolve)[ids[3]][0] is R.REF_LACUNA


def test_pua_resolver_cached_per_corpus(tmp_path, monkeypatch):
    """同一语料目录只建一次索引（约 29 MB 源文件），不能每出一张单就读一遍。"""
    from guji_manager.review import reasons
    calls = []
    monkeypatch.setattr(reasons, "_build_resolver", lambda corpus: calls.append(corpus) or (lambda a, b: None))
    monkeypatch.setattr(reasons, "_RESOLVERS", {})
    a = reasons.pua_resolver(tmp_path)
    b = reasons.pua_resolver(tmp_path)
    assert a is b and len(calls) == 1
    reasons.pua_resolver(tmp_path / "other")
    assert len(calls) == 2


def test_load_glyph_pending_reads_config_pua(tmp_path):
    """登记表在数据目录 config/pua/；读不到或坏文件＝空表（全走 ref_lacuna）。"""
    from guji_manager.review.reasons import load_glyph_pending
    assert load_glyph_pending(tmp_path) == frozenset()
    d = tmp_path / "config" / "pua"
    d.mkdir(parents=True)
    (d / "glyph_pending_codes.json").write_text('{"codes": ["daizhige:U+EA96"]}', encoding="utf-8")
    assert load_glyph_pending(tmp_path) == frozenset({"daizhige:U+EA96"})
    (d / "glyph_pending_codes.json").write_text("{坏", encoding="utf-8")
    assert load_glyph_pending(tmp_path) == frozenset()


def test_registry_missing_is_reported_in_stats(monkeypatch):
    from collections import Counter
    import guji_manager.review.reasons as rs
    monkeypatch.setattr(rs, "load_glyph_pending", lambda *a, **k: frozenset())
    st = Counter()
    try:
        rs.reasons_for_pending({"cells": []}, "/nonexistent", "b", stats=st)
    except Exception:  # noqa: BLE001  空单子/路径不在都行，只看登记表缺失是否记了
        pass
    assert st["glyph_pending_registry_missing"] == 1


def test_align_for_seed_alt_cols():
    """史記 alt_cut：准入改用备选切法的列读 alt_draft 的坐标对位，现役对位字丢掉（02:106 第 6 列错一位）。"""
    from guji_manager.review.reasons import align_for_seed
    align = {"chars": [{"id": "v:1:6:1", "align_char": "赤"}, {"id": "v:1:5:1", "align_char": "甲"}],
             "coord": [{"id": "v:1:6:1", "ref_char": "赤"}],
             "alt_draft": {"coord": [{"id": "v:1:6:-1", "ref_char": "赤"}, {"id": "v:1:6:1", "ref_char": "埴"},
                                     {"id": "v:1:5:1", "ref_char": "乙"}]}}
    got = align_for_seed({"alt_cols": [6]}, align)
    assert [c["id"] for c in got["chars"]] == ["v:1:5:1"]
    assert {c["id"]: c["ref_char"] for c in got["coord"]} == {"v:1:6:-1": "赤", "v:1:6:1": "埴"}
    assert align_for_seed({}, align) is align


def test_load_pua_table_reads_config_pua(tmp_path):
    """码表在数据目录 config/pua/pua_table.jsonl；不在＝空表，坏行跳过；只报数，不改判法。"""
    from guji_manager.review.reasons import load_pua_table, pua_table_stats
    assert load_pua_table(tmp_path) == {}
    d = tmp_path / "config" / "pua"
    d.mkdir(parents=True)
    (d / "pua_table.jsonl").write_text(
        '{"code": "daizhige:U+EA96", "verdict": "pending"}\n{坏\n'
        '{"code": "daizhige:U+EAA0", "verdict": "char", "char": "卿"}\n{"verdict": "open"}\n', encoding="utf-8")
    t = load_pua_table(tmp_path)
    assert set(t) == {"daizhige:U+EA96", "daizhige:U+EAA0"} and t["daizhige:U+EAA0"]["char"] == "卿"
    st = pua_table_stats(t, frozenset({"daizhige:U+EA96", "daizhige:U+EAA0"}))
    assert st["pua_table_codes"] == 2 and st["pua_table_pending"] == 1 and st["pua_table_char"] == 1
    assert st["pua_table_registry_mismatch"] == 1
    assert pua_table_stats({}, frozenset({"x"}))["pua_table_registry_mismatch"] == 0


def test_renamed_reason_old_names_still_parse():
    from guji_manager.review.pending_reason import PendingReason, parse
    assert parse("ref_replaced") is PendingReason.REF_OCR_DIFF
    assert parse("ref_mismatch") is PendingReason.REF_FINAL_DIFF
    assert parse("ref_ocr_diff") is PendingReason.REF_OCR_DIFF


def test_hard_pair_same_char_in_jys_or_top2():
    """Z01 深挖（A24 11-06）：参校字＝机器字＝首位同是己已巳日曰之一时，字组 jys/ry 或库前两名都在组内 → H01，不落 Z01。"""
    g = {"id": "jys", "solvers": [], "why": "abstain"}
    a = Cell(id="v:1:1:1", char="已", ref="已", cands=[["已", 0.97], ["己", 0.96]], evidence={"group": g})
    b = Cell(id="v:1:2:1", char="已", ref="已", cands=[["已", 0.97], ["乙", 0.5]], evidence={"group": {**g, "id": "zz"}})
    c = Cell(id="v:1:3:1", char="日", ref="日", cands=[["日", 0.97], ["曰", 0.96]], evidence={"group": {**g, "id": "zz"}})
    assert _cls([a]) == [R.HARD_PAIR]
    assert _cls([b]) == [R.GROUP_ABSTAIN]
    assert _cls([c]) == [R.HARD_PAIR]


def test_s01_skips_lacuna_and_nonbody():
    """S01 深挖（A22 11-06）：〓 不算页无对位（同列一支）；非正文页（page_kind）不判 S01。"""
    lac = [Cell(id=f"v:7:1:{i}", char="甲", ref="〓") for i in range(12)]
    assert R.SEG_PAGE_UNALIGNED not in set(_cls(lac))
    noref = [Cell(id=f"v:8:{i % 3 + 1}:{i}", char="甲", ref=None) for i in range(12)]
    assert R.SEG_PAGE_UNALIGNED in set(_cls(noref))
    roster = [Cell(id=f"v:9:{i % 3 + 1}:{i}", char="甲", ref=None, page_kind="roster") for i in range(12)]
    assert R.SEG_PAGE_UNALIGNED not in set(_cls(roster))


def test_near_form_narrowed(monkeypatch):
    """N01 收窄（A24 11-06）：疑问码 near_form 只因家族字碰巧在候选里，不算形近护栏；参校字与机器字／候选前三成表内对才算。"""
    from guji_manager.review import reasons as rs
    monkeypatch.setattr(rs, "_NEAR_PAIRS", frozenset({("圓", "圖"), ("侯", "候")}))
    lib_n = lambda ch: 50
    cells = [
        # 家族字「圖」陪衬，参校字「愒」不成对 → 落 ref_final_diff
        Cell(id="v:1:1:1", char="闡", ref="愒", doubts=["near_form"], cands=[["闡", .96], ["圖", .95]]),
        # 改字层 → ref_ocr_diff
        Cell(id="v:1:1:2", char="面", ref="凶", ref_op="replace", doubts=["near_form"], cands=[["面", .95]]),
        # 参校字「圓」与候选第二「圖」成表内对 → 形近
        Cell(id="v:1:1:3", char="闡", ref="圓", doubts=["near_form"], cands=[["闡", .96], ["圖", .95]]),
        # 参校字与机器字成表内对 → 形近
        Cell(id="v:1:1:4", char="侯", ref="候", cands=[["侯", .99]]),
        # 表内对在候选第四 → 不算
        Cell(id="v:1:1:5", char="甲", ref="圓", cands=[["甲", .9], ["乙", .8], ["丙", .7], ["圖", .6]]),
    ]
    assert _cls(cells, lib=lib_n) == [R.REF_FINAL_DIFF, R.REF_OCR_DIFF, R.NEAR_FORM_GUARD,
                                      R.NEAR_FORM_GUARD, R.REF_FINAL_DIFF]
    # 刻例 ≤2 → lib_sparse_dissent
    assert _cls([cells[0]], lib=lambda ch: 1) == [R.LIB_SPARSE_DISSENT]


def test_ref_suspect_unit():
    """ref_suspect（A32 D01 11-06）：只比库首位与整理本字在整理本上下文里的相邻二字次数，整理本这一格自己不算。"""
    from collections import Counter
    from guji_manager.review.reasons import ref_suspect
    bg = Counter({"之曰": 1, "曰子": 1, "之日": 5, "日子": 3})
    # 整理本「曰」只有自己这一处 → 库首位「日」更通顺 → 疑整理本错
    a = Cell(id="v:1:1:1", char="日", ref="曰", cands=[["日", .99]], ref_left="…之", ref_right="子…")
    assert ref_suspect(a, bg) == "ref"
    # 反过来：整理本「日」常见、库首位「曰」少见 → 疑库错
    b = Cell(id="v:1:1:2", char="曰", ref="日", cands=[["曰", .99]], ref_left="之", ref_right="子")
    assert ref_suspect(b, bg) == "lib"
    # 库首位＝整理本、没上下文、没语料 → 不标
    assert ref_suspect(Cell(id="v:1:1:3", char="日", ref="日", cands=[["日", .9]], ref_left="之"), bg) == ""
    assert ref_suspect(Cell(id="v:1:1:4", char="日", ref="曰", cands=[["日", .9]]), bg) == ""
    assert ref_suspect(a, Counter()) == ""


def test_ref_suspect_stamped_on_pending(tmp_path):
    """reasons_for_pending 顺手在单上写 ref_suspect，不改原因；分不出的格把旧值删掉。"""
    from collections import Counter
    chars = [{"id": f"vol9:1:1:{i}", "admit": True, "char": ch} for i, ch in enumerate("子曰學而時習之子曰", 1)]
    chars[1] = {"id": "vol9:1:1:2", "admit": False, "char": "日", "doubts": []}
    chars += [{"id": f"vol9:1:2:{i}", "admit": True, "char": ch} for i, ch in enumerate("子曰有朋", 1)]
    align = {"chars": [{"id": c["id"], "align_char": ch, "align_op": "equal"}
                       for c, ch in zip(chars, "子日學而時習之子曰子曰有朋")]}
    gm = {"columns": [{"chars": [{"id": "vol9:1:1:2", "candidates": [["曰", .99], ["日", .9]]}]}]}
    _page(tmp_path, "vol9", 1, chars, align=align, gm=gm)
    doc = {"cells": [{"cell": "1:1:2", "why": []}, {"cell": "8:8:8", "why": [], "ref_suspect": "lib"}]}
    st = Counter()
    res = reasons_for_pending(doc, tmp_path, "vol9", are_variants=lambda a, b: False, stats=st)
    assert doc["cells"][0]["ref_suspect"] == "ref"         # 整理本「子日學」，全册「子曰」3 次 → 疑整理本错
    assert "ref_suspect" not in doc["cells"][1]
    assert st["ref_suspect_ref"] == 1
    doc2 = {"cells": [{"cell": "1:1:2", "why": []}]}
    res2 = reasons_for_pending(doc2, tmp_path, "vol9", are_variants=lambda a, b: False, suspect=False)
    assert "ref_suspect" not in doc2["cells"][0]
    assert res2["1:1:2"] == res["1:1:2"]                     # 原因不受标记影响


def test_sparse_zero_goes_lib_missing():
    """L02／L03 里参校字库里 0 例的都归 L01（L02 深挖 #258；L03 深挖，sheldon 11-06）；1～2 例照旧；前面的原因不受影响。"""
    lib_n = {"乙": 1, "丁": 2, "甲": 50}.get
    n = lambda ch: lib_n(ch) or 0
    cells = [
        Cell(id="v:1:1:1", char="甲", ref="丙", ref_op="coord"),     # 不同、0 例 → L01（原先 L02）
        Cell(id="v:1:1:2", char="丙", ref="丙", ref_op="coord"),     # 相同、0 例 → L01（原先 L03）
        Cell(id="v:1:1:3", char="甲", ref="乙"),                     # 1 例 → L02
        Cell(id="v:1:1:4", char="丁", ref="丁"),                     # 2 例 → L02（L03 11-07 停用并入）
        Cell(id="v:1:1:5", char="甲", ref="丙", doubts=["ctx_garble_shape"]),   # 乱码闸先判，不动
    ]
    assert _cls(cells, lib=n) == [R.LIB_MISSING, R.LIB_MISSING, R.LIB_SPARSE_DISSENT, R.LIB_SPARSE_DISSENT, R.GARBLE_GATE]
    from guji_manager.review.reasons import build_context, detail_of
    ctx = build_context(cells, lib_n=n, lib_split=lambda ch: (n(ch), 0))
    assert detail_of(R.LIB_MISSING, cells[0], ctx) == "all_zero:丙"
    assert detail_of(R.LIB_MISSING, cells[1], ctx) == "all_zero:丙"


def test_lib_boundary_table():
    """L01–L04 边界表（A23 L03 深挖，sheldon 11-06）：本书刻例 n × 机器字是否＝参校字。"""
    for n, same, want in [(0, True, R.LIB_MISSING), (0, False, R.LIB_MISSING),
                          (1, True, R.LIB_SPARSE_DISSENT), (1, False, R.LIB_SPARSE_DISSENT),
                          (2, True, R.LIB_SPARSE_DISSENT), (2, False, R.LIB_SPARSE_DISSENT),
                          (3, True, R.LIB_UNRECOGNIZED), (3, False, R.REF_FINAL_DIFF)]:
        c = Cell(id="v:1:1:1", char="丙" if same else "甲", ref="丙")
        ctx = build_context([c], lib_own=lambda ch, n=n: n if ch == "丙" else 50)
        assert classify(c, ctx) == want, (n, same)
    # 带 lib_miss 码（5a 判 diff）：本书 0 例仍 L01；1～2 例 L02；≥3 例的印糊整字有乱码闸码落 L05、否则 L04（细分 lib_diff）（11-07）
    def lm(n, char="丙", doubts=("lib_miss",), ref="丙"):
        c = Cell(id="v:1:1:1", char=char, ref=ref, doubts=list(doubts), cands=[[char, 0.8]])
        return c, build_context([c], lib_own=lambda ch: n)
    assert classify(*lm(0)) == R.LIB_MISSING
    assert classify(*lm(2)) == R.LIB_SPARSE_DISSENT
    assert classify(*lm(9)) == R.LIB_UNRECOGNIZED
    assert classify(*lm(9, char="甲", doubts=("lib_miss", "ctx_garble_shape"))) == R.GARBLE_GATE
    from guji_manager.review.reasons import lib_unrecognized_kind
    c, ctx = lm(9, char="甲")
    assert lib_unrecognized_kind(c, ctx) == "lib_diff" and detail_of(R.LIB_UNRECOGNIZED, c, ctx) == "lib_diff:丙"
    # lib_diff 且带 boundary_ink 旗（溢墨）→ 归切分 S04 bleed（A22 判据，A24 11-08）；不带旗照旧 L04
    cb = Cell(id="v:1:1:1", char="甲", ref="丙", doubts=["lib_miss"], cands=[["甲", 0.8]], bleed=True)
    ctxb = build_context([cb], lib_own=lambda ch: 9)
    assert classify(cb, ctxb) == R.SEG_DEFECT and detail_of(R.SEG_DEFECT, cb, ctxb) == "bleed"
    cb0 = Cell(id="v:1:1:1", char="甲", ref="丙", doubts=["lib_miss"], cands=[["甲", 0.8]], bleed=True)
    assert classify(cb0, build_context([cb0], lib_own=lambda ch: 0)) == R.LIB_MISSING     # 本书 0 例仍 L01，不动
    # 整理本这位没字：不归 L01，落 R02
    assert classify(*lm(9, ref=None)) == R.REF_GAP
    assert classify(*lm(0, ref=None)) == R.REF_GAP
    # 旧人裁锚点漂移（L04 human_unbound）改归 X01
    h = Cell(id="v:1:1:1", char="乾", ref="乾", doubts=["human_unbound"], cands=[["乾", 0.99]],
             evidence={"human_unbound": {"char": "所"}})
    assert classify(h, build_context([h], lib_own=lambda ch: 9)) == R.RULING_CONFLICT
    assert detail_of(R.RULING_CONFLICT, h) == "human_unbound:所>乾"
    # 没给库：L01–L03 都不按刻例判
    c = Cell(id="v:1:1:1", char="丙", ref="丙")
    assert classify(c, build_context([c])) == R.LIB_UNRECOGNIZED


def test_lib_count_own_book_only(tmp_path):
    """刻例只算本书版本：借来的刻例不让少刻例字逃出 L02／L03（史記借全唐文）；没给 lib_own 时退回老口径 lib_n。"""
    import sqlite3
    from guji_manager.review.reasons import lib_counts, lib_own_counts
    c = Cell(id="v:1:1:1", char="牘", ref="牘")
    assert classify(c, build_context([c], lib_n=lambda ch: 4, lib_own=lambda ch: 1)) == R.LIB_SPARSE_DISSENT
    assert classify(c, build_context([c], lib_n=lambda ch: 4, lib_own=lambda ch: 0)) == R.LIB_MISSING
    assert classify(c, build_context([c], lib_n=lambda ch: 4)) == R.LIB_UNRECOGNIZED      # 老口径 4 例 → 不算少
    db = tmp_path / "g.db"
    con = sqlite3.connect(db)
    con.execute("create table meta (key text primary key, value text)")
    con.execute("create table glyphs (edition_tag text, char text, n_confirmed int)")
    con.execute("insert into meta values ('book_edition', 'sj')")
    con.executemany("insert into glyphs values (?,?,?)", [("sj", "牘", 1), ("qtw", "牘", 3), ("qtw", "一", 20)])
    con.commit(); con.close()
    own, allv = lib_own_counts(db), lib_counts(db)
    assert (own("牘"), own("一"), allv("牘")) == (1, 0, 4)
    assert lib_own_counts(tmp_path / "missing.db") is None


def test_variant_pair_narrowed():
    """V01 收窄（A24 11-06）：只看库首位／机器字与整理本的边；给了边分型只认 T1、T2。"""
    var = lambda a, b: {a, b} in ({"衞", "衛"}, {"職", "軄"}, {"畫", "晝"})
    tier = {frozenset("衞衛"): "T1", frozenset("職軄"): "T1", frozenset("畫晝"): "T3"}
    et = lambda a, b: tier.get(frozenset((a, b)))
    cells = [
        Cell(id="v:1:1:1", char="衞", ref="衛", cands=[["衞", .9]]),                     # 首位有 T1 边 → V01
        Cell(id="v:1:1:2", char="甲", ref="職", cands=[["甲", .9], ["軄", .8]]),         # 边只在陪衬候选 → 不算
        Cell(id="v:1:1:3", char="晝", ref="畫", cands=[["晝", .9]]),                     # T3 → 不算
    ]
    ctx = build_context(cells, lib_n=lambda ch: 50, are_variants=var, edge_tier=et)
    assert [classify(c, ctx) for c in cells] == [R.VARIANT_PAIR, R.REF_FINAL_DIFF, R.REF_FINAL_DIFF]
    # 不给分型（旧 cv）：T3 也照旧算
    ctx2 = build_context(cells, lib_n=lambda ch: 50, are_variants=var)
    assert classify(cells[2], ctx2) is R.VARIANT_PAIR

def test_lib_unrecognized_kind_detail():
    """L04 细分（A23 11-06）：按 ref_lib_coord 逐关看哪一关没过。"""
    from guji_manager.review.reasons import detail_of, lib_unrecognized_kind
    mk = lambda **kw: Cell(id="v:1:1:1", char="全", ref="全", **kw)
    cases = {
        "lib_other": mk(cands=[["今", 0.988], ["全", 0.969]], doubts=["ctx_guard_ref"]),
        "human_unbound": mk(cands=[["全", 0.97]], doubts=["human_unbound"], evidence={"human_unbound": {"char": "所"}}),
        "doubt_blocked": mk(cands=[["全", 0.97]], doubts=["库 unsure(cov=0.970)", "coord_conflict"]),
        "low_cov": mk(cands=[["全", 0.95]], doubts=["库 unsure(cov=0.950)"]),
        "near_rival": mk(cands=[["全", 0.97], ["仝", 0.965]]),
        "clear": mk(cands=[["全", 0.97], ["今", 0.93]], doubts=["库 unsure(cov=0.970)", "上下文 margin 不足(0.02)", "context_page_end"]),
    }
    assert {k: lib_unrecognized_kind(c) for k, c in cases.items()} == {k: k for k in cases}
    # 人裁绑丢但旧裁字就是本格字：不拦（ref_lib_coord 也放）
    assert lib_unrecognized_kind(mk(cands=[["全", 0.97]], doubts=["human_unbound"], evidence={"human_unbound": {"char": "全"}})) == "clear"
    assert lib_unrecognized_kind(mk()) == "lib_other"                        # 没有库候选
    assert detail_of(R.LIB_UNRECOGNIZED, cases["low_cov"]) == "low_cov:全"
    # 紧咬的是参校字的异体：给了异体判断就不算 near_rival
    from guji_manager.review.reasons import Context
    av = Context(are_variants=lambda a, b: {a, b} == {"全", "仝"})
    assert lib_unrecognized_kind(cases["near_rival"], av) == "clear"


def test_fragment_cell_without_ref_is_seg_defect():
    """整理本这位没字、格框又比本页同类格小得多的碎片格归 S04（细分 clipped，R02 深挖 11-06）；有整理本字的不算。"""
    from guji_manager.review.reasons import detail_of
    c = Cell(id="v:1:2:3", char="一", ref=None, frag=True)
    assert _cls([c]) == [R.SEG_DEFECT]
    assert detail_of(R.SEG_DEFECT, c) == "clipped"
    assert _cls([Cell(id="v:1:2:4", char="一", ref="六", frag=True)]) != [R.SEG_DEFECT]
    assert _cls([Cell(id="v:1:2:5", char="一", ref=None, frag=False)]) == [R.REF_GAP]


def test_frag_ids_from_cell_shrink(monkeypatch, tmp_path):
    """格框边长 <0.6 倍本页同类格中位数、或长宽比 <0.35 算碎片；夹注与正文分开比；同类格不足 5 个不判。"""
    from guji_manager.review import reasons

    def box(i, w, h, jz=False):
        return {"id": f"v:1:1:{i}", "width": w, "height": h, "step3_kind": "jiazhu" if jz else "char"}
    chars = [box(i, 80, 80) for i in range(8)] + [box(8, 30, 30), box(9, 80, 20), box(10, 20, 20, True)]
    monkeypatch.setattr(reasons, "_load_layer", lambda *a, **k: {"columns": [{"chars": chars}]})
    assert reasons._frag_ids(tmp_path, "p001.json") == {"v:1:1:8", "v:1:1:9"}   # 夹注只 1 个，不判

def test_group_same_form_not_conflict():
    """A24 Z02 11-06：解法只差写法（同字异形）不算判法打架；真异字照旧。"""
    g = lambda a, b, **k: Cell(id="v:1:1:1", char=a, ref=b, evidence={"group": {"id": "xz", "solvers": [{"char": a}, {"char": b}], **k}})
    var = lambda a, b: {a, b} == {"象", "𧰼"}
    assert _cls([g("象", "𧰼", why="conflict")], var=var) == [R.GROUP_ABSTAIN]  # Z05 已停用，落 Z01
    assert _cls([g("象", "𧰼", decision="demote")], var=var) == [R.GROUP_DEMOTED]
    assert _cls([g("傅", "傳", why="conflict")], var=var) == [R.GROUP_CONFLICT]
    assert _cls([g("象", "𧰼", why="conflict")]) == [R.GROUP_CONFLICT]  # 没给 are_variants 不折叠
def test_group_fold_uses_same_writing_not_wide_variants():
    """A24 Z03 11-07：折叠用同一个字的写法（same_writing），异体表里的大／太、傳／傅 不折，落 Z02。"""
    g = lambda a, b, **k: Cell(id="v:1:1:1", char=a, ref=a, evidence={"group": {"id": "dt", "solvers": [{"char": a}, {"char": b}], **k}})
    wide = lambda a, b: {a, b} == {"大", "太"} or {a, b} == {"象", "𧰼"}
    same = lambda a, b: {a, b} == {"象", "𧰼"}
    cells = [g("太", "大", decision="demote"), g("象", "𧰼", decision="demote")]
    assert _cls(cells, var=wide) == [R.GROUP_DEMOTED, R.GROUP_DEMOTED]          # 只给宽表：大太被折成一个字（旧行为）
    ctx = build_context(cells, are_variants=wide, same_writing=same)
    assert [classify(c, ctx) for c in cells] == [R.GROUP_CONFLICT, R.GROUP_DEMOTED]


def test_garble_gate_needs_ref():
    """L05 要有整理本字；无对位的糊格（框线碎片、并格、圈点）落 R02（A24 L05 深挖 11-06）。"""
    cells = [
        Cell(id="v:1:1:1", char="甲", ref="乙", doubts=["ctx_garble_shape"]),
        Cell(id="v:1:1:2", char="甲", ref=None, doubts=["ctx_garble_shape"]),
        Cell(id="v:1:1:3", char="甲", ref=None, doubts=["shadow_veto"]),
    ]
    assert _cls(cells) == [R.GARBLE_GATE, R.REF_GAP, R.REF_GAP]


def test_private_use_ref_is_lacuna():
    """整理本这位是私用码（史記）也算参校本缺字 R01，detail 写码位；基本区字不受影响（A24 R01 核实，11-07）。"""
    from guji_manager.review.reasons import ref_missing
    assert ref_missing("") and ref_missing("\U000f0001") and ref_missing("〓") and not ref_missing("纏")
    c = Cell(id="01:1:1:1:1", char="墟", ref="")
    assert classify(c, build_context([c], lib_own=lambda ch: 0)) == R.REF_LACUNA
    assert detail_of(R.REF_LACUNA, c) == "U+EDC1"
    assert detail_of(R.REF_LACUNA, Cell(id="v:1:1:2", ref="〓")) == ""


def test_ref_by_design_not_seg_or_ref_gap():
    """本页本就没配参校本（全唐文 001–003 故意不带）：不判 S01／S02／R02，落 L04（细分 no_ref）；库 unsure 带 lib_miss 的细分 lib_diff。"""
    page = [Cell(id=f"v:8:{i % 3 + 1}:{i}", char="甲", ref=None, ref_by_design=True) for i in range(12)]
    ctx = build_context(page)
    assert set(classify(c, ctx) for c in page) == {R.LIB_UNRECOGNIZED}
    assert detail_of(R.LIB_UNRECOGNIZED, page[0], ctx) == "no_ref:"
    miss = Cell(id="v:8:1:30", char="甲", ref=None, ref_by_design=True, doubts=["lib_miss"])
    assert classify(miss, build_context([miss])) is R.LIB_UNRECOGNIZED
    assert detail_of(R.LIB_UNRECOGNIZED, miss, None) == "lib_diff:"
    # 对照：没标设计的同样 12 格仍是整页对不上
    plain = [Cell(id=f"v:9:{i % 3 + 1}:{i}", char="甲", ref=None) for i in range(12)]
    assert set(_cls(plain)) == {R.SEG_PAGE_UNALIGNED}


def test_noref_notes_include_unreadable(tmp_path):
    """align_ref 备注「整理本读不到」（册里没写 references）算本就没参照。"""
    import json
    from guji_manager.review.reasons import _ref_by_design
    d = tmp_path / "align_ref"
    d.mkdir()
    for name, note, want in (("p1.json", "整理本读不到", True), ("p2.json", "8-gram 锚定失败", False)):
        (d / name).write_text(json.dumps({"align_ref": {"note": note}}), encoding="utf-8")
        assert _ref_by_design(tmp_path, name) is want
