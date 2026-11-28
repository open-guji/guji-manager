import pytest
pytest.importorskip("open_guji_cv")



def test_vis_glyph_kind_is_inert():
    """cv 第三步 vis_glyph 事件（rulings/ 目录，按图指纹缓存）：不算钉、不要求 u、换图源闸不管。"""
    from guji_manager.feedback.levels import counts_as_pin
    from guji_manager.feedback.source_rebase import GATE_EXEMPT_KINDS
    from guji_manager.u_stamp import lacks_u
    assert not counts_as_pin({"kind": "vis_glyph", "actor": "model", "payload": {"source": "llm"}})
    assert "vis_glyph" in GATE_EXEMPT_KINDS
    assert lacks_u("vis_glyph", {"unit": "cell", "key": "b:1:1:1"}, {"cell": "b:1:1:1"}, lambda b: True) is None
