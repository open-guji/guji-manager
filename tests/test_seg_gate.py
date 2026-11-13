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
