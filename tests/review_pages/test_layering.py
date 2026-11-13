"""少见字人审分层规则（layering.py）。"""
import json

from guji_manager.review_pages.layering import BookParams, Cell, cells_from_pack, classify

VH = BookParams(ref_trust="very_high")


def cell(cid="29:165:3:8", ref="剄", lib="則", cov=.95, n=4, emb=(("剄", .966), ("到", .95), ("剉", .9))):
    return Cell(cid, ref, lib, cov, n, list(emb))


def test_quick_very_high():
    assert classify(cell(), VH) == ("quick", "ref_trust_very_high")
    # 參校本字排第二不算；格图不干净（库首位 cov < .90）不算
    assert classify(cell(emb=(("到", .96), ("剄", .95))), VH)[0] != "quick"
    assert classify(cell(cov=.85), VH)[0] != "quick"


def test_high_trust_needs_5b_top_eq_ref():
    bp = BookParams(ref_trust="high")
    assert classify(cell(), bp)[0] == "quick"
    assert classify(cell(emb=(("到", .96), ("剄", .95))), bp)[0] != "quick"
    assert classify(cell(emb=(("剄", .92), ("到", .91))), bp)[0] != "quick"


def test_medium_needs_three_way():
    bp = BookParams(ref_trust="medium")
    assert classify(cell(), bp)[0] != "quick"
    assert classify(cell(lib="剄"), bp)[0] == "quick"
    assert classify(cell(lib="剄", cov=.97), bp)[0] != "quick"


def test_none_never_quick():
    assert classify(cell(lib="剄"), BookParams(ref_trust="none"))[0] != "quick"


def test_context_chars_go_hard():
    for ch in "一二三己已巳日曰":
        assert classify(cell(ref=ch, emb=((ch, .97), ("x", .9))), VH) == ("hard", "context_char")


def test_no_ref_or_low_5b_go_hard():
    assert classify(cell(ref=""), VH) == ("hard", "no_ref")
    assert classify(cell(emb=(("剄", .85),)), VH) == ("hard", "5b_low")


def test_position_and_near_not_quick():
    assert classify(cell(cid="29:165:3:1"), VH)[0] != "quick"      # 列首
    assert classify(cell(cid="29:165:3:21"), VH)[0] != "quick"     # 列尾
    assert classify(cell(cid="29:165:3:8a"), VH)[0] != "quick"     # 小注
    assert classify(cell(ref="未", emb=(("未", .97), ("末", .96))), VH)[0] != "quick"
    bp = BookParams(ref_trust="very_high", near_pairs=frozenset({frozenset("剄到")}))
    assert classify(cell(), bp)[0] != "quick"


def test_align_suspect_when_ref_absent_from_5b():
    # 史記 36:67:6:16b：參校本「服」，圖上是「罪」→ 多半對位錯
    c = cell(ref="服", lib="服", emb=(("罪", .942), ("暃", .9), ("㠑", .89)))
    assert classify(c, VH) == ("align", "ref_not_in_5b_top3")
    assert classify(c, BookParams(ref_trust="medium"))[0] != "align"


def test_high_and_low():
    c = cell(cid="29:165:3:1", lib="剄", cov=.95)
    assert classify(c, VH) == ("high", "lib_eq_5b")
    c = cell(cid="29:165:3:1", lib="則", emb=(("剄", .966), ("到", .95)))
    assert classify(c, VH)[0] == "low"


def test_cells_from_pack(tmp_path):
    pk = tmp_path / "29"
    def w(step, doc):
        (pk / step).mkdir(parents=True)
        (pk / step / "p0165.json").write_text(json.dumps({step: doc}), encoding="utf-8")
    cid = "29:165:3:8"
    w("glyph_match", {"columns": [{"chars": [{"id": cid, "candidates": [["則", .95]]}]}]})
    w("rare_candidates", {"columns": [{"chars": [{"id": cid, "candidates": [
        {"char": "到", "score": .95, "font": "emb"}, {"char": "剄", "score": .966, "font": "emb"},
        {"char": "x", "score": .99, "font": "other"}]}]}]})
    w("align_ref", {"chars": [{"id": cid, "align_char": "剄"}]})
    [c] = cells_from_pack([cid, "29:165:3:9"], str(tmp_path / "{vol}"), {"則": 4})
    assert (c.ref, c.lib, c.lib_n, c.top) == ("剄", "則", 4, ["剄", "到"])
