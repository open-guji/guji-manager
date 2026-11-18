"""库文一致的分类与处置（`ops/lib_text_check.py`）。字体模板识别、写库、待审单要整套 cv 环境，不在这里测。"""
import sqlite3

import pytest

from guji_manager.ops import lib_text_check as LT

CANON = {"陝": "陜", "宼": "𡨥"}.get


def canon(c):
    return CANON(c, c)


def _lib(label, prov="auto", at="2026-11-10T00:00:00+00:00"):
    return {"label": label, "provenance": prov, "at": at, "via": ""}


def _cell(ch, channel="match_ref", admit=True, provenance=None):
    return {"char": ch, "channel": channel, "admit": admit, "provenance": provenance or channel}


PAGE_AT = {1: "2026-11-15T00:00:00+00:00"}


def _cats(lib, cells):
    return {r["key"]: r["cat"] for r in LT.classify(lib, cells, canon, PAGE_AT)}


def test_classify_same_char_and_codepoint_variants_are_ok():
    lib = {"001:1:1:1": _lib("之"), "001:1:1:2": _lib("陝", "human")}
    cells = {"001:1:1:1": _cell("之"), "001:1:1:2": _cell("陜", "human")}
    assert set(_cats(lib, cells).values()) == {"ok"}


def test_classify_each_kind_of_mismatch():
    lib = {
        "001:1:1:1": _lib("槩", "human", at="2026-11-18T06:37:28+00:00"),   # 库在产物之后改的
        "001:1:1:2": _lib("主"),                                            # 文本是人裁
        "001:1:1:3": _lib("輪", "human"),                                   # 库是人裁，文本机器放行了别的字
        "001:1:1:4": _lib("𡨥"),                                            # 两边机器
        "001:1:1:5": _lib("六"),                                            # 格没了
        "001:1:1:6": _lib("真"),                                            # 文本这一格在待审
    }
    cells = {
        "001:1:1:1": _cell("㮣"),
        "001:1:1:2": _cell("王", "human"),
        "001:1:1:3": _cell("上"),
        "001:1:1:4": _cell("寇", "witness3"),
        "001:1:1:6": _cell("眞", admit=False),
    }
    assert _cats(lib, cells) == {
        "001:1:1:1": "text_stale", "001:1:1:2": "follow_human", "001:1:1:3": "human_unapplied",
        "001:1:1:4": "machine", "001:1:1:5": "orphan", "001:1:1:6": "pending"}


def test_stale_needs_page_time_and_newer_library():
    lib = {"001:2:1:1": _lib("槩", "human", at="2026-11-18T06:37:28+00:00")}
    assert _cats(lib, {"001:2:1:1": _cell("㮣")}) == {"001:2:1:1": "human_unapplied"}   # 这一页没有写出时刻


def _row(cat, lib="𡨥", text="寇", prov="auto"):
    return {"key": "001:1:1:1", "cat": cat, "lib": lib, "text": text, "lib_prov": prov}


def test_decide_machine_conflict_by_template_top1():
    assert LT.decide(_row("machine"), canon, "寇") == "relabel_auto"      # 模板认成文本的字：库改标
    assert LT.decide(_row("machine"), canon, "宼") == "review"            # 模板认成库标（码位归一后）：文本可疑
    assert LT.decide(_row("machine"), canon, "冠") == "review"            # 都不是：也送人看，库例不撤
    assert LT.decide(_row("machine"), canon, None) == "report"            # 没识别结果：只报


def test_decide_other_kinds():
    assert LT.decide(_row("text_stale")) == "invalidate"
    assert LT.decide(_row("follow_human")) == "relabel"
    assert LT.decide(_row("follow_human", text="⿰木寸")) == "report"      # 文本不是单个汉字，改不了标
    assert LT.decide(_row("human_unapplied", prov="human")) == "review"
    assert LT.decide(_row("orphan")) == "evict"
    assert LT.decide(_row("orphan", prov="human")) == "report"            # 人裁刻例不自动撤
    assert LT.decide(_row("ok")) == LT.decide(_row("pending")) == "none"


