import json
from guji_manager.review_pages import ctx2


def _pack(tmp_path):
    d = tmp_path / "07" / "seed_admit"; d.mkdir(parents=True, exist_ok=True)
    ch = lambda i, c, adm=False: {"id": i, "char": c, "admit": adm}
    col = {"chars": [ch("07:1:1:1", "講"), ch("07:1:1:2", "日"), ch("07:1:1:3", "官"), ch("07:1:1:4a", "曰"),
                     ch("07:1:1:5", "未", False), ch("07:1:1:6", "曰", True)]}
    (d / "p0001.json").write_text(json.dumps({"seed_admit": {"columns": [col]}}), encoding="utf-8")
    return str(tmp_path)


def test_collect_whole_pending_only(tmp_path):
    cells = ctx2.collect(_pack(tmp_path))
    assert [c["id"] for c in cells] == ["07:1:1:2"]          # 半格、放行格不收
    assert cells[0]["l"] == "講" and cells[0]["r"].startswith("官")
    assert len(ctx2.collect(_pack(tmp_path), include_admitted=True)) == 2


def test_prompt_order_and_decide(tmp_path):
    cells = ctx2.collect(_pack(tmp_path))
    assert "候选：日、曰" in ctx2.prompts(cells, False) and "候选：曰、日" in ctx2.prompts(cells, True)
    a = [{"n": 1, "ch": "日", "conf": "high"}]
    assert ctx2.decide(cells, a, a)[0]["char"] == "日"
    assert ctx2.decide(cells, a, [{"n": 1, "ch": "日", "conf": "low"}])[0]["char"] == "待审"
    assert ctx2.decide(cells, a, [{"n": 1, "ch": "曰", "conf": "high"}])[0]["char"] == "待审"
    st = ctx2.write(ctx2.decide(cells, a, a), str(tmp_path / "o"), "r41")
    assert st == {"cells": 1, "decided": 1, "pending": 0}
    assert json.loads((tmp_path / "o" / "import草案.jsonl").read_text(encoding="utf-8"))["group"] == "ry"


def test_two_rounds_must_agree(tmp_path):
    cells = ctx2.collect(_pack(tmp_path))
    h = [{"n": 1, "ch": "日", "conf": "high"}]
    lo = [{"n": 1, "ch": "日", "conf": "low"}]
    assert ctx2.decide_rounds(cells, [(h, h), (h, h)])[0]["char"] == "日"
    assert ctx2.decide_rounds(cells, [(h, h), (h, lo)])[0]["char"] == "待审"
    assert ctx2.decide_rounds(cells, [(h, h), ([{"n": 1, "ch": "曰", "conf": "high"}],) * 2])[0]["char"] == "待审"


def test_half_cell_context_follows_reading_order(tmp_path):
    d = tmp_path / "07" / "seed_admit"; d.mkdir(parents=True)
    ch = lambda i, c: {"id": i, "char": c, "admit": False}
    col = {"chars": [ch("07:1:1:1", "前"), ch("07:1:1:2a", "甲"), ch("07:1:1:2b", "乙"),
                     ch("07:1:1:3a", "日"), ch("07:1:1:3b", "丙"), ch("07:1:1:4", "後")]}
    (d / "p0001.json").write_text(json.dumps({"seed_admit": {"columns": [col]}}), encoding="utf-8")
    cells = ctx2.collect(str(tmp_path), half=True)
    assert [c["id"] for c in cells] == ["07:1:1:3a"]
    assert cells[0]["l"] == "前甲" and cells[0]["r"] == "乙丙後"   # a 行读完接 b 行
