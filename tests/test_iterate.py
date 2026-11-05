"""iterate：轮报告、金标、抽检台账、杠杆排序、冻结日历。全用自造小数据。"""
import json

from guji_manager.iterate import audit, freeze, gold, leverage, round_report
from guji_manager.iterate.common import binom_upper, required_sample, write_tsv

COLS = ["vol", "cell", "pending_reason", "big", "sub", "key", "owner", "fix", "conc", "cause", "kind", "ref", "top"]


def mk_round(d, cells, vols):
    d.mkdir(parents=True)
    rows = [dict(zip(COLS, ["", "", "", "", "", "", "", "", "", "", "body", "", ""])) | c for c in cells]
    write_tsv(d / "cells.tsv", COLS, rows)
    by = {}
    for r in rows:
        by.setdefault(r["vol"], 0)
        by[r["vol"]] += 1
    (d / "summary.json").write_text(json.dumps({"n": len(rows), "n_nonbody": 0, "vols": {
        v: {"n": by.get(v, 0), "cells": vols[v], "rev": "r", "cv": "0.6"} for v in vols}}), encoding="utf-8")


def test_round_report(tmp_path):
    prev = [{"vol": "020", "cell": f"1:1:{i}", "pending_reason": "group_abstain"} for i in range(1, 6)]
    cur = prev[:3] + [{"vol": "020", "cell": "9:9:9", "pending_reason": "hard_pair"}]
    mk_round(tmp_path / "p", prev, {"020": 1000})
    mk_round(tmp_path / "c", cur, {"020": 1000})
    res = round_report.compare(tmp_path / "c", tmp_path / "p")
    assert (res["prev_n"], res["n"], len(res["regress"]), res["fixed_n"], res["sep"], res["net"]) == (5, 4, 1, 2, 1, 3)
    assert res["red"]   # 回退 1/5=20% ≥5%
    assert round_report.main(["--cur", str(tmp_path / "c"), "--prev", str(tmp_path / "p"), "--out", str(tmp_path / "o")]) == 2
    assert "回退清单" in (tmp_path / "o" / "report.md").read_text(encoding="utf-8")


def test_notify_and_closing(tmp_path):
    prev = [{"vol": "020", "cell": "1:1:1", "pending_reason": "hard_pair"}, {"vol": "021", "cell": "1:1:1", "pending_reason": "lib_missing"}]
    mk_round(tmp_path / "p", prev, {"020": 100, "021": 100})
    mk_round(tmp_path / "c", prev, {"020": 100, "021": 100})
    out = tmp_path / "o"
    round_report.main(["--cur", str(tmp_path / "c"), "--prev", str(tmp_path / "p"), "--label", "r5", "--round-kind", "S", "--out", str(out)])
    msg = (out / "notify_A33.txt").read_text(encoding="utf-8")
    assert msg.startswith("【A31→A33】S轮 r5 出口") and "020" in msg and "格号:不变" in msg
    rep = (out / "report.md").read_text(encoding="utf-8")
    assert "点校待办" in rep


def test_binom_and_sample():
    assert 0.09 < binom_upper(30, 0) < 0.11
    assert [required_sample(x) for x in (20, 99, 150, 301, 1001)] == [20, 30, 60, 100, 200]


def test_gold_flow(tmp_path):
    f = tmp_path / "a.tsv"
    write_tsv(f, ["cell_id", "label"], [{"cell_id": f"20:1:1:{i}", "label": "以"} for i in range(1, 31)])
    root = tmp_path / "gold"
    assert gold.main(["add", "--root", str(root), "--book", "sj", "--cls", "x", "--file", str(f)]) == 0
    (root / "sj" / "_index.yaml").write_text("- {name: 5a, kind: 5a, path: p, version: v1, frozen_at: 2026-11-05, owner: A23, used_for: 门槛}\n", encoding="utf-8")
    assert gold.main(["validate", "--root", str(root)]) == 0
    rel = tmp_path / "rel.tsv"
    write_tsv(rel, ["vol", "cell", "char"], [{"vol": "020", "cell": f"1:1:{i}", "char": "以"} for i in range(1, 31)])
    assert gold.main(["eval", "--root", str(root), "--book", "sj", "--cls", "x", "--released", str(rel)]) == 0
    write_tsv(rel, ["vol", "cell", "char"], [{"vol": "020", "cell": f"1:1:{i}", "char": "已" if i == 1 else "以"} for i in range(1, 31)])
    assert gold.main(["eval", "--root", str(root), "--book", "sj", "--cls", "x", "--released", str(rel)]) == 2
    write_tsv(f, ["cell_id", "label"], [{"cell_id": "20:1:1:1", "label": "已"}])
    assert gold.main(["add", "--root", str(root), "--book", "sj", "--cls", "x", "--file", str(f)]) == 1   # 冲突不覆盖


