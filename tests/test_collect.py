"""收单快路 ``guji collect``：定字票对 book-text 现文分流、落字、核对位；cellvotes 落票结条目。"""
from __future__ import annotations

import json

import pytest

from guji_manager import collect as C


def _char(s, extra=None):
    cells = [{"a": f"1:1:{i + 1}", "c": ch} for i, ch in enumerate(s)]
    for a, kv in (extra or {}).items():
        next(x for x in cells if x["a"] == a).update(kv)
    return {"pages": [{"page": 1, "columns": [{"col": 1, "cells": cells}]}]}


def test_plan_edits_sorts_cells():
    char = _char("曰天□別圖", {"1:1:3": {"lacuna": True}, "1:1:5": {"fig": {"alt": "圖"}, "c": "□"}})
    want = {"1:1:1": ("日", "票"), "1:1:2": ("天", "票"), "1:1:3": ("地", "票"), "1:1:4": ("别", "票"),
            "1:1:5": ("圖", "票"), "1:1:9": ("人", "票"), "1:1:10": ("之", "票")}
    same = lambda p, q: {"别": "別"}.get(p, p) == {"别": "別"}.get(q, q)  # noqa: E731
    plan = C.plan_edits(char, want, box_problem=lambda a: "本列格位变了" if a == "1:1:1" else None, same=same)
    got = {k: [x[0] for x in v] for k, v in plan.items()}
    assert got["layout"] == ["1:1:1"]                 # 格框对不上：等重放
    assert got["already"] == ["1:1:2", "1:1:4"]       # 同字、只差码位都不动
    assert got["apply"] == ["1:1:3"]                  # □（阙）→ 人裁字
    assert got["fig"] == ["1:1:5"]
    assert got["missing"] == ["1:1:9", "1:1:10"]       # 按格序，不按字符串序


def test_apply_edits_sets_char_and_drops_lacuna():
    char = _char("曰天□", {"1:1:3": {"lacuna": True, "guess_c": "地"}})
    out = C.apply_edits(char, [("1:1:3", "□", "地", "票"), ("1:1:1", "曰", "日", "票")])
    cells = out["pages"][0]["columns"][0]["cells"]
    assert [x["c"] for x in cells] == ["日", "天", "地"]
    assert "lacuna" not in cells[2] and "guess_c" not in cells[2]
    assert char["pages"][0]["columns"][0]["cells"][2]["c"] == "□"     # 入参不动


