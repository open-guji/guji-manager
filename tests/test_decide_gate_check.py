# -*- coding: utf-8 -*-
"""cv 第四步出口检查 decide_gate（cv #2005）在 manager 里的读法：fail 汇总、flag 只计数、没跑不进 1a 坏账。"""
from __future__ import annotations

import json
from types import SimpleNamespace

from guji_manager.ops import close_check as CC
from guji_manager.ops import decide_gate_check as DG


class _Store:
    def __init__(self, root):
        self.root = root

    def read_raw(self, book, step, key):
        p = self.root / book / step / f"{key}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def _gate(root, book, pg, checks):
    d = root / book / "decide_gate"
    d.mkdir(parents=True, exist_ok=True)
    doc = {"decide_gate": {"page": pg, "passed": not any(c["level"] == "fail" for c in checks),
                           "checks": checks, "metrics": {}}}
    (d / f"p{pg:04d}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _c(name, level, key="1:2:3"):
    return {"name": name, "level": level, "unit": "cell", "key": key, "reason": "x", "metrics": {}}


def test_summarize_counts_fail_and_flag(tmp_path):
    _gate(tmp_path, "b", 1, [_c("char_not_in_evidence", "fail"), _c("rare_codepoint", "flag")])
    _gate(tmp_path, "b", 2, [_c("col_alt_cut", "flag")])
    s = DG.summarize("b", [1, 2, 3], _Store(tmp_path))
    assert s["checked"] == 2 and s["missing"] == [3]
    assert s["fails"] == {"char_not_in_evidence": 1} and s["fail_pages"] == [1]
    assert s["flags"] == {"rare_codepoint": 1, "col_alt_cut": 1}
    assert s["rows"][0]["page"] == 1 and s["rows"][0]["name"] == "char_not_in_evidence"
    assert "fail 1 条／1 页" in DG.describe(s) and "1 页没出 decide_gate" in DG.describe(s)


def test_close_check_2e_tiers(tmp_path):
    st = _Store(tmp_path)
    assert CC._decide_gate("b", [1], st)["status"] == CC.SKIP            # 一页都没有：cv 太旧或没补跑
    _gate(tmp_path, "b", 1, [_c("rare_codepoint", "flag")])
    assert CC._decide_gate("b", [1], st)["status"] == CC.PASS            # 只有 flag 不告警
    _gate(tmp_path, "b", 1, [_c("ref_shift", "fail", "3")])
    assert CC._decide_gate("b", [1], st)["status"] == CC.FAIL
    r = CC._decide_gate("b", [1], st, tier="rough")
    assert r["status"] == CC.PASS and "粗校档只报数" in r["detail"]


def _row(**counts):
    c = {"fresh": 0, "stale": 0, "missing": 0, "failed": 0, "blocked": 0, **counts}
    return {"counts": c, "pages": {}, "stale_reasons": {}}


def test_fresh_ignores_detect_only_gate_not_run():
    """cv 升级到带 decide_gate 后老册还没补跑：status 多一行 decide_gate 全 missing，1a 不能因此判失败。"""
    steps = {"seed_admit": _row(fresh=3), "decide_gate": _row(missing=3)}
    eng = SimpleNamespace(status=lambda pages, code_ok: {"steps": steps})
    assert CC._fresh(eng, [1, 2, 3])["status"] == CC.PASS
    steps["seed_admit"] = _row(fresh=2, missing=1)
    assert CC._fresh(eng, [1, 2, 3])["status"] == CC.FAIL                # 真正出字的步缺页照旧判失败


def test_stale_gate_not_counted(tmp_path):
    """上游重跑后 gate 自己过期：旧产物里的 fail 不作数，单列过期页（CV4 11-28）。"""
    _gate(tmp_path, "b", 1, [_c("ref_shift", "fail", "3")])
    _gate(tmp_path, "b", 2, [_c("rare_codepoint", "flag")])
    eng = SimpleNamespace(status=lambda pages: {"steps": {"decide_gate": {
        "pages": {1: {"status": "stale"}, 2: {"status": "fresh"}}}}})
    r = CC._decide_gate("b", [1, 2], _Store(tmp_path), eng=eng)
    assert r["status"] == CC.PASS and r["data"]["stale"] == [1] and "1 页 decide_gate 已过期" in r["detail"]
    eng1 = SimpleNamespace(status=lambda pages: {"steps": {"decide_gate": {"pages": {1: {"status": "stale"}}}}})
    assert CC._decide_gate("b", [1], _Store(tmp_path), eng=eng1)["status"] == CC.SKIP
