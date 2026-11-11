"""库里逐行文件缺行（旧 push 同主键重复行后者覆盖，丢了前面的行；史記 anchors/04.jsonl，2026-11-10）：
缺省仍报 sha 不符，--repair-gaps 时按库里现有的行还原。"""
from __future__ import annotations

from hashlib import sha256

import pytest

from guji_manager.datastore.materialize import MaterializeError, _texts


class _Src:
    def __init__(self, lines):
        self.lines = lines                         # {src_line: raw}

    def rows(self, tbl, ws, cols=None, **filters):
        return iter([{"src_path": "feedback/anchors/04.jsonl", "src_line": i, "raw": r} for i, r in self.lines.items()])


def _files(n=5):
    full = "\n".join(f"L{i}" for i in range(n)) + "\n"
    return {"feedback/anchors/04.jsonl": {"tbl": "anchors", "sha256": sha256(full.encode()).hexdigest(),
                                          "bytes": len(full.encode()), "n_lines": n, "final_newline": True}}


def test_gap_raises_by_default():
    with pytest.raises(MaterializeError, match="sha 不符"):
        _texts(_Src({0: "L0", 1: "L1", 4: "L4"}), "ws", _files(), None)


def test_repair_gaps_rebuilds_from_present_lines():
    texts, _, _, repaired = _texts(_Src({0: "L0", 1: "L1", 4: "L4"}), "ws", _files(), None, repair_gaps=True)
    assert texts["feedback/anchors/04.jsonl"] == b"L0\nL1\nL4\n"
    assert repaired and "feedback/anchors/04.jsonl" in repaired[0]


def test_complete_file_not_marked_repaired():
    texts, _, _, repaired = _texts(_Src({i: f"L{i}" for i in range(5)}), "ws", _files(), None, repair_gaps=True)
    assert texts["feedback/anchors/04.jsonl"].decode().count("\n") == 5 and not repaired


def test_dup_key_problems_only_for_changed_files():
    from guji_manager.datastore.workcopy import dup_key_problems
    pr = ["feedback/anchors/04.jsonl:61: 主键 ('a',) 与第 58 行重复，后者覆盖",
          "feedback/anchors/05.jsonl:3: 主键 ('a',) 与第 1 行重复，后者覆盖",
          "x.png: 没有实例引用的刻例图，未入库"]
    got = dup_key_problems(pr, {"feedback/anchors/04.jsonl"})
    assert len(got) == 1 and "04.jsonl" in got[0]
