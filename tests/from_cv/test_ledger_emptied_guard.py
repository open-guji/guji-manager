"""字形库账本被本机空壳清空的护栏（2026-11-04 殿本事故）：纯函数，不连库。"""
from guji_manager.datastore.importer import emptied_ledger


def test_empty_local_against_big_ledger_refused():
    assert emptied_ledger("glyph_admissions", 22002, 0, 22002)
    assert emptied_ledger("glyphs", 3381, 10, 3371)


def test_rekey_rewrite_not_refused():
    # 改键重写：删得多、本地行数也跟着在（edition_tag 改书 ID 那种）
    assert not emptied_ledger("glyph_exemplars", 21928, 21928, 21928)


def test_small_eviction_not_refused():
    assert not emptied_ledger("glyph_exemplars", 21928, 21900, 28)


def test_small_or_other_tables_not_refused():
    assert not emptied_ledger("glyphs", 10, 0, 10)             # 小库不拦
    assert not emptied_ledger("glyph_pairs", 5000, 0, 5000)    # 非账本表不在此护栏


def test_shrink_over_5pct_refused_2026_11_10():
    # 史記 11-10：6,465 → 3,554（55%）旧门槛「一半」没拦住
    assert emptied_ledger("glyph_exemplars", 6465, 3554, 2911)
    assert emptied_ledger("glyph_instances", 6465, 6000, 465)         # 缩 7%
    assert not emptied_ledger("glyph_exemplars", 6465, 6300, 165)     # 缩 2.5%：正常驱逐
