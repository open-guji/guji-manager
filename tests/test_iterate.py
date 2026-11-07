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


def test_closing(tmp_path):
    prev = [{"vol": "020", "cell": "1:1:1", "pending_reason": "hard_pair"}, {"vol": "021", "cell": "1:1:1", "pending_reason": "lib_missing"}]
    mk_round(tmp_path / "p", prev, {"020": 100, "021": 100})
    mk_round(tmp_path / "c", prev, {"020": 100, "021": 100})
    out = tmp_path / "o"
    round_report.main(["--cur", str(tmp_path / "c"), "--prev", str(tmp_path / "p"), "--label", "r5", "--out", str(out)])
    assert not (out / "notify_A33.txt").exists()
    rep = (out / "report.md").read_text(encoding="utf-8")
    assert "交接单·极难字" in rep


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


def test_leverage_l02_by_ref():
    """L02 只按参校本字并卡：库首位乱选，不拆卡（A23 11-06）。别的原因照旧按字对。"""
    cells = [{"vol": "035", "cell": f"1:1:{i}", "pending_reason": "lib_sparse_dissent", "ref": "𮪍", "top": t}
             for i, t in enumerate("驎關駉駒隋", 1)]
    cells += [{"vol": "005", "cell": f"2:1:{i}", "pending_reason": "group_abstain", "ref": "以", "top": t} for i, t in enumerate("已巳", 1)]
    cards, _ = leverage.rank(cells)
    l2 = [c for c in cards if c["reason"] == "lib_sparse_dissent"]
    assert len(l2) == 1 and l2[0]["n_cells"] == 5 and l2[0]["ref"] == "𮪍" and l2[0]["top"] == ""
    assert len([c for c in cards if c["reason"] == "group_abstain"]) == 2
    # L03 同样按参校字并卡（A23 L03 深挖 11-06）
    l3 = [{"vol": "057", "cell": f"9:1:{i}", "pending_reason": "lib_sparse_agree", "ref": "耆", "top": t} for i, t in enumerate("者書者", 1)]
    cards3, _ = leverage.rank(l3)
    assert len(cards3) == 1 and cards3[0]["n_cells"] == 3 and cards3[0]["tier"] == 0


def test_freeze(tmp_path):
    f = tmp_path / "cal.yaml"
    freeze.main(["add", "--file", str(f), "--book", "dianben", "--from", "2026-11-05 10:00", "--to", "2026-11-05 20:00"])
    fr = freeze.load(f)
    at = freeze.parse_t("2026-11-05 12:00")
    assert "A33" not in fr[0]["notify"]
    assert freeze.conflicts(fr, ["dianben"], ["row_segment"], at)
    assert not freeze.conflicts(fr, ["dianben"], ["seed_admit"], at)      # D 轮不冻结
    assert not freeze.conflicts(fr, ["shiji"], ["row_segment"], at)
    assert not freeze.conflicts(fr, ["dianben"], ["row_segment"], freeze.parse_t("2026-11-06 09:00"))
    assert freeze.main(["check", "--file", str(f), "--books", "dianben", "--steps", "border_detect", "--at", "2026-11-05 12:00"]) == 3
    assert freeze.main(["check", "--file", str(f), "--books", "dianben", "--at", "2026-11-05 12:00"]) == 3   # 不写 steps＝按结构步查


def test_progress_rounds_rows_and_report(tmp_path, capsys):
    from guji_manager.iterate import progress_rounds as pr
    assert [pr.round_key(x) for x in ("r5", "第5轮", "5", "r10b")] == ["r5", "r5", "r5", "r10b"]
    res = {"n": 90, "prev_n": 100, "cells_total": 45000, "net": 80, "regress": [{}] * 3, "by_vol": [{}, {}],
           "reasons": [{"reason": "a", "cur": 10, "delta": -8}, {"reason": "b", "cur": 5, "delta": 0}, {"reason": "c", "cur": 9, "delta": 2}]}
    rec = pr.from_report(res, "r5", kind="D", cv=None, verdict="main")
    assert rec["key"] == "r5" and rec["gain"] == 10 and rec["regress"] == 3 and rec["rate"] == 0.002
    assert [t["reason"] for t in rec["top"]] == ["a", "c"] and "cv" not in rec
    rs = pr.rows("bk", [rec, {"key": "r10b", "label": "第10b轮", "rate": None}], target=0.0015)
    assert rs[0][1] == "target" and rs[0][3] == 0.0015
    assert rs[1][4]["kind"] == "D" and "key" not in rs[1][4] and rs[1][5] < rs[2][5]
    f = tmp_path / "h.json"
    f.write_text(json.dumps({"books": {"bk": {"target": 0.002, "rounds": [rec]}, "other": {"rounds": [rec]}}}), encoding="utf-8")
    assert pr.main(["--json", str(f), "--book", "bk"]) == 0
    out = capsys.readouterr().out
    assert "bk\tr5" in out and "other" not in out