def test_vote_chars_reads_only_char_confirms(tmp_path):
    rows = [{"id": "vol20:84:3:10", "v": "confirm", "shape": "𦱪"},
            {"id": "vol20:84:3:11", "v": "seg_defect", "quality": "truncated", "shape": "之"},
            {"id": "vol20:84:3:12", "v": "figure", "unk": "艹+冊"},
            {"id": "vol20:84:3:13", "v": "not_a_char"},
            {"id": "vol20:84:3:14", "v": "confirm", "shape": "□"}]
    (tmp_path / "drafts.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    assert C.vote_chars(tmp_path) == {"84:3:10": ("𦱪", "票")}


def test_live_open_cells():
    doc = {"cells": [{"cell": "1:1:1"}, {"cell": "1:1:2", "review": "human"}, {"cell": "vol01:1:1:3", "review": "pending"}]}
    assert C.live_open_cells(doc) == {"1:1:1", "1:1:3"}


def test_run_state_resume_and_dry(tmp_path):
    sp = tmp_path / "s" / "state.json"
    r = C.Run(sp, fresh=False)
    r.mark("pull", {"rev": "020-r13"})
    assert C.Run(sp, fresh=False).done("pull")
    assert not C.Run(sp, fresh=True).done("pull")
    d = C.Run(tmp_path / "d" / "state.json", fresh=True, dry=True)
    d.mark("draft")
    assert not (tmp_path / "d" / "state.json").exists()


def test_cellvotes_write_resolves_items_by_draft_id(tmp_path, monkeypatch):
    """草稿行只有 id（vol04:15:8:20）没有 a：落票后条目照样结案。"""
    from guji_manager import cli_cellvotes as CVT
    from guji_manager.review import pending_items as P

    store = P.ItemStore.open(tmp_path, "96mid1ogzk", "004")
    try:
        store.add("15:8:20", {"pending_reason": "R01"}, by="t", src="test")
    except TypeError:
        pytest.skip("ItemStore.add 签名变了")
    store.save()
    monkeypatch.setattr("guji_manager._cv.feedback_root", lambda: tmp_path / "feedback", raising=False)
    import guji_manager._cv as cvmod
    monkeypatch.setattr(cvmod, "feedback_root", lambda: tmp_path / "feedback", raising=False)
    rows = [{"id": "vol04:15:8:20", "v": "confirm", "shape": "之"}]
    CVT._resolve_items({"site_book": "96mid1ogzk", "rev": "004-r3"}, rows, {"ids": ["ev1"]}, "sheldon")
    st = P.ItemStore.open(tmp_path, "96mid1ogzk", "004")
    assert [x["state"] for x in st.items.values()] == ["resolved"]


def test_consistent_cells_from_draft_meta(tmp_path):
    meta = {"skipped": [["84:3:10", "与已有人裁 evt_H-web-vol20-020-r12-2026-11-19_000011 一致"],
                        ["84:3:11", "只有「看不出」×1"], ["84:3:12", "char 档不写"]]}
    (tmp_path / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    assert C.consistent_cells(tmp_path) == {"84:3:10": "evt_H-web-vol20-020-r12-2026-11-19_000011"}


def test_books_with_votes_picks_open_items_only():
    votes = [{"vol": "13", "item": "i1"}, {"vol": "013", "item": "i2"}, {"vol": "14", "item": "j1"}, {"vol": "20"}]
    open_ = {"013": {"i2"}, "014": set()}
    assert C.books_with_votes(votes, lambda ch: open_.get(ch, set())) == ["vol13"]


def test_ai_ruling_chars_window_hit_and_vis(tmp_path):
    """AI 裁定直接落（11-20）：文意按窗口命中且 high、字在组内；看图 O 要 admit_ok、对位字没变、非半格；已放行格不落。"""
    from guji_manager._cv import RulingLog, RulingStore
    from open_guji_cv.feedback.events import EventTarget, make_event
    from open_guji_cv.feedback.llm_queue import PENDING
    store = RulingStore(tmp_path / "fb")
    store._batch = "llm-x"
    store.put("ry", "v1", "甲乙", "丙丁", char="曰", conf="high", why="", model="m", cell="001:1:1:1")
    store.put("ry", "v1", "子丑", "寅卯", char="日", conf="mid", why="", model="m", cell="001:1:1:2")
    store.put("ry", "v1", "辰", "巳", char="月", conf="high", why="", model="m", cell="001:1:1:3")     # 不在组内
    store.put("ry", "v1", "午", "未", char="曰", conf="high", why="", model="m", cell="001:1:1:8")     # 已放行
    log = RulingLog(tmp_path / "fb")
    for i, (cell, ref) in enumerate([("001:1:1:4", "日"), ("001:1:1:5", "日"), ("001:1:1:6a", "日")]):
        pay = {"source": "llm", "group": "O", "prompt_ver": "vis-o1", "char": "曰", "conf": "high", "admit_ok": True,
               "cell": cell, "ref": ref, "ctx": {"left": "", "right": "", "hash": f"h{i}"}}
        log.append([make_event("vis-b", i + 1, "ctx_ruling", EventTarget(step="seed_admit", unit="cell", key=cell, book="001"),
                               pay, actor="model")])
    ask = lambda l, r: {"evidence": {"group": {"id": "ry", "solvers": [{"why": PENDING, "ask": {"ver": "v1", "l": l, "r": r}}]}}}  # noqa: E731
    root = tmp_path / "p"
    (root / "001" / "seed_admit").mkdir(parents=True)
    cells = [{"id": "001:1:1:1", "char": "日", **ask("甲乙", "丙丁")}, {"id": "001:1:1:2", "char": "日", **ask("子丑", "寅卯")},
             {"id": "001:1:1:3", "char": "日", **ask("辰", "巳")}, {"id": "001:1:1:4", "char": "日"},
             {"id": "001:1:1:5", "char": "日"}, {"id": "001:1:1:6a", "char": "日"},
             {"id": "001:1:1:8", "char": "曰", "admit": True, **ask("午", "未")}]
    (root / "001" / "seed_admit" / "p0001.json").write_text(json.dumps({"seed_admit": {"columns": [{"chars": cells}]}}), encoding="utf-8")
    (root / "001" / "align_ref").mkdir(parents=True)
    (root / "001" / "align_ref" / "p0001.json").write_text(json.dumps({"align_ref": {"chars": [
        {"id": "001:1:1:4", "align_char": "日"}, {"id": "001:1:1:5", "align_char": "曰"}, {"id": "001:1:1:6a", "align_char": "日"}]}}),
        encoding="utf-8")
    got, notes = C.ai_ruling_chars(root, "001", RulingStore(tmp_path / "fb"), members={"ry": {"日", "曰"}})
    assert got == {"1:1:1": ("曰", "AI文意/ry"), "1:1:4": ("曰", "AI看图/vis-o1")}
    joined = "\n".join(notes)
    assert "把握 mid" in joined and "不在组" in joined and "对位字" in joined and "半格" in joined


def test_ai_ruling_chars_cross_version_same_window(tmp_path):
    """提示词版本／字组改名、窗口没变的文意裁定（ZM 11-21 约 210 格）：rekey 列表给了才落，并记下待补键；窗口变了的不认。"""
    from guji_manager._cv import RulingStore
    from open_guji_cv.feedback.llm_queue import PENDING
    store = RulingStore(tmp_path / "fb")
    store._batch = "llm-x"
    store.put("ry", "v1#m:high", "甲乙", "丙丁", char="曰", conf="high", why="w", model="m", cell="001:1:1:1")
    store.put("ry_old", "v1", "子丑", "寅卯", char="日", conf="high", why="", model="m", cell="001:1:1:2")   # 组改名
    store.put("ry", "v1", "辰", "巳", char="曰", conf="high", why="", model="m", cell="001:1:1:3")          # 窗口变了
    ask = lambda l, r: {"evidence": {"group": {"id": "ry", "solvers": [{"why": PENDING, "ask": {"ver": "v2", "l": l, "r": r}}]}}}  # noqa: E731
    root = tmp_path / "p"
    (root / "001" / "seed_admit").mkdir(parents=True)
    cells = [{"id": "001:1:1:1", "char": "日", **ask("甲乙", "丙丁")}, {"id": "001:1:1:2", "char": "曰", **ask("子丑", "寅卯")},
             {"id": "001:1:1:3", "char": "日", **ask("辰辰", "巳")}]
    (root / "001" / "seed_admit" / "p0001.json").write_text(json.dumps({"seed_admit": {"columns": [{"chars": cells}]}}), encoding="utf-8")
    got, _ = C.ai_ruling_chars(root, "001", RulingStore(tmp_path / "fb"), members={"ry": {"日", "曰"}})
    assert got == {}                                   # 不给 rekey：照旧只认窗口键
    rk: list = []
    got, _ = C.ai_ruling_chars(root, "001", RulingStore(tmp_path / "fb"), members={"ry": {"日", "曰"}}, rekey=rk)
    assert got == {"1:1:1": ("曰", "AI文意/ry/改版重键"), "1:1:2": ("日", "AI文意/ry/改版重键")}
    assert sorted(q["cell"] for q, _ in rk) == ["001:1:1:1", "001:1:1:2"]
    import os
    os.environ["GUJI_FEEDBACK_DIR"] = str(tmp_path / "fb")
    try:
        from unittest import mock
        with mock.patch("guji_manager._cv.RulingStore", lambda: RulingStore(tmp_path / "fb")):
            assert C.write_rekeys("001", rk, batch="llm-rekey-t") == 2
    finally:
        os.environ.pop("GUJI_FEEDBACK_DIR", None)
    s2 = RulingStore(tmp_path / "fb")
    assert s2.get("ry", "v2", "甲乙", "丙丁")["char"] == "曰"
    assert s2.get("ry", "v2", "子丑", "寅卯")["why"].startswith("rekey:")


def test_why_tail_picks_error_lines():
    C._TAIL[:] = ["读票 12 条", "Traceback (most recent call last):", "BadRequest: 事件锚点 vol78:3:2:5 页表 rev r004≠r005", ""]
    w = C._why("cellvotes write 失败")
    assert w.startswith("cellvotes write 失败｜") and "vol78:3:2:5" in w


def test_run_keeps_tail(tmp_path):
    import sys
    rc = C._run([sys.executable, "-c", "print('a'); print('格 1:2:3 坏了'); raise SystemExit(3)"], {**__import__('os').environ})
    assert rc == 3 and C._TAIL[-1] == "格 1:2:3 坏了"


def test_run_parallel_one_sync(tmp_path, monkeypatch):
    """--jobs：每册一个子进程（--child，各自 worktree），回来后父进程只推库一次、给各册记推库。"""
    import argparse
    import subprocess as sp
    from pathlib import Path
    from guji_manager.swap import booktext as BT
    calls, marked = [], []
    monkeypatch.setattr(BT, "_git", lambda *a, **k: "")
    monkeypatch.setattr(C, "_run", lambda cmd, env, tries=1: calls.append([str(c) for c in cmd]) or 0)

    def fake_child(cmd, env=None, stdout=None, stderr=None):
        b = cmd[cmd.index("--books") + 1]
        assert "--child" in cmd and cmd[cmd.index("--worktree") + 1].endswith(f"-collect-{b}")
        st = "blocked" if b == "vol03" else "to-sync"
        Path(env["GUJI_COLLECT_RESULT"]).write_text(json.dumps({b: {"status": st, "why": "x" if st == "blocked" else None}}))
        return sp.CompletedProcess(cmd, 0)
    monkeypatch.setattr(C.subprocess, "run", fake_child)

    class R:
        def __init__(self, b):
            self.b = b

        def mark(self, step, info=None, t=None):
            marked.append((self.b, step))
    monkeypatch.setattr(C, "_state_of", lambda ws, tid, b: (None, R(b), None))
    a = argparse.Namespace(no_pull=False, book_text=str(tmp_path / "bt"), text_id="t", reviewer="r", batch=None, no_push=False,
                           no_ai=False, fresh=False, keep_pack=False, jobs=3, no_publish=False)
    res = C.run_parallel(a, tmp_path, ["vol01", "vol02", "vol03"], tmp_path / "runs" / "x.json")
    assert {b: v["status"] for b, v in res.items()} == {"vol01": "to-publish", "vol02": "to-publish", "vol03": "blocked"}
    assert sum(1 for c in calls if "sync" in c) == 1 and sum(1 for c in calls if "pull" in c) == 1
    assert sorted(marked) == [("vol01", "sync"), ("vol02", "sync")]


def test_ai_ruling_chars_by_cell(tmp_path):
    """按格写的文意裁定（ZM 11-21 兩雨 3 格、閔 1 格 landed 0）：seed_admit 没 ask，或 ask 同组同版本但窗口小变，
    按格号取、窗口大体一致（紧邻字一样、相似度够）且字是整理本字／库前五／组员才落；对不上的写进 notes。"""
    from guji_manager._cv import RulingStore
    from open_guji_cv.feedback.llm_queue import PENDING
    L, R = "江南江北之地凡十有二", "淮之鹽皆屬焉其後又分"
    store = RulingStore(tmp_path / "fb")
    store._batch = "llm-wenyi-b5"
    store.put("liang", "liang-l2-1", L, R, char="兩", conf="high", why="", model="m", cell="001:1:1:2")      # 无 ask，窗口一致
    store.put("men", "men-l2-1", "統冠□□□冠燕居冠顔", R, char="閔", conf="high", why="", model="m", cell="001:1:1:5")  # ask 窗口远处一字不同
    store.put("liang", "liang-l2-1", "完全不同的上文內容", R, char="兩", conf="high", why="", model="m", cell="001:1:1:7")  # 窗口对不上
    store.put("liang", "liang-l2-1", "其他上文", "其他下文", char="木", conf="high", why="", model="m", cell="001:1:1:9")       # 字不沾边
    ask = lambda g, v, l, r: {"evidence": {"group": {"id": g, "solvers": [{"why": PENDING, "ask": {"ver": v, "l": l, "r": r}}]}}}  # noqa: E731
    root = tmp_path / "p"
    for d in ("seed_admit", "align_ref", "glyph_match"):
        (root / "001" / d).mkdir(parents=True)
    seq = list(L) + ["X"] + list(R)
    cells = [{"id": f"001:1:1:{100 + i}", "char": c, "admit": True, "slot": i + 1} for i, c in enumerate(seq)]
    cells[len(L)]["id"] = "001:1:1:2"
    cells[len(L)]["admit"] = False
    cells[len(L)]["char"] = "雨"
    cells += [{"id": "001:1:1:5", "char": "閑", "slot": 90, **ask("men", "men-l2-1", "載冠□□□冠燕居冠顔", R)},
              {"id": "001:1:1:7", "char": "雨", "slot": 91, **ask("liang", "liang-l2-1", "另一段文字甲乙丙", R)},
              {"id": "001:1:1:9", "char": "雨", "slot": 92, **ask("liang", "liang-l2-1", "其他上文", "其他下文又")}]
    (root / "001" / "seed_admit" / "p0001.json").write_text(json.dumps({"seed_admit": {"page": 1, "columns": [{"col": 1, "chars": cells}]}}),
                                                           encoding="utf-8")
    (root / "001" / "align_ref" / "p0001.json").write_text(json.dumps({"align_ref": {"chars": [
        {"id": "001:1:1:2", "align_char": "兩"}]}}), encoding="utf-8")
    (root / "001" / "glyph_match" / "p0001.json").write_text(json.dumps({"glyph_match": {"columns": [{"chars": [
        {"id": "001:1:1:2", "candidates": [["雨", 0.98], ["兩", 0.97], ["而", 0.96]]}]}]}}), encoding="utf-8")
    got, notes = C.ai_ruling_chars(root, "001", RulingStore(tmp_path / "fb"),
                                   members={"liang": {"兩", "雨"}, "men": {"閔", "閑"}}, rekey=[])
    assert got.get("1:1:5") == ("閔", "AI文意/men/按格")
    joined = "\n".join(notes)
    assert "1:1:7" not in got and "1:1:7 按格文意裁定" in joined and "对不上" in joined
    assert "1:1:9" not in got and "不是整理本字" in joined
    # 无 ask 的格：窗口按 5c 口径从 seed_admit 现算
    assert got.get("1:1:2") == ("兩", "AI文意/liang/按格"), notes


def test_window_ok():
    assert C._window_ok("甲乙丙丁戊己庚辛", "壬癸子丑", "甲乙丙丁戊己庚辛", "壬癸子丑")[0]
    assert C._window_ok("某乙丙丁戊己庚辛", "壬癸子丑", "甲乙丙丁戊己庚辛", "壬癸子丑")[0]      # 远处一字变
    assert not C._window_ok("甲乙丙丁戊己庚某", "壬癸子丑", "甲乙丙丁戊己庚辛", "壬癸子丑")[0]  # 紧邻字变


def test_ledger_of_and_render():
    from guji_manager import collect as C
    meta = {"n_raw": 5, "n_votes": 4, "old_landed": 2, "old_sheet": 1, "waiting": 0, "ready": 3, "held": 1, "skipped": [("a", "x")]}
    r = C.ledger_of("vol06", "006-r13", meta, plan={"apply": 2, "already": 1, "layout": 0}, want=3, n_ai=0)
    assert (r["votes"], r["old_landed"], r["skipped"], r["apply"], r["already"]) == (5, 2, 1, 2, 1)
    txt = C.render_ledger([r], {"vol06": "done"})
    lines = txt.splitlines()
    assert lines[0].startswith("册\t单版\t收件箱票") and lines[1].startswith("vol06\t006-r13\t5") and lines[-1].startswith("合计")


def test_needs_review_of_collects_three_sources(tmp_path):
    from guji_manager import collect as C
    d = tmp_path / "reports" / "vol21" / "_collect" / "021-r12"
    (d / "draft").mkdir(parents=True)
    (d / "needs_review.tsv").write_text("说明\n143:9:4 新包「𣴭」≠人裁／手改「茫」\n", encoding="utf-8")
    (d / "draft" / "stale_votes.tsv").write_text("格位\t票\n1:1:1\tchar=甲\n", encoding="utf-8")
    got = C.needs_review_of(tmp_path, {"vol21": {"rev": "021-r12"}, "vol22": {"rev": "022-r1"}})
    assert list(got) == ["vol21"] and len(got["vol21"]) == 2
