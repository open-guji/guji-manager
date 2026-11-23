"""GUJI-776：按主键排的字形表（glyph_instances）中间插行时不推「只是行号变了」，还原按主键排回。"""
from __future__ import annotations

import json

from guji_manager.datastore.importer import diff, fingerprint, key_sorted_paths
from guji_manager.datastore.materialize import _texts
from guji_manager.datastore.scope import TABLES, scan_files, sha256

P = "output/glyph_store/instances/v2.jsonl"


def _inst(i: str) -> str:
    return json.dumps({"instance_id": i, "source_id": "v2", "label": "師"}, ensure_ascii=False, sort_keys=True)


def _rows(ids):
    body = ("\n".join(_inst(i) for i in ids) + "\n").encode()
    files = {"workspace.yaml": b"id: tws\n", P: body}
    rows = scan_files([(k, (lambda v=v: v)) for k, v in files.items()], "d").rows
    return [r for r in rows if r.tbl == "glyph_instances"], body


def test_insert_in_middle_is_not_a_move():
    assert TABLES["glyph_instances"].key_ordered
    old, _ = _rows(["a", "c", "e"])
    existing = {r.key: (fingerprint(r), r.src_line) for r in old}
    new, _ = _rows(["a", "b", "c", "d", "e"])
    plan = diff(new, existing, key_ordered=True)
    assert [r.key for r in plan.inserts] == [("b",), ("d",)] and plan.moves == []
    assert len(diff(new, existing).moves) == 2            # 老规矩：逐行记行号
    shuffled, _ = _rows(["c", "a", "b", "d", "e"])         # 没按主键排的文件照旧推行号
    assert key_sorted_paths(shuffled) == set()
    assert diff(shuffled, existing, key_ordered=True).moves


class _Src:
    def __init__(self, rows, body):
        self.lines = rows
        self.sf = {"src_path": P, "tbl": "glyph_instances", "sha256": sha256(body), "bytes": len(body),
                   "n_lines": body.count(b"\n"), "final_newline": True}

    def rows(self, tbl, ws, cols=None, **_):
        return [dict(r) for r in self.lines]


def test_materialize_rebuilds_key_ordered_file_from_stale_lines():
    # 库里：老三行行号没改（0,1,2），新插的 b、d 是新行号（1,3）——按行号拼会撞行，按主键排正好还原
    _, body = _rows(["a", "b", "c", "d", "e"])
    db = [{"src_path": P, "src_line": n, "raw": _inst(i), "instance_id": i}
          for i, n in (("a", 0), ("c", 1), ("e", 2), ("b", 1), ("d", 3))]
    src = _Src(db, body)
    texts, _, fetched, _ = _texts(src, "tws", {P: src.sf}, None)
    assert texts[P] == body and fetched == 1
