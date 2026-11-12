import json
from guji_manager.review_pages import cold_start as cs


def _pack(tmp_path, cell, scores):
    vol, page = cell.split(":")[:2]
    d = tmp_path / vol / "rare_candidates"; d.mkdir(parents=True, exist_ok=True)
    (d / f"p{int(page):04d}.json").write_text(json.dumps({"rare_candidates": {"columns": [{"chars": [
        {"id": cell, "candidates": [{"char": "x", "font": "emb", "score": s} for s in scores]}]}]}}))


def _row(cell, lib, top3, cov, n):
    return {"cell": cell, "参校本": lib, "库首位": lib, "cov": str(cov), "5b前三": top3, "库例数": str(n), "疑问": ""}


def test_split_hi_lo(tmp_path):
    _pack(tmp_path, "001:1:1:1", [0.95, 0.94])      # 领先 .01
    _pack(tmp_path, "001:2:1:2", [0.95, 0.90])      # 领先 .05
    _pack(tmp_path, "001:3:1:3", [0.95, 0.94])
    rows = [_row("001:1:1:1", "甲", "甲乙丙", 0.93, 3),   # 库＝5b、cov 够、有例 → 高
            _row("001:2:1:2", "乙", "丙甲乙", 0.93, 3),   # 5b 领先 .05 → 高
            _row("001:3:1:3", "甲", "甲乙丙", 0.93, 0),   # 库 0 例 → 低
            _row("001:4:1:4", "甲", "甲乙丙", 0.85, 3)]   # cov<.90 → 低
    hi, lo, st = cs.classify(rows, str(tmp_path / "{vol}"), "/c/{cell}.png", skip_chars="")
    assert [i["id"] for i in hi] == ["001:1:1:1", "001:2:1:2"]
    assert {i["id"] for i in lo} == {"001:3:1:3", "001:4:1:4"}
    assert hi[1]["pre"] == "丙" and hi[0]["cands"][0] == ["甲", "5b首位"]
    assert hi[0]["img"] == "/c/001_1_1_1.png"


def test_skip(tmp_path):
    rows = [_row("001:1:1:1", "木", "木", 0.95, 3), _row("001:2:1:2", "甲", "甲", 0.95, 3)]
    hi, lo, st = cs.classify(rows, str(tmp_path / "{vol}"), "/c/{cell}.png", {"001:2:1:2"}, "木")
    assert not hi and not lo and st["skip_cell"] == 1 and st["skip_char"] == 1


def test_cold_start_items_have_no_column_fields():
    """低把握页照原样（Sheldon 11-10）：cold-items 出的 items 不带整列图／邻列图／上下文。"""
    import inspect
    from guji_manager.review_pages import cold_start
    src = inspect.getsource(cold_start)
    assert "col_img" not in src and "nb_imgs" not in src and "column_images" not in src


def test_char_grid_embeds_font_subset(tmp_path):
    """char_grid 1.3：出页默认内嵌 Jigmo 子集（扩展 H 的 𲨹 也能显示）；没字体时页上改显码位。"""
    import pytest
    pytest.importorskip("fontTools"); pytest.importorskip("brotli")
    from guji_manager.review_pages import build as b
    if not b.auto_fonts():
        pytest.skip("no fonts")
    items = [{"id": "001:1:1:1", "pre": "\U00032A39", "cov": .95, "img": None, "n": 1}]
    out = tmp_path / "g.html"
    st = b.build("char_grid", items, "995ejelvk0", out, per_page=40)
    html = out.read_text(encoding="utf-8")
    assert "@font-face" in html and "GujiSub" in html
    assert st["bytes"] < 800_000
    assert "\\u32a39" not in html.lower()


def test_font_stack_system_first():
    """Sheldon 11-10：系统原字体（大陆标准字形）排在前，内嵌 Jigmo／I.Ming 子集只给缺字兜底。"""
    import pytest
    pytest.importorskip("fontTools")
    from guji_manager.review_pages import build as b
    fs = b.auto_fonts()
    if not fs:
        pytest.skip("no fonts")
    css, _ = b.font_subset_css({"c": "\U00032A39"}, fs)
    stack = css[css.index("--font-glyph:"):]
    assert stack.index("Songti SC") < stack.index("GujiSub")