def test_gold_non_char_label_counts_wrong():
    g = {("020", "1:1:1"): {"label": "@unreadable", "ctx_hash": ""}}
    e = gold.evaluate(g, [{"vol": "020", "cell": "1:1:1", "char": "以"}], "x")
    assert len(e["wrong"]) == 1


def test_gold_stale_ctx_hash():
    g = {("020", "1:1:1"): {"label": "以", "ctx_hash": "a"}}
    e = gold.evaluate(g, [{"vol": "020", "cell": "1:1:1", "char": "以", "ctx_hash": "b"}], "x")
    assert e["stale"] == 1 and e["n_gold_hit"] == 0


def test_gold_validate_rejects_bad():
    assert gold.validate_rows([{"cell_id": "1:1:1:1", "label": "以已"}, {"cell_id": "2:1", "label": "a"}])


def test_audit(tmp_path):
    rel = tmp_path / "rel.tsv"
    write_tsv(rel, ["vol", "cell", "char"], [{"vol": "1", "cell": f"1:1:{i}", "char": "a"} for i in range(1, 41)])
    out = tmp_path / "s.tsv"
    root = tmp_path / "audit"
    audit.main(["sample", "--root", str(root), "--book", "b", "--round", "r1", "--cls", "L2:z", "--released", str(rel), "--out", str(out)])
    from guji_manager.iterate.common import read_tsv
    picked = read_tsv(out)
    assert len(picked) == 30
    res = tmp_path / "res.tsv"
    write_tsv(res, ["vol", "cell", "verdict"], [{"vol": r["vol"], "cell": r["cell"], "verdict": "ok"} for r in picked])
    assert audit.main(["add", "--root", str(root), "--book", "b", "--round", "r1", "--cls", "L2:z", "--results", str(res)]) == 0
    assert audit.main(["summary", "--root", str(root), "--book", "b"]) == 0
    audit.main(["sample", "--root", str(root), "--book", "b", "--round", "r2", "--cls", "L2:z", "--released", str(rel), "--out", str(out)])
    assert len(read_tsv(out)) == 10   # 前 30 个不再抽
    write_tsv(res, ["vol", "cell", "verdict"], [{"vol": "001", "cell": "1:1:99", "verdict": "bad"}])
    audit.main(["add", "--root", str(root), "--book", "b", "--round", "r2", "--cls", "L2:z", "--results", str(res)])
    assert audit.main(["summary", "--root", str(root), "--book", "b"]) == 2


def test_leverage(tmp_path):
    cells = [{"vol": "005", "cell": f"1:1:{i}", "pending_reason": "group_abstain", "ref": "以", "top": "已"} for i in range(1, 6)]
    cells += [{"vol": "005", "cell": "2:1:1", "pending_reason": "lib_missing", "ref": "人", "top": ""}]
    cells += [{"vol": "005", "cell": "3:1:1", "pending_reason": "hard_pair", "ref": "日", "top": "曰"}] * 9
    cards, rows = leverage.rank(cells)
    assert cards[0]["reason"] == "lib_missing"           # 第一次进库排最前，哪怕只有 1 格
    assert cards[1]["reason"] == "group_abstain" and cards[1]["n_cells"] == 5
    assert cards[-1]["reason"] == "hard_pair" and cards[-1]["tier"] == 2
    assert len(rows) == 15


def test_freeze(tmp_path):
    f = tmp_path / "cal.yaml"
    freeze.main(["add", "--file", str(f), "--book", "dianben", "--from", "2026-11-05 10:00", "--to", "2026-11-05 20:00"])
    fr = freeze.load(f)
    at = freeze.parse_t("2026-11-05 12:00")
    assert "A33" in fr[0]["notify"]
    assert freeze.conflicts(fr, ["dianben"], ["row_segment"], at)
    assert not freeze.conflicts(fr, ["dianben"], ["seed_admit"], at)      # D 轮不冻结
    assert not freeze.conflicts(fr, ["shiji"], ["row_segment"], at)
    assert not freeze.conflicts(fr, ["dianben"], ["row_segment"], freeze.parse_t("2026-11-06 09:00"))
    assert freeze.main(["check", "--file", str(f), "--books", "dianben", "--steps", "border_detect", "--at", "2026-11-05 12:00"]) == 3
    assert freeze.main(["check", "--file", str(f), "--books", "dianben", "--at", "2026-11-05 12:00"]) == 3   # 不写 steps＝按结构步查