def test_progress_rounds_aggregate():
    from guji_manager.iterate import progress_rounds as pr
    v = lambda vol, m, p, cells, rev, cv="v0.6.3": {"vol": vol, "cv_version": cv, "extra": {"a31.main": {"label": m}, "cv.pack": {"label": p, "cells": cells, "review": rev}}}
    vols = [v("11", "x", "cv0.6.3-c30-g19-r5", 1000, 2), v("12", "x", "cv0.6.3-c31-g19-r5-a2", 3000, 4), v("13", "x", "cv0.6.2-c30-g19-r4", 1000, 9), v("01", "x", "job207", 500, 1)]
    assert pr.round_of("cv0.6.1.dev185pg85-c--g-2a1a4c-qtw07-r9b-a2") == "r9b" and pr.round_of("cv0.6.2-c1-g4-job207") is None
    r = pr.aggregate(vols, "r5", prev={"key": "r4", "vols": 2, "pending": 10})
    assert (r["vols"], r["cells"], r["pending"], r["gain"], r["cv"]) == (2, 4000, 6, 4, "0.6.3")
    assert abs(r["rate"] - 0.0015) < 1e-9 and r["key"] == "r5" and r["verdict"] == "main"
    assert "gain" not in pr.aggregate(vols, "r5", prev={"vols": 3, "pending": 10})
    assert pr.aggregate(vols, "r9", None) is None


def test_progress_rounds_auto_round_merges(monkeypatch):
    from guji_manager.iterate import progress_rounds as pr
    calls = []

    class Cur:
        def __init__(self, rows): self.rows = rows
        def fetchall(self): return self.rows

    class Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, q, args=()):
            if "FROM progress.volume" in q:
                return Cur([("11", {"a31.main": {"label": "r5"}, "cv.pack": {"label": "cv0.6.3-c30-g19-r5", "cells": 2000, "review": 3, "pick": "main"}}, None)])
            if "FROM progress.metric" in q:
                return Cur([("r4", {"pending": 5, "vols": 1}, "第4轮"), ("r5", {"note": "人工备注", "human_min": 12}, "第5轮")])
            calls.append((q, args)); return Cur([])

    import guji_manager._cv as cv
    monkeypatch.setattr(cv, "connect", lambda: Conn(), raising=False)
    out = pr.auto_round("bk", "r5")
    assert out["note"] == "人工备注" and out["human_min"] == 12 and out["gain"] == 2 and out["pending"] == 3
    put = [c for c in calls if "put_metric" in c[0]]
    assert put and put[0][1][2] == "r5" and put[0][1][3] == "第5轮" and out["cv"] == "0.6.3"
    assert pr.auto_round("bk", "cv0.6.2-c1-g4-job207") is None


def test_note_main_round_placeholder(monkeypatch):
    from guji_manager.iterate import progress_rounds as pr
    written = []

    class Conn:
        def __init__(self, exists): self.exists = exists
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a):
            class R:
                def fetchone(s): return (1,) if self.exists else None
            return R()

    import guji_manager._cv as cv
    monkeypatch.setattr(cv, "connect", lambda: Conn(False), raising=False)
    monkeypatch.setattr(pr, "write", lambda rs: written.extend(rs) or len(rs))
    assert pr.note_main_round("b1", "cv0.6.4-c30-g19-r5-a2")
    assert written[0][1] == "r5" and written[0][3] is None and written[0][4]["verdict"] == "pending"
    written.clear()
    monkeypatch.setattr(cv, "connect", lambda: Conn(True), raising=False)
    assert pr.note_main_round("b1", "r5") and not written          # 已有就不动
    assert not pr.note_main_round("b1", "job207")                  # 没有轮次的标签不占
