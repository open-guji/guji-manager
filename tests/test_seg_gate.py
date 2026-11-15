"""guji seg gate：新旧两份 seg check 列清单比回退、页级错、台账挂靠。只用自造的列清单。"""
from __future__ import annotations

import csv
import json

from guji_manager import seg_gate as sg

FIELDS = ["列", "类", "处置", "结构分", "装饰分", "各项", "例格"]


def _write(d, rows):
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "列清单.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t")
        w.writeheader()
        for col, act in rows:
            w.writerow({"列": col, "类": "结构" if act in sg.STRUCT_ACTS else "装饰", "处置": act,
                        "结构分": 1, "装饰分": 0, "各项": "{}", "例格": ""})
    return d


def test_regression_blocks_known_does_not(tmp_path):
    base = _write(tmp_path / "base", [("vol01:5:1", "需钉子"), ("vol01:5:2", "公用清格"), ("vol01:6:1", "需钉子")])
    new = _write(tmp_path / "new", [("vol01:5:1", "需钉子"), ("vol01:5:2", "需钉子")])
    ledger = tmp_path / "ledger.tsv"
    ledger.write_text("\t".join(sg.LEDGER_COLS) + "\n" + "R001\t殿本\t1\t列端框线\t01:5\t在办\tA22\tr9\t2026-11-13\n",
                      encoding="utf-8")
    text, code = sg.run(new, base, tmp_path / "out", ledger_path=ledger, book="殿本")
    assert code == 3 and "01:5:2" in text
    meta = json.loads((tmp_path / "out" / "gate.json").read_text(encoding="utf-8"))
    assert meta["n_regress"] == 1 and meta["n_known"] == 1 and meta["n_fixed"] == 1 and meta["n_unregistered"] == 0
    rows = list(csv.DictReader(open(tmp_path / "out" / "切分未定.tsv", encoding="utf-8"), delimiter="\t"))
    assert {(r["页"], r["列"], r["回退"], r["根因号"]) for r in rows} == {("5", "1", "", "R001"), ("5", "2", "是", "R001")}


def test_known_only_passes_and_lists_unregistered(tmp_path):
    base = _write(tmp_path / "base", [("01:5:1", "版式不符")])
    new = _write(tmp_path / "new", [("vol01:5:1", "版式不符")])
    text, code = sg.run(new, base, tmp_path / "out")
    assert code == 0 and "可以标 main" in text and "01:5:1" in text.split("未挂台账")[-1]


def test_page_level_error(tmp_path):
    cols = [(f"01:7:{c}", "需钉子") for c in range(1, 6)] + [("01:7:6", "公用清格")]
    base = _write(tmp_path / "base", [(f"01:7:{c}", "需钉子") for c in range(1, 3)])
    g = sg.gate(sg.read_check(_write(tmp_path / "new", cols)), sg.read_check(base), [])
    assert g["bad_pages"] == [("01", 7)] and g["blocked"]


def test_ledger_patterns_and_closed(tmp_path):
    led = [{"根因号": "R1", "涉及": "vol28:*:*", "状态": "在办"}, {"根因号": "R2", "涉及": "42:114:2", "状态": "已结"}]
    assert sg.ledger_hit(led, ("28", 3, 4)) == "R1"
    assert sg.ledger_hit(led, ("42", 114, 2)) == ""


def test_ledger_filtered_by_book(tmp_path):
    led = tmp_path / "l.tsv"
    led.write_text("\t".join(sg.LEDGER_COLS) + "\n" + "R1\t史記\t2\tx\t01:5\t在办\tSJ\t\t\n", encoding="utf-8")
    assert sg.read_ledger(led, "殿本") == [] and len(sg.read_ledger(led, "史記")) == 1


def _write_geo(d, geo):
    with open(d / "格几何.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["列", "格几何"])
        for k, g in geo.items():
            w.writerow([k, g])


def test_geometry_same_not_regress(tmp_path):
    """新冒出的结构列，格子与旧包一样（线挪 ≤0.05 格高）→ 不挡、切分未定里记「几何没变」；挪多了照挡；缺几何表照旧挡。"""
    base = _write(tmp_path / "base", [])
    new = _write(tmp_path / "new", [("031:5:1", "需钉子"), ("031:5:2", "需钉子"), ("031:5:3", "需钉子")])
    g0 = "1:0,100,10,300;2:0,300,10,500;3:0,500,10,700#1:1,110,9,290"
    _write_geo(base, {"031:5:1": g0, "031:5:2": g0, "031:5:3": g0})
    _write_geo(new, {"031:5:1": "1:0,103,10,302;2:0,302,10,498;3:0,498,10,700#1:1,112,9,290",
                     "031:5:2": "1:0,100,10,260;2:0,260,10,500;3:0,500,10,700#1:1,110,9,290",
                     "031:5:3": "1:0,100,10,300;2:0,300,10,500;3a:5,500,10,700;3b:0,500,5,700#1:1,110,9,290"})
    _, code = sg.run(new, base, tmp_path / "out")
    meta = json.loads((tmp_path / "out" / "gate.json").read_text(encoding="utf-8"))
    assert code == 3 and meta["n_regress"] == 2 and meta["n_geo_same"] == 1 and meta["geometry"]
    with open(tmp_path / "out" / "切分未定.tsv", encoding="utf-8") as f:
        rows = {r["列"]: r["回退"] for r in csv.DictReader(f, delimiter="\t")}
    assert rows == {"1": "几何没变", "2": "是", "3": "是"}
    (base / "格几何.tsv").unlink()
    _, code = sg.run(new, base, tmp_path / "out2")
    assert code == 3 and json.loads((tmp_path / "out2" / "gate.json").read_text(encoding="utf-8"))["n_regress"] == 3


def test_r020_qtw_s1_regression_sample():
    """全唐文 R020（2026-11-14）：s1 对 g1 闸挡 143 列，QTW 逐列看图。按 0.05 格高收掉「切分没变」53 列，32 列真回退一列不放。"""
    from pathlib import Path
    with open(Path(__file__).parent / "data" / "seg_gate_R020_qtw_s1.tsv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    assert len(rows) == 143
    same = {r["列"] for r in rows if sg.geometry_same(r["s1格几何"], r["g1格几何"])}
    real = {r["列"] for r in rows if r["结论"] == "s1 真回退"}
    assert len(real) == 32 and not (same & real)
    assert {r["结论"] for r in rows if r["列"] in same} == {"切分没变(闸误报)"} and len(same) == 53
