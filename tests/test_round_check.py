"""收轮检查（`guji round-check`、任务库单型 roundcheck；A31 2026-11-20）。"""
from __future__ import annotations

import argparse
import json
from collections import Counter

import pytest

from guji_manager import round_check as RC
from guji_manager.jobs import spec as SP

C1 = "a" * 40


def norm(**kw):
    return SP.normalize(kw, resolve=lambda ref: C1)


# ── 单型 ──
def test_roundcheck_spec_normalizes():
    s = norm(kind="roundcheck", book="046", cv="v0.7.80", ws_glob="995ejelvk0-*",
             roundcheck={"pack": "046-r12", "ledger": "根因号\t书\nR1\t全唐文\n", "ledger_book": "全唐文"})
    assert s["roundcheck"] == {"pack": "046-r12", "main": "main", "ledger_book": "全唐文",
                               "ledger": "根因号\t书\nR1\t全唐文\n", "ledger_src": None, "allow": None}
    assert s["base"] is None and s["output"]["pack"] is False and s["run"] is None
    assert "收轮检查 046-r12 对 main 台账 全唐文" in SP.summary(s)


@pytest.mark.parametrize("rc,msg", [
    ({}, "roundcheck.pack"),
    ({"pack": "main"}, "不能是 main"),
    ({"pack": "x", "ledger": "a"}, "ledger_book"),
    ({"pack": "x", "foo": 1}, "只收"),
])
def test_roundcheck_spec_rejects(rc, msg):
    with pytest.raises(SP.SpecError, match=msg):
        norm(kind="roundcheck", book="046", cv="v0.7.80", roundcheck=rc)


def test_roundcheck_needs_book_and_no_base():
    with pytest.raises(SP.SpecError, match="book"):
        norm(kind="roundcheck", cv="v0.7.80", roundcheck={"pack": "x"})
    with pytest.raises(SP.SpecError, match="只读"):
        norm(kind="roundcheck", book="046", cv="v0.7.80", base="main", roundcheck={"pack": "x"})


def test_old_kinds_unchanged():
    """不是 roundcheck 的单不出 roundcheck 键：老任务的指纹不变；rerun 带 roundcheck 拒收。"""
    s = norm(kind="rerun", book="vol10", cv="v0.5.16")
    assert "roundcheck" not in s
    with pytest.raises(SP.SpecError, match="kind=roundcheck"):
        norm(kind="rerun", book="vol10", cv="v0.5.16", roundcheck={"pack": "x"})


def test_ledger_in_hash():
    a = norm(kind="roundcheck", book="046", cv="v", roundcheck={"pack": "p", "ledger": "h\n", "ledger_book": "全唐文"})
    b = norm(kind="roundcheck", book="046", cv="v", roundcheck={"pack": "p", "ledger": "h\nR\n", "ledger_book": "全唐文"})
    assert SP.spec_hash(a) != SP.spec_hash(b)


def test_submit_args_carry_local_ledger_and_allow(tmp_path):
    from guji_manager.jobs.cli import _spec_from_args, fill
    led = tmp_path / "台账.tsv"
    led.write_text("根因号\t书\t层\nR1\t史記\tx\nR2\t全唐文\ty\nR3\t*\tz\n", encoding="utf-8")
    allow = tmp_path / "allow.tsv"
    allow.write_text("046\t3\t*\n", encoding="utf-8")
    p = argparse.ArgumentParser()
    fill(p)
    a = p.parse_args(["submit", "--book", "046", "--book-id", "995ejelvk0", "--cv", "v0.7.80", "--rc-pack", "046-r12",
                      "--rc-ledger-book", "全唐文", "--rc-ledger", str(led), "--rc-allow", str(allow)])
    raw = _spec_from_args(a)
    assert raw["kind"] == "roundcheck"
    rc = raw["roundcheck"]
    assert rc["ledger"] == "根因号\t书\t层\nR2\t全唐文\ty\nR3\t*\tz\n"      # 只留本书和 * 的行
    assert rc["ledger_src"] == "file:台账.tsv" and rc["allow"] == "046\t3\t*\n"
    s = SP.normalize(raw, resolve=lambda r: C1)
    assert s["roundcheck"]["pack"] == "046-r12" and s["ws_glob"] == "995ejelvk0-*"


def test_submit_no_ledger():
    from guji_manager.jobs.cli import _spec_from_args, fill
    p = argparse.ArgumentParser()
    fill(p)
    a = p.parse_args(["submit", "--book", "046", "--cv", "v", "--rc-pack", "x", "--rc-ledger", "none"])
    assert "ledger" not in _spec_from_args(a)["roundcheck"]


# ── 四层（QTW cls36 口径）──
G, NF = frozenset("己已巳"), frozenset("日曰")


def fact(**kw):
    f = {"ref": "天", "top": "天", "cov": 0.95, "has_cands": True, "r5": [], "doubts": "", "channel": "lib"}
    f.update(kw)
    return f


