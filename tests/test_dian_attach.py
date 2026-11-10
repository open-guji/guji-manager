import json

from guji_manager.review.dian_attach import attach_dian
from guji_manager.review.dian_trace import load_notes

ROW = {"group": "ry", "ctx": {"hash": "h1"}, "cell": "vol21:98:7:17", "cands": ["日", "曰"],
       "trace": [{"level": "L1", "routes": {"A": ["日", "mid"], "B": ["日", "mid"]}},
                 {"level": "L2", "char": "日", "conf": "mid", "why": "日月"}]}


def test_attach_by_cell_and_hash(tmp_path):
    p = tmp_path / "n.jsonl"
    p.write_text(json.dumps(ROW, ensure_ascii=False) + "\n", encoding="utf-8")
    idx = load_notes(p)
    cards = [{"id": "vol21:98:7:17"}, {"id": "x", "group": "ry", "ctx_hash": "h1"}, {"id": "vol9:1:1:1"},
             {"id": "vol21:98:7:17", "dian": {"why": "keep"}}]
    out, n = attach_dian(cards, idx)
    assert n == 2 and out[0]["dian"]["char"] == "日" and out[1]["dian"]["char"] == "日"
    assert "dian" not in out[2] and out[3]["dian"] == {"why": "keep"}
