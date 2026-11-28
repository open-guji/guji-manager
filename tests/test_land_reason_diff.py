"""land：cv 收尾直写的送审原因 ↔ manager 反推的对账（过渡期，缺省仍取 manager）。"""
from guji_manager.land_enrich import cv_reason_snapshot, reason_diff, write_reason_diff


def test_snapshot_and_diff(tmp_path):
    cells = [{"cell": "1:1:1", "pending_reason": "ref_gap", "pending_reason_detail": "d", "form_src": "ref"},
             {"cell": "1:1:2", "pending_reason": None},                      # 旧产物／归别人的
             {"cell": "1:1:3", "pending_reason": "hard_pair"}]
    cv = cv_reason_snapshot(cells)
    assert set(cv) == {"1:1:1", "1:1:3"}
    mine = [{"cell": "1:1:1", "pending_reason": "ref_gap"}, {"cell": "1:1:2", "pending_reason": "seg_defect"},
            {"cell": "1:1:3", "pending_reason": "unknown"}]
    assert reason_diff(mine, cv) == [("1:1:3", "hard_pair", "unknown")]
    st = write_reason_diff(tmp_path / "x" / "d.tsv", "b", mine, cv)
    assert st == {"cv_written": 2, "differ": 1, "total": 3}
    assert "b:1:1:3\thard_pair\tunknown" in (tmp_path / "x" / "d.tsv").read_text(encoding="utf-8")