def test_lib_rows_reads_one_book(tmp_path):
    p = tmp_path / "g.db"
    c = sqlite3.connect(p)
    c.executescript("""
        CREATE TABLE instances(instance_id TEXT PRIMARY KEY, label TEXT);
        CREATE TABLE admissions(instance_id TEXT, provenance TEXT, evidence TEXT, admitted_at TEXT);
        INSERT INTO instances VALUES ('v2:001:1:1:1','之'),('v2:002:1:1:1','乎'),('v2:001:1:1:2a','也');
        INSERT INTO admissions VALUES ('v2:001:1:1:1','human','{"via":"glyph_audit"}','2026-11-18T00:00:00+00:00'),
                                      ('v2:001:1:1:2a','auto','{"channel":"rare_ref"}','2026-11-17T00:00:00+00:00');
    """)
    c.commit()
    c.close()
    rows = LT.lib_rows(p, "001")
    assert set(rows) == {"001:1:1:1", "001:1:1:2a"}
    assert rows["001:1:1:1"] == {"label": "之", "provenance": "human", "at": "2026-11-18T00:00:00+00:00",
                                 "via": "glyph_audit"}
    assert rows["001:1:1:2a"]["via"] == "rare_ref"


@pytest.mark.parametrize("text,want", [("", "report"), ("glyph_lib:\n  text_check: apply\n", "apply"),
                                       ("glyph_lib:\n  text_check: false\n", None),
                                       ("glyph_lib:\n  text_check: report\n", "report")])
def test_config(tmp_path, text, want):
    (tmp_path / "workspace.yaml").write_text(text, encoding="utf-8")
    assert LT.config(tmp_path) == want


def test_config_rejects_unknown_value(tmp_path):
    (tmp_path / "workspace.yaml").write_text("glyph_lib:\n  text_check: maybe\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        LT.config(tmp_path)


def test_shifted_when_lib_label_is_the_neighbor_cell_char():
    """库标正是同列邻格的字：库图是旧切分的字块（史記卷首题署列、全唐文 輪／上）。排在人裁改标之前。"""
    lib = {"001:1:1:3": _lib("卷", "human"), "001:1:2:5a": _lib("校")}
    cells = {"001:1:1:3": _cell("記", "human"), "001:1:1:4": _cell("卷", "human"),
             "001:1:2:5a": _cell("勘"), "001:1:2:4a": _cell("校"), "001:1:2:5b": _cell("校")}
    rows = {r["key"]: r for r in LT.classify(lib, cells, canon, PAGE_AT)}
    assert rows["001:1:1:3"]["cat"] == rows["001:1:2:5a"]["cat"] == "shifted"
    assert LT.decide(rows["001:1:1:3"]) == "report"       # 人裁刻例不自动撤
    assert LT.decide(rows["001:1:2:5a"]) == "evict"       # 机器刻例撤掉，文本不动


def test_neighbors_keep_half_cell_side():
    assert LT._neighbors("001:1:2:5a") == ["001:1:2:4a", "001:1:2:6a"]
    assert LT._neighbors("001:1:2:1") == ["001:1:2:0", "001:1:2:2"]


def test_low_template_margin_goes_to_review_not_relabel():
    assert LT.decide(_row("machine"), canon, "寇", LT.MARGIN_MIN - 0.01) == "review"
    assert LT.decide(_row("machine"), canon, "寇", LT.MARGIN_MIN + 0.01) == "relabel_auto"


def test_page_time_prefers_manifest_ts_over_file_mtime(tmp_path):
    """取包会刷新文件时刻：页的计算时刻认 manifest 的 ts。"""
    import json
    d = tmp_path / "001" / "seed_admit"
    d.mkdir(parents=True)
    (d / "p0001.json").write_text(json.dumps({"seed_admit": {"page": 1, "columns": [
        {"col": 1, "chars": [{"id": "001:1:1:1", "char": "之", "admit": True}]}]}}), encoding="utf-8")
    (d / "_manifest.jsonl").write_text(json.dumps({"key": "p0001", "ts": 1700000000.0}) + "\n", encoding="utf-8")
    cells, page_at = LT._seed(tmp_path, "001")
    assert set(cells) == {"001:1:1:1"} and page_at[1].startswith("2023-11-14")
