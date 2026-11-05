"""新书体检信号（diagnose）：按 pending_reason 分布给方向。"""
from guji_manager import diagnose


def _r(reason, i, **kw):
    return {"vol": "001", "cell": f"{i % 3 + 1}:1:{i}", "pending_reason": reason, "conc": "零散", **kw}


def test_layout_borrowed_and_symbol():
    rows = [_r("seg_page_unaligned", i, conc="整页") for i in range(40)]
    rows += [_r("lib_missing", i, ref="以") for i in range(20)] + [_r("lib_missing", i, ref="懷") for i in range(2)]
    rows += [_r("ref_gap", i, top="○") for i in range(10)] + [_r("ref_gap", i, top="之") for i in range(2)]
    rows += [_r("hard_pair", i) for i in range(5)]
    sg = {d["sig"]: d for d in diagnose.signals(rows, lib_n=lambda ch: {"以": 300}.get(ch, 0))}
    assert sg["版式／切分为主"]["tier"] == "A–B"
    assert sg["借来的字形不像这本书"]["n"] == 22
    assert 'symbol_ref_blank: "○"' in sg["整理本空位、图上是符号"]["todo"]
    assert sg["其他极难形近"]["tier"] == "B"   # 11-05 起己已巳、日曰折叠，不再 C 档单列


def test_rare_chars_and_pairs():
    rows = [_r("lib_missing", i, ref=chr(0x4E00 + i)) for i in range(30)]
    rows += [_r("near_form_guard", i, ref="天", top="大") for i in range(10)]
    sg = {d["sig"]: d for d in diagnose.signals(rows)}
    assert "真生僻字多（第一次进库）" in sg
    assert "天/大 10" in sg["异体／形近字对多"]["why"]
    assert diagnose.is_symbol("○") and not diagnose.is_symbol("天")


def test_render_empty():
    assert "没有命中的信号" in "\n".join(diagnose.render([]))
