"""待审条目／单路径按数值认册号（11-27 册号位数统一：改号后旧 rev 001-r3 仍要找到 1.items.jsonl）。"""
from guji_manager.review.pending_items import items_path, sheet_path


def test_items_path_numeric_twin(tmp_path):
    d = tmp_path / "feedback" / "lists" / "pending" / "99k3i35yww"
    d.mkdir(parents=True)
    (d / "1.items.jsonl").write_text("", encoding="utf-8")
    assert items_path(tmp_path, "99k3i35yww", "001") == d / "1.items.jsonl"
    assert items_path(tmp_path, "99k3i35yww", "1") == d / "1.items.jsonl"
    assert items_path(tmp_path, "99k3i35yww", "002") == d / "002.items.jsonl"     # 不在就给字面
    assert items_path(tmp_path, "mai", "01").name == "01.items.jsonl"


def test_sheet_path_numeric_twin(tmp_path):
    d = tmp_path / "feedback" / "lists" / "proofing" / "x"
    d.mkdir(parents=True)
    (d / "01.pending.json").write_text("{}", encoding="utf-8")
    assert sheet_path(tmp_path, "x", "1") == d / "01.pending.json"
