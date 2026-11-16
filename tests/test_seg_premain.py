from guji_manager import seg_premain as sp


def _col(chars):
    return {"char_index": {"columns": [{"col": 1, "chars": chars}]}}


def _c(slot, h, **kw):
    return {"slot": slot, "height": h, "cell_type": "char", "ink_ratio": 0.3, **kw}


def test_tall_and_inkblank_and_fewer():
    chars = [_c(i, 110) for i in range(1, 6)] + [_c(6, 230), {**_c(7, 60), "cell_type": "empty", "ink_ratio": 0.15}]
    hits = sp.scan_page(_col(chars), {"align_ref": {"coord_fallback": {"1": "格数少于整理本字数（16 < 17）"}}})
    kinds = sorted(h[1] for h in hits)
    assert kinds == ["FEWER", "INK_BLANK", "TALL"]


def test_clean_column_and_jiazhu_ignored():
    chars = [_c(i, 110) for i in range(1, 8)] + [_c(8, 240, step3_kind="jiazhu", sub="a")]
    assert sp.scan_page(_col(chars), None) == []


def test_allow(tmp_path):
    f = tmp_path / "a.tsv"
    f.write_text("vol01\t5\t*\t看过\n", encoding="utf-8")
    a = sp.load_allow(f)
    assert sp._allowed(a, "vol01", 5, 3) and not sp._allowed(a, "vol01", 6, 3)
