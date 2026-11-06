"""机器改字抽检表：分档、统计、渲染、从 git 取旧字。"""

import json
import subprocess

from guji_manager import machine_audit as ma


def test_tier():
    av = lambda a, b: {a, b} == {"隱", "隠"}
    assert ma.tier("□", "已", "已", av) is None            # F 同整理本
    assert ma.tier("□", "隱", "隠", av) is None            # E 异体
    assert ma.tier("□", "已", "巳", av) == "A"
    assert ma.tier("己", "日", "曰", av) == "A"
    assert ma.tier("□", "入", "人", av) == "B"
    assert ma.tier("□", "撰", "𢰅", av) == "C"
    assert ma.tier("□", "直", None, av) == "D"
    assert ma.tier("□", "直", "〓", av) == "D"             # 整理本也缺字
    assert ma.tier("字", "", "字", av) == "C"              # 改成空，留着看


def test_audit_cells_counts_and_skips():
    old = {"1:1:1": "", "1:1:2": "", "1:1:3": "", "1:1:4": "甲", "1:1:5": "乙"}
    new = {"1:1:1": "已", "1:1:2": "入", "1:1:3": "人", "1:1:4": "甲", "1:1:5": "丙"}
    sig = {"1:1:1": {"ref": "巳", "channel": "group_flow", "prov": "match"},
           "1:1:2": {"ref": "人", "channel": "x", "prov": "match"},
           "1:1:3": {"ref": "人", "channel": "match_ref", "prov": "match"},
           "1:1:5": {"ref": "丁", "channel": "ctx", "prov": "human"}}
    r = ma.audit_cells("vol20", old, new, sig, None)
    assert [(x["cell"], x["tier"]) for x in r["rows"]] == [("1:1:1", "A"), ("1:1:2", "B")]
    assert (r["n_changed"], r["n_human"], r["n_same_ref"]) == (4, 1, 1)


def test_pack_signals_and_render(tmp_path):
    pk = tmp_path / "vol20"
    (pk / "seed_admit").mkdir(parents=True)
    (pk / "align_ref").mkdir()
    seed = {"seed_admit": {"columns": [{"chars": [{"id": "vol20:5:1:1", "char": "已", "admit": True,
                                                   "channel": "group_flow", "provenance": "match"}]}]}}
    align = {"align_ref": {"chars": [{"id": "vol20:5:1:1", "align_char": "巳", "align_op": "sub"}]}}
    (pk / "seed_admit" / "p0005.json").write_text(json.dumps(seed), encoding="utf-8")
    (pk / "align_ref" / "p0005.json").write_text(json.dumps(align), encoding="utf-8")
    sig = ma.pack_signals(tmp_path, "vol20")
    assert sig["5:1:1"] == {"ref": "巳", "char": "已", "channel": "group_flow", "prov": "match"}
    res = {"vol20": ma.audit_cells("vol20", {"5:1:1": ""}, {"5:1:1": "已"}, sig, None)}
    md = ma.render(res)
    assert "| vol20 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |" in md and "## A 档" in md and "vol20:5:1:1" in md
    assert ma.render_tsv(res).splitlines()[1].split("\t")[:3] == ["vol20", "5:1:1", "A"]
    p = ma.write_report(tmp_path, res, "t")
    assert p.exists() and p.with_suffix(".tsv").exists()


def test_old_char_from_git(tmp_path):
    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True,
                       capture_output=True)
    git("init", "-q")
    f = tmp_path / "Book" / "x.char.json"
    f.parent.mkdir()
    for v in ("a", "b"):
        f.write_text(json.dumps({"v": v}), encoding="utf-8")
        git("add", "-A")
        git("commit", "-qm", v)
    assert ma.old_char_from_git(tmp_path, f.relative_to(tmp_path)) == {"v": "a"}
    assert ma.old_char_from_git(tmp_path, "nope.json") is None