LIB = Counter({"天": 9, "己": 9, "日": 9})


@pytest.mark.parametrize("f,want", [
    (fact(doubts="occluded"), "1 切分"),
    (fact(channel="seal"), "1 切分"),
    (fact(cov=0.85), "1 切分"),
    (fact(cov=0.0, has_cands=False), "2 库缺样本"),          # 无候选不算切分，算库缺
    (fact(ref="己", cov=0.85), "1 切分"),                    # 判序 切分 先于 形近
    (fact(ref="己"), "3 形近字组"),
    (fact(ref="日"), "3 形近字组"),
    (fact(doubts="near_form"), "3 形近字组"),
    (fact(ref="地"), "2 库缺样本"),
    (fact(r5=["地"]), "2 库缺样本"),
    (fact(), "4 其余"),
])
def test_classify_default_order(f, want):
    assert RC.classify(f, RC.LayerConfig(), G, NF, LIB) == want


def test_layer_config_from_ws(tmp_path):
    (tmp_path / "workspace.yaml").write_text("id: x\nround_check:\n  order: [group, seg, lib]\n  cov_min: 0.8\n"
                                             "  lib_min: 3\n  seg_defect: true\n", encoding="utf-8")
    c = RC.LayerConfig.from_ws(tmp_path)
    assert c.as_dict() == {"order": ["group", "seg", "lib"], "cov_min": 0.8, "lib_min": 3, "seg_defect": True}
    assert RC.classify(fact(ref="己", cov=0.85), c, G, NF, LIB) == "3 形近字组"
    assert RC.classify(fact(cov=0.85), c, G, NF, LIB) == "4 其余"
    assert RC.LayerConfig.from_ws(tmp_path / "none").as_dict() == RC.LayerConfig().as_dict()


def _page(root, step, body):
    d = root / step
    d.mkdir(parents=True, exist_ok=True)
    (d / "p0001.json").write_text(json.dumps({step: body}, ensure_ascii=False), encoding="utf-8")


def test_pending_facts_and_rows(tmp_path):
    root = tmp_path / "046"
    _page(root, "seed_admit", {"columns": [{"chars": [
        {"id": "046:1:1:1", "char": "天", "admit": True},
        {"id": "046:1:1:2", "char": "己", "admit": False, "doubts": ["near_form"]},
        {"id": "046:1:1:3", "char": "地", "admit": False, "channel": "excluded"},
        {"id": "046:1:1:4", "char": "人", "admit": False, "doubts": ["occluded"]}]}]})
    _page(root, "glyph_match", {"columns": [{"chars": [
        {"id": "046:1:1:2", "candidates": [["已", 0.97]]}, {"id": "046:1:1:4", "candidates": []}]}]})
    _page(root, "rare_candidates", {"columns": [{"chars": [{"id": "046:1:1:2", "candidates": [{"char": "已"}, {"char": "巳"}]}]}]})
    _page(root, "align_ref", {"chars": [{"id": "046:1:1:2", "align_char": "己"}]})
    n, facts = RC.pending_facts(tmp_path, "046")
    assert n == 3 and set(facts) == {"046:1:1:2", "046:1:1:4"}
    assert facts["046:1:1:2"] == {"ref": "己", "top": "已", "cov": 0.97, "has_cands": True, "r5": ["已", "巳"],
                                  "doubts": "near_form", "channel": None}
    rows = {r["cell"]: r for r in RC.layer_rows(facts, RC.LayerConfig(), Counter(), sets=(G, NF))}
    assert rows["046:1:1:2"]["层"] == "3 形近字组" and rows["046:1:1:4"]["层"] == "1 切分"


def test_lib_counter(tmp_path):
    p = tmp_path / "exemplars.jsonl"
    p.write_text('{"char":"天"}\n{"char":"天"}\n\n{"char":"地"}\n', encoding="utf-8")
    lib, meta = RC.lib_counter(p)
    assert lib == Counter({"天": 2, "地": 1}) and meta["rows"] == 3 and len(meta["sha"]) == 12
    assert RC.lib_counter(None)[1]["sha"] is None


def test_cv_sets_available():
    g, nf = RC._cv_sets()
    assert g and nf


# ── 收一批 ──
def _summary(blocked=False, hits=0):
    return {"book": "046", "pack_got": "046-r12", "main": "046-r11", "pass": not blocked and not hits,
            "gate": {"blocked": blocked, "n_regress": int(blocked), "n_bad_pages": 0, "n_known": 2, "n_unregistered": 1},
            "premain": {"hits": hits, "cols": hits, "pass": not hits},
            "pending": {"cells": 1000, "total": 7, "by_layer": {"1 切分": 2, "4 其余": 5},
                        "by_reason": [{"码": "S04", "pending_reason": "seg_defect", "格数": 2}]},
            "diff": {"review_main": 9, "review_new": 7, "flips": {"放行字变": 1, "review→admit": 3}},
            "central_rev": 123, "glyph_lib": {"sha": "abc"}}


