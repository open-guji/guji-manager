import json

from guji_manager.review.dian_trace import dian_for, load_notes, summarize_trace
from guji_manager.review.proof_fields import pending_fields

CANDS = ["日", "曰"]


def test_l2_mid_with_l3_evidence():
    tr = [
        {"level": "L1", "routes": {"A": ["日", "mid"], "B": ["曰", "high"]}},
        {"level": "L2", "char": "日", "conf": "mid", "why": "書名《日畿訪勝錄》"},
        {"level": "L3", "char": "日", "conf": "high", "status": "confirmed",
         "evidence": [{"url": "https://zh.wikipedia.org/wiki/x", "quote": "魏方泰字日乾", "source_kind": "wikipedia"},
                      {"url": "javascript:alert(1)", "quote": "bad"}]},
    ]
    d = summarize_trace(tr, CANDS)
    assert d["char"] == "日" and len(d["why"]) <= 400
    assert d["why"].startswith("L1 两路分歧(日/曰)")
    assert d["refs"] == [{"u": "https://zh.wikipedia.org/wiki/x", "t": "维基百科：魏方泰字日乾"}]


def test_out_of_candidates_gives_no_char():
    tr = [{"level": "L2", "char": "日", "conf": "low", "why": "疑為白"},
          {"level": "L3", "char": "白", "conf": "high", "status": "contradicts_L2",
           "evidence": [{"url": "https://zh.wikisource.org/x", "quote": "白鷗沒浩蕩", "source_kind": "other_book"}]}]
    d = summarize_trace(tr, CANDS)
    assert "char" not in d and "白" in d["why"] and d["refs"]


def test_refs_capped_and_why_truncated():
    ev = [{"url": f"https://e.com/{i}", "quote": "q" * 80} for i in range(9)]
    d = summarize_trace([{"level": "L3", "char": "日", "conf": "high", "why": "x" * 400, "evidence": ev}], CANDS)
    assert len(d["refs"]) == 5 and len(d["why"]) == 400 and all(len(r["t"]) <= 60 for r in d["refs"])


def test_empty_and_into_pending_fields(tmp_path):
    assert summarize_trace([], CANDS) is None
    f = tmp_path / "vol21.jsonl"
    row = {"group": "ry", "ctx": {"hash": "h1"}, "cell": "vol21:98:7:17", "cands": CANDS,
           "trace": [{"level": "L2", "char": "日", "conf": "mid", "why": "日月"}]}
    f.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    idx = load_notes(f)
    dian = dian_for(idx, cell="vol21:98:7:17", group="ry", ctx_hash="h1")
    out = pending_fields({"dian": dian})
    assert out["ctx"]["c"] == "日" and out["ctx"]["src"] == "punct_llm"
    assert dian_for(idx, cell="nope") is None


def test_find_by_u_and_long_why(tmp_path):
    p = tmp_path / "n.jsonl"
    p.write_text(json.dumps({"book": "vol11", "u": 7, "cell": "11:3:5:14a",
                             "trace": [{"level": "L3", "char": "已", "conf": "mid", "why": "甲" * 380}]}, ensure_ascii=False) + "\n",
                 encoding="utf-8")
    d = dian_for(load_notes(p), cell="x:y", book="vol11", u=7, cands=["已", "巳"])
    assert d["char"] == "已" and 300 < len(d["why"]) <= 400
