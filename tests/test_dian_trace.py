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


def test_ai_block_and_out_of_cands():
    tr = [{"level": "L3", "char": "己", "conf": "high", "status": "pending", "why": "文意自指，三家註卷24作己", "s": "倾向己·高；三家註同",
           "log": [{"src": "维基文库三家註卷024", "r": "同字", "t": "窗口8"}]}]
    d = summarize_trace(tr, ["已", "巳"], "pending")
    ai = d["ai"]
    assert ai["c"] == "己" and ai["st"] == "pending" and ai["out_of_cands"] and ai["log"][0]["r"] == "同字"
    assert pending_fields({"id": "x", "dian": d, "doubts": []})["ai"]["s"] == "倾向己·高；三家註同"


def test_released_list(tmp_path):
    from guji_manager.review.dian_trace import released_list
    rows = [{"book": "vol11", "u": 9, "cell": "11:1:1:1", "cands": ["已", "巳"],
             "trace": [{"level": "L3", "char": "已", "conf": "high", "status": "released", "why": "x", "s": "已·高"}]},
            {"book": "vol11", "u": 3, "cell": "11:1:1:2", "cands": ["日", "曰"],
             "trace": [{"level": "L3", "char": "曰", "conf": "high", "status": "released", "why": "y"}]},
            {"book": "vol11", "u": 5, "cell": "11:1:1:3", "trace": [{"level": "L3", "char": "己", "status": "pending"}]}]
    p = tmp_path / "n.jsonl"
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    idx = load_notes(p)
    out = released_list(idx)
    assert [x["u"] for x in out] == [3, 9] and out[1]["ai"]["st"] == "released" and out[1]["ai"]["s"] == "已·高"
    assert [x["u"] for x in released_list(idx, {"11:1:1:1"})] == [3]
    assert dian_for(idx, cell="x", book="vol11", u=9)["ai"]["st"] == "released"


def test_write_notes_row():
    import importlib.util, pathlib
    p = pathlib.Path(__file__).parent.parent / "tools/dianjiao/write_notes.py"
    sp = importlib.util.spec_from_file_location("wn", p); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    n = m.row_to_note({"册": "10", "u": "881", "格号": "10:98:7:5a", "AI判": "曰", "置信": "high", "状态": "pending",
                       "一句话": "倾向曰", "详情": "述贊曰", "检索": "三家註卷15|同字|窗口8 ; ctext|取不到|", "候选": "日/曰"}, "L3", "m", "b")
    assert n["trace"][0]["status"] == "pending" and n["trace"][0]["log"][1] == {"src": "ctext", "r": "取不到", "t": ""} and n["u"] == 881


def test_notes_keyed_by_vol_and_u_across_collisions(tmp_path):
    """u 是册内编号：别的册撞号的 u 不能挂到本册；册标签 037／37／vol35 视为同一册；老行没有 book 用文件名。"""
    import json
    from guji_manager.review import dian_trace as T
    f = tmp_path / "037.jsonl"
    rows = [
        {"book": "26", "u": 26933, "cell": "26:146:8:8a", "cands": ["甲"], "trace": [{"status": "released", "char": "字"}]},
        {"book": "38", "u": 26933, "cell": "38:114:1:8b", "cands": ["乙"], "trace": [{"status": "released", "char": "字"}]},
        {"u": 5, "cell": "037:1:1:1", "cands": ["丙"], "trace": []},
    ]
    f.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    idx = T.load_notes(f)
    assert T.find_note(idx, book="26", u=26933)["cands"] == ["甲"]
    assert T.find_note(idx, book="038", u=26933)["cands"] == ["乙"]
    assert T.find_note(idx, book="99", u=26933) is None
    assert T.find_note(idx, book="37", u=5)["cands"] == ["丙"]
    assert T.find_note(idx, book="vol37", u=5)["cands"] == ["丙"]
    rel = T.released_list(idx)
    assert [(r["book"], r["u"]) for r in rel] == [("26", 26933), ("38", 26933)]