def test_verdict_line_and_collect(tmp_path):
    assert "通过" in RC.verdict_line(_summary()) and "不能标 main" in RC.verdict_line(_summary(blocked=True))
    jobs = {
        1: {"id": 1, "kind": "roundcheck", "book": "046", "status": "succeeded",
            "results": [{"name": "roundcheck", "data": {"summary": _summary()}},
                        {"name": "seg_gate", "data": json.dumps({"text": "# gate\n"})}]},
        2: {"id": 2, "kind": "roundcheck", "book": "047", "status": "succeeded",
            "results": [{"name": "roundcheck", "data": {"summary": {**_summary(hits=2), "book": "047"}}}]},
        3: {"id": 3, "kind": "roundcheck", "book": "048", "status": "failed", "results": []},
    }

    def db(fn, i):
        return jobs.get(i)
    code = RC.collect(db, [1, 2, 3, 4], tmp_path, say=lambda *_: None)
    assert code == 3
    rows = (tmp_path / "汇总.tsv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 4 and rows[1].split("\t")[5] == "通过" and rows[2].split("\t")[5] == "不能标main"
    assert (tmp_path / "046" / "gate.md").read_text(encoding="utf-8") == "# gate\n"
    assert "S04\tseg_defect\t4" in (tmp_path / "待审按原因-合计.tsv").read_text(encoding="utf-8")


def test_ids():
    assert RC._ids("12,20-22") == [12, 20, 21, 22]


def test_command_registered():
    from guji_manager.commands import COMMANDS
    assert "round-check" in COMMANDS


# ── 执行方 ──
def test_runner_roundcheck_writes_files_and_results(tmp_path):
    from guji_manager.jobs import runner as R
    j = object.__new__(R.Job)
    j.spec = {"book": "046", "pages": "all", "roundcheck": {"pack": "046-r12", "main": "main", "ledger_book": "全唐文",
                                                            "ledger": "根因号\t书\n", "ledger_src": "ai-team@abc", "allow": "x\n"}}
    j.dry, j.id, j.aid, j.ws, j.dir = False, 9, 1, "/ws", tmp_path
    j.evs, j.res, j.calls = [], [], []
    j.ev = lambda msg, **k: j.evs.append(msg)
    j.db = lambda fn, *a, **k: j.res.append((a[2], a[3], k.get("data")))

    def guji(*args, **kw):
        j.calls.append(args)
        out = tmp_path / "roundcheck"
        (out / "seg-gate").mkdir(parents=True)
        (out / "seg-gate" / "gate.md").write_text("# g\n", encoding="utf-8")
        (out / "summary.json").write_text(json.dumps(_summary()), encoding="utf-8")
        return ""
    j.guji = guji
    j.run_roundcheck()
    a = j.calls[0]
    assert a[:2] == ("round-check", "046") and "--job" in a and a[a.index("--ledger-book") + 1] == "全唐文"
    assert (tmp_path / "ledger.tsv").read_text(encoding="utf-8") == "根因号\t书\n"
    assert (tmp_path / "allow.tsv").read_text(encoding="utf-8") == "x\n"
    names = {(k, n): d for k, n, d in j.res}
    assert names[("check", "seg_gate")]["text"] == "# g\n" and names[("check", "seg_gate")]["blocked"] is False
    assert names[("output", "roundcheck")]["summary"]["ledger_src"] == "ai-team@abc"
    assert "通过" in j.evs[-1]


def test_roundcheck_book_id_fills_ws_repo():
    """QTW 11-20 首批 22 单：只给 --book-id、spec 里 ws_repo=null，新执行机没克隆就备不了工作区。"""
    from guji_manager.jobs.cli import _spec_from_args, fill
    p = argparse.ArgumentParser()
    fill(p)
    for bid, repo in (("995ejelvk0", "guji-workspace/995ejelvk0-quan-tang-wen"),
                      ("988g3f0wsu", "guji-workspace/988g3f0wsu-shi-ji-wen-yuan-ge"),
                      ("96mid1ogzk", "guji-workspace/96mid1ogzk-si-ku-zong-mu")):
        a = p.parse_args(["submit", "--book", "046", "--book-id", bid, "--cv", "v", "--rc-pack", "x", "--rc-ledger", "none"])
        assert SP.normalize(_spec_from_args(a), resolve=lambda r: C1)["ws_repo"] == repo
    a = p.parse_args(["submit", "--book", "046", "--book-id", "995ejelvk0", "--ws-repo", "o/r", "--cv", "v", "--rc-pack", "x",
                      "--rc-ledger", "none"])
    assert SP.normalize(_spec_from_args(a), resolve=lambda r: C1)["ws_repo"] == "o/r"
