"""审字卡候选并 5b 首位的异体族（family_cands.py）。"""
import json

import pytest

from guji_manager.review_pages import cold_start as cs
from guji_manager.review_pages import family_cands as fc
from guji_manager.review_pages.layering import BookParams, Cell, to_row

FAM = {"內": ["内", "𡗠", "納"], "步": ["歩", "歨"]}


def fam(ch):
    return FAM.get(ch, [])


def test_family_goes_right_after_top():
    out = fc.with_family([["步", "5b首位"], ["涉", "库首位"], ["少", "5b次选"]], "步", fam)
    assert out == [["步", "5b首位"], ["歩", fc.FAMILY_SRC], ["歨", fc.FAMILY_SRC], ["涉", "库首位"], ["少", "5b次选"]]


def test_member_already_listed_moves_into_block_and_keeps_source():
    out = fc.with_family([["步", "5b首位"], ["涉", "库首位"], ["歨", "参校本"]], "步", fam)
    assert out == [["步", "5b首位"], ["歨", fc.FAMILY_SRC + "、参校本"], ["歩", fc.FAMILY_SRC], ["涉", "库首位"]]
    assert len({c[0] for c in out}) == len(out)


def test_cap_12_counts_whole_block():
    big = lambda ch: [chr(0x4E00 + i) for i in range(30)]
    cands = [["步", "5b首位"], [chr(0x4E00 + 20), "参校本"], ["涉", "库首位"]]
    out = fc.with_family(cands, "步", big)
    block = [c for c in out if c[1].startswith(fc.FAMILY_SRC)]
    assert len(block) == fc.FAMILY_MAX == 12
    assert block[0] == [chr(0x4E00 + 20), fc.FAMILY_SRC + "、参校本"]      # 已在候选里的同族字优先占位
    assert [c[0] for c in block[1:]] == [chr(0x4E00 + i) for i in range(11)]
    assert out[-1] == ["涉", "库首位"] and len(out) == 14


def test_no_family_or_wrong_head_is_untouched():
    cands = [["甲", "5b首位"], ["乙", "库首位"]]
    assert fc.with_family(cands, "甲", fam) == cands                # 族为空
    assert fc.with_family(cands, "甲", None) == cands               # 关掉
    assert fc.with_family([["乙", "库首位"]], "步", fam) == [["乙", "库首位"]]   # 首位不是 5b 首位：不插


def test_family_of_orders_by_sources_and_vetoes_simplified(monkeypatch):
    class E:
        def __init__(self, rel, src):
            self.rel, self.src = rel, src

    class DB:
        def family(self, ch):
            return {"𡗠": [E("related", "charcomp:rt"), E("variant", "twedu")],
                    "内": [E("variant", "yitizi"), E("variant", "twedu"), E("variant", "zi:link")],
                    "納": [E("variant", "charcomp:rt")], "芮": [E("related", "charcomp:rt")]}

    from guji_manager import _cv
    monkeypatch.setitem(_cv._LOCAL, "hanzi_shared", ("review_pages.family_cands", "_test_db"))
    monkeypatch.setitem(_cv._LOCAL, "is_simplified", ("review_pages.family_cands", "_test_simp"))
    monkeypatch.setattr(fc, "_test_db", lambda: DB(), raising=False)
    monkeypatch.setattr(fc, "_test_simp", lambda c: c == "内", raising=False)
    assert fc.family_of("內") == ["𡗠", "納", "芮"]                  # 简体「内」否决；来源多的在前，异体先于部件对应
    assert fc.family_of("內", no_simplified=False) == ["内", "𡗠", "納", "芮"]
    assert fc.family_of("") == []


def test_family_of_without_relation_db_returns_empty(monkeypatch):
    from guji_manager import _cv

    def boom():
        raise RuntimeError("关系库没灌")
    monkeypatch.setitem(_cv._LOCAL, "hanzi_shared", ("review_pages.family_cands", "_test_db"))
    monkeypatch.setattr(fc, "_test_db", boom, raising=False)
    monkeypatch.setattr(fc, "_WARNED", False)
    with pytest.warns(RuntimeWarning, match="不并异体族"):
        assert fc.family_of("內") == []


