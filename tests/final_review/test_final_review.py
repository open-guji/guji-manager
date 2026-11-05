"""终审跨书流水线：选格、分批、门槛、金标、端到端（假产物包，不需要 cv）。"""
import json
from types import SimpleNamespace as NS

from guji_manager.final_review import core, pack
from guji_manager.final_review import __main__ as fr


def test_select_and_batches():
    rows = [{"vol": "020", "cell": "10:3:10", "pending_reason": "group_abstain", "key": "zy", "ref": "予"},
            {"vol": "020", "cell": "10:3:11a", "pending_reason": "group_abstain", "key": "zy"},
            {"vol": "020", "cell": "11:1:1", "pending_reason": "hard_pair"},
            {"vol": "021", "cell": "1:1:1", "pending_reason": "ref_mismatch", "ref": "x"}]
    sel, sk = core.select(rows)
    assert [(s["id"], s["cls"]) for s in sel] == [("vol20:10:3:10", "Z"), ("vol21:1:1:1", "P")]
    assert sk["a/b 半格（归 S）"] == 1 and sk["不属判读类：hard_pair"] == 1
    assert core.select(rows, classes={"P"})[0][0]["cls"] == "P"
    bt = core.batches([{"id": f"v:{i}", "cls": "Z"} for i in range(5)], size=2)
    assert [len(b) for b in bt["Z"]] == [2, 2, 1]


def _x(cands, cls="Z", group="zy", ref="予"):
    return {"cands": cands, "cls": cls, "group": group, "ref_char": ref}


def test_gate():
    hi = lambda c: {"char": c, "conf": "high"}   # noqa: E731
    x = _x({"予": ["参校本", "机器识别"]})
    assert core.gate(x, hi("予"), hi("予"), set()) == (True, "ok")
    assert core.gate(x, hi("予"), {"char": "予", "conf": "mid"}, set())[1] == "no_double_high"
    y = _x({"予": ["参校本"], "子": ["字形库前五(0.50)"]})
    assert core.gate(y, hi("子"), hi("子"), set())[1] == "over_ref_not_allowed"        # 越过参校本，组不在白名单
    assert core.gate(y, hi("子"), hi("子"), {"zy"})[1] == "weak_evidence"                # 在白名单但证据不够
    z = _x({"予": ["参校本"], "子": ["字形库前五(0.97)"]})
    assert core.gate(z, hi("子"), hi("子"), {"zy"})[0] is True
    n = _x({"予": ["参校本"], "子": ["字形库前五(0.97)"]}, cls="N", group=None)
    assert core.gate(n, hi("子"), hi("子"), {"zy"})[1] == "over_ref_not_allowed"          # N 类永不越过参校本


def _write(p, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False), encoding="utf-8")


def _fake_pkg(root):
    chars = [{"id": f"vol20:1:1:{i}", "slot": i, "sub": 0, "char": c, "admit": True} for i, c in enumerate("甲乙丙丁")]
    chars[2].update(char="子", admit=False, doubts=[])
    _write(root / "vol20/seed_admit/p0001.json", {"seed_admit": {"columns": [{"col": 1, "chars": chars}]}})
    _write(root / "vol20/align_ref/p0001.json", {"align_ref": {"anchored": True, "chars": [{"id": "vol20:1:1:2", "align_char": "予"}]}})
    _write(root / "vol20/glyph_match/p0001.json", {"glyph_match": {"columns": [{"chars": [
        {"id": "vol20:1:1:2", "candidates": [{"char": "予", "score": 0.97}, {"char": "子", "score": 0.5}]}]}]}})


def test_end_to_end_with_fake_pkg(tmp_path):
    pkg, out = tmp_path / "pkg", tmp_path / "w"
    _fake_pkg(pkg)
    cells = tmp_path / "cells.tsv"
    cells.write_text("vol\tcell\tpending_reason\tkey\tref\n020\t1:1:2\tgroup_abstain\tzy\t予\n", encoding="utf-8")
    sort_fn = lambda recs: sorted(recs, key=lambda r: r.slot)   # noqa: E731
    groups = {"zy": NS(members="予子")}
    inj = (sort_fn, groups, None, 2)
    a = NS(cells=cells, out=out, vols=None, classes=None, vol_fmt="vol{n}", pkg=pkg, width=None, size=350, book="测试书", _inject=inj)
    sel = fr.cmd_select(a)
    c = fr.cmd_build(a, sel)
    assert c[0]["left"] == "甲乙" and c[0]["right"] == "丁" and c[0]["cands"]["予"][0] == "参校本"
    sess = fr.cmd_batches(a, c)
    assert {s["name"] for s in sess} == {"A_Z_001", "B_Z_001"}
    assert fr.cmd_status(NS(out=out)) == 1                       # 还没回
    ans = [{"id": "vol20:1:1:2", "char": "予", "conf": "high", "why": "予也"}]
    _write(out / "out/A_Z_001.json", ans)
    _write(out / "out/B_Z_001.json", ans)
    assert fr.cmd_status(NS(out=out)) == 0
    gold = tmp_path / "gold.tsv"
    gold.write_text("id\tchar\nvol20:1:1:2\t予\n", encoding="utf-8")
    f = NS(out=out, pkg=pkg, whitelist="", gold=gold, glyph_db=None, min_score=0.95, min_sources=2, _inject=inj)
    r = fr.cmd_finalize(f)
    assert r["rows"][0]["admit_ok"] and r["gold"]["wrong"] == [] and r["rows"][0]["win"][0] == "甲乙"
    # 金标说是「子」→ 放错 → write 拒绝
    gold.write_text("id\tchar\nvol20:1:1:2\t子\n", encoding="utf-8")
    fr.cmd_finalize(f)
    assert fr.main(["write", "--out", str(out), "--ruling-dir", str(tmp_path / "r"), "--batch", "b"]) == 2


def test_ref_falls_back_to_cells_ref(tmp_path):
    pkg = tmp_path / "pkg"
    _fake_pkg(pkg)
    _write(pkg / "vol20/align_ref/p0001.json", {"align_ref": {"anchored": True, "chars": []}})   # 无 align_char
    sel = [{"id": "vol20:1:1:2", "cls": "N", "reason": "near_form_guard", "group": "", "ref": "予"}]
    c = pack.build_cells(pkg, sel, lambda recs: sorted(recs, key=lambda r: r.slot), {}, 2)
    assert c[0]["ref_char"] == "予" and "参校本" in c[0]["cands"]["予"][0]
