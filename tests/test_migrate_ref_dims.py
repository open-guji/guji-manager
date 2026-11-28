import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("mrd", Path(__file__).parents[1] / "scripts" / "migrate_ref_dims.py")
mrd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mrd)


def test_block_and_flow_only_add():
    src = """references:
  - file: qtw_kanripo_grid.txt
    quality: best
    line_is_column: true   # 注释留着
  - {file: maijing_wikisource.txt, quality: low, line_is_column: false}   # 尾注
iron_gate: true
"""
    out, n = mrd.migrate_text(src)
    assert n == 2
    assert "    line_is_column: true   # 注释留着\n    form: column\n    script: trad\n    accuracy: high\n" in out
    assert "{file: maijing_wikisource.txt, quality: low, line_is_column: false, form: text, accuracy: low}   # 尾注" in out
    assert out.endswith("iron_gate: true\n")
    again, n2 = mrd.migrate_text(out)
    assert n2 == 0 and again == out            # 写过的不再补


def test_unknown_file_only_form():
    out, n = mrd.migrate_text("references:\n  - file: x.txt\n    line_is_column: false\n")
    assert n == 1 and out.endswith("    form: text\n") and "accuracy" not in out