def test_real_relation_db():
    """真关系库：內 的族里有 𡗠（异体字字典），简体「内」被否决；步 的族里有 歩。"""
    pytest.importorskip("open_guji_cv")
    try:
        from guji_manager._cv import hanzi_shared
        hanzi_shared().family("步")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"关系库不可用：{e!r}")
    assert "歩" in fc.family_of("步")
    assert "内" in fc.family_of("內", no_simplified=False)
    pytest.importorskip("opencc")
    assert "内" not in fc.family_of("內")


# ---- 冷启动低把握页 ----

def _pack(tmp_path, cell, scores):
    vol, page = cell.split(":")[:2]
    d = tmp_path / vol / "rare_candidates"; d.mkdir(parents=True, exist_ok=True)
    (d / f"p{int(page):04d}.json").write_text(json.dumps({"rare_candidates": {"columns": [{"chars": [
        {"id": cell, "candidates": [{"char": "x", "font": "emb", "score": s} for s in scores]}]}]}}))


def _row(cell, ref, lib, top3, cov, n):
    return {"cell": cell, "参校本": ref, "库首位": lib, "cov": str(cov), "5b前三": top3, "库例数": str(n), "疑问": ""}


def test_cold_start_low_gets_family_high_does_not(tmp_path):
    _pack(tmp_path, "001:1:1:1", [0.95, 0.94])
    _pack(tmp_path, "001:2:1:2", [0.95, 0.94])
    rows = [_row("001:1:1:1", "步", "步", "步涉少", 0.93, 3),          # 高把握：候选照旧
            _row("001:2:1:2", "歩", "涉", "步涉少", 0.85, 3)]          # 低把握：并族，参校本「歩」挪进族块
    hi, lo, _ = cs.classify(rows, str(tmp_path / "{vol}"), "/c/{cell}.png", family=fam)
    assert hi[0]["cands"] == [["步", "5b首位"], ["涉", "5b次选"], ["少", "5b次选"]]
    assert lo[0]["cands"] == [["步", "5b首位"], ["歩", "5b首位同族、参校本"], ["歨", "5b首位同族"],
                              ["涉", "库首位"], ["少", "5b次选"]]
    assert lo[0]["pre"] == "步"                                        # 预选字不变
    _, lo2, _ = cs.classify(rows, str(tmp_path / "{vol}"), "/c/{cell}.png", family=None)
    assert [c[0] for c in lo2[0]["cands"]] == ["步", "涉", "歩", "少"]


# ---- 分层出页（难认字／低把握／对位可疑） ----

def _cell(ref="步", lib="涉", cov=.95, n=4, emb=(("步", .96), ("涉", .95), ("少", .9))):
    return Cell("29:165:3:8", ref, lib, cov, n, list(emb))


def test_to_row_hard_and_low_get_family():
    bp = BookParams(ref_trust="very_high")
    hard = to_row(_cell(ref="", emb=(("內", .80), ("丙", .78))), bp, family=fam)      # 没有参校本 → 难认字
    assert hard["layer"] == "hard"
    assert hard["cands"][:5] == [["內", "5b"], ["内", "5b首位同族"], ["𡗠", "5b首位同族"], ["納", "5b首位同族"], ["丙", "5b"]]
    low = to_row(_cell(ref="歩", cov=.80, emb=(("步", .96), ("歩", .955), ("涉", .9))), bp, family=fam)
    assert low["layer"] == "low" and low["pre"] == "步"
    assert low["cands"] == [["步", "5b"], ["歩", "5b首位同族、5b"], ["歨", "5b首位同族"], ["涉", "5b"]]
    assert to_row(_cell(ref="", emb=(("內", .80),)), bp, family=None)["cands"] == [["內", "5b"], ["涉", "库候选"]]


def test_to_row_quick_and_high_untouched():
    bp = BookParams(ref_trust="very_high")
    q = to_row(_cell(lib="步"), bp, family=fam)
    assert q["layer"] == "quick" and all(not c[1].startswith("5b首位同族") for c in q["cands"])
    h = to_row(_cell(ref="涉", lib="步", emb=(("步", .96), ("涉", .92))), BookParams(ref_trust="medium"), family=fam)
    assert h["layer"] == "high" and all(not c[1].startswith("5b首位同族") for c in h["cands"])
