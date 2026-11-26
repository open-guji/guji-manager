# -*- coding: utf-8 -*-
"""待审原因 manual_cells_remapped（S05）：钉子按列图几何换算、位移 >3px 的列，格捞回待审。"""


def test_pending_reason_manual_cells_remapped():
    from guji_manager.review import reasons as R
    from guji_manager.review.pending_reason import PendingReason, specs
    c = R.Cell(id="b:5:3:1", char="之", ref="之", doubts=[R.PIN_REMAPPED_DOUBT])
    assert R.classify(c, R.build_context([c])) is PendingReason.MANUAL_CELLS_REMAPPED
    assert specs()[PendingReason.MANUAL_CELLS_REMAPPED].code == "S05"
    c2 = R.Cell(id="b:5:3:1", char="之", ref="之")
    assert R.classify(c2, R.build_context([c2])) is not PendingReason.MANUAL_CELLS_REMAPPED


def test_book_cells_pulls_remapped_column(tmp_path):
    import json
    from guji_manager.review.reasons import PIN_REMAPPED_DOUBT, book_cells
    root = tmp_path / "b"
    for step, kind, body in (
            ("seed_admit", "seed_admit", {"columns": [
                {"col": 3, "chars": [{"id": "b:5:3:1", "char": "之", "admit": True}]},
                {"col": 4, "chars": [{"id": "b:5:4:1", "char": "也", "admit": True}]}]}),
            ("row_segment", "cells", {"columns": [{"col": 3, "flags": ["manual_cells", PIN_REMAPPED_DOUBT]},
                                                  {"col": 4, "flags": []}]})):
        (root / step).mkdir(parents=True)
        (root / step / "p0005.json").write_text(json.dumps({kind: body}), encoding="utf-8")
    got = book_cells(tmp_path, "b")
    assert list(got) == ["5:3:1"] and PIN_REMAPPED_DOUBT in got["5:3:1"].doubts
