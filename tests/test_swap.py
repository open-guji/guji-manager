"""换单 driver 里不连网的部分：册号展开、分批、账本核对、auto_cycle 输出解析、状态读写。"""

import json

import pytest

from guji_manager import swap


def test_parse_books_expands_ranges_and_dedups():
    assert swap.parse_books("vol20-vol22,vol21,vol30") == ["vol20", "vol21", "vol22", "vol30"]
    assert swap.parse_books("20-22") == ["20", "21", "22"]      # 纯数字册名（全唐文、史記）也能写区间
    with pytest.raises(SystemExit):
        swap.parse_books("vol1-3")


def test_chunks():
    assert list(swap.chunks(list(range(7)), 3)) == [[0, 1, 2], [3, 4, 5], [6]]


def test_ledger_problem():
    ok = {"glyphs.jsonl": 3381, "exemplars.jsonl": 21928, "admissions.jsonl": 22002}
    assert swap.ledger_problem(ok, None) is None
    assert swap.ledger_problem(ok, dict(ok)) is None
    assert "空文件" in swap.ledger_problem({**ok, "glyphs.jsonl": 0}, ok)
    assert "降到" in swap.ledger_problem({**ok, "exemplars.jsonl": 100}, ok)      # 少了九成
    assert swap.ledger_problem({**ok, "exemplars.jsonl": 21000}, ok) is None      # 少一点不拦


def test_ledger_counts(tmp_path):
    store = tmp_path / "output" / "glyph_store"
    store.mkdir(parents=True)
    (store / "glyphs.jsonl").write_text("a\nb\n")
    got = swap.ledger_counts(tmp_path)
    assert got == {"glyphs.jsonl": 2, "exemplars.jsonl": 0, "admissions.jsonl": 0}


def test_parse_cycle_log():
    text = "guji-manager 3f609c8\nvol20\tgo\t零票\nvol20\t→ done\t写人裁 0 条\nvol21\t→ need-A33\t锚点落空\n"
    assert swap.parse_cycle_log(text) == {
        "vol20": {"verdict": "done", "why": "写人裁 0 条"},
        "vol21": {"verdict": "need-A33", "why": "锚点落空"}}


def test_state_roundtrip(tmp_path):
    p = tmp_path / "x" / "state.json"
    assert swap.load_state(p) == {"books": {}}
    swap.save_state(p, {"books": {"vol20": {"status": "verified"}}})
    assert json.loads(p.read_text())["books"]["vol20"]["status"] == "verified"


def test_expected_rev(tmp_path):
    for r in ("020-r5", "020-r6", "020-r10"):
        (tmp_path / "reports" / "vol20" / "_cycle" / r).mkdir(parents=True)
    assert swap.expected_rev(tmp_path, "vol20", "x") == "020-r11"
    assert swap.expected_rev(tmp_path, "vol99", "x") is None


def test_resume_skips_issued_books(tmp_path, monkeypatch):
    """上次已换好单（done／publish-mismatch）的册，续跑时只补发布，不再进 auto_cycle。"""
    import argparse
    ws = tmp_path
    sp = ws / "state.json"
    swap.save_state(sp, {"books": {"vol20": {"status": "done"}, "vol21": {"status": "publish-mismatch"},
                                   "vol22": {"status": "verified"}, "vol23": {"status": "need-A33"}}})
    monkeypatch.setattr(swap, "precheck", lambda ws, state, *a: None)
    monkeypatch.setattr(swap, "current_main", lambda ws, b: None)
    a = argparse.Namespace(workspace=str(ws), state=str(sp), text_id="x", cv=str(ws), book_text=str(ws),
                           books="vol20-vol24", batch_size=6, dry_run=True)
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        swap.cmd_run(a)
    out = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert out["publish_only"] == ["vol20", "vol21"]
    assert out["todo"] == ["vol23", "vol24"]


def test_data_problem(tmp_path):
    assert "待收字登记表" in swap.data_problem(tmp_path) and "语料" in swap.data_problem(tmp_path)
    (tmp_path / "config" / "pua").mkdir(parents=True)
    (tmp_path / "config" / "pua" / "glyph_pending_codes.json").write_text("[]")
    assert "待收字登记表" not in swap.data_problem(tmp_path)
    (tmp_path / "corpus" / "daizhige").mkdir(parents=True)
    (tmp_path / "corpus" / "daizhige" / "0001.jsonl").write_text("{}\n")
    assert swap.data_problem(tmp_path) is None


def test_parse_books_numeric_and_chapter():
    from guji_manager import swap as S
    assert S.parse_books("001-003,010") == ["001", "002", "003", "010"]
    assert S.parse_books("01-02") == ["01", "02"]
    assert S.parse_books("vol9-vol10") == ["vol09", "vol10"]
    assert S.chapter_of("vol07") == "007" and S.chapter_of("07") == "007" and S.chapter_of("045") == "045"
    assert S.parse_cycle_log("045\t→ done\t写人裁 3 条")["045"]["verdict"] == "done"


def test_precheck_nondianben_data_problem_not_fatal(tmp_path, monkeypatch, capsys):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("GUJI_ACTOR", "t")
    monkeypatch.setattr("guji_manager.datastore.workcopy.data_dir", lambda w: tmp_path / "dd")
    monkeypatch.setattr(swap, "ledger_counts", lambda dd: {})
    state = {"books": {}}
    swap.precheck(ws, state, "995ejelvk0")          # 全唐文：数据目录没有殿本的数据，不拦
    assert "非殿本，不拦" in capsys.readouterr().err
    try:
        swap.precheck(ws, state)                    # 殿本：照拦
        assert False
    except SystemExit as e:
        assert "待收字登记表" in str(e)


def test_parse_cycle_log_fresh_is_terminal():
    from guji_manager.swap import parse_cycle_log
    r = parse_cycle_log("004\tfresh\t线上单 004-r4 就是基于现在的 main 包出的\n009\tgo\t零票\n009\t→ done\t写人裁 0 条\n")
    assert r["004"]["verdict"] == "fresh"
    assert r["009"]["verdict"] == "done"


def test_parse_cycle_log_waiting_recorded():
    from guji_manager.swap import parse_cycle_log
    r = parse_cycle_log("001\twaiting\t线上单 28 格已投 8，还没投完\n")
    assert r["001"] == {"verdict": "waiting", "why": "线上单 28 格已投 8，还没投完"}


def test_new_main_voids_old_verdict(tmp_path, monkeypatch):
    """状态按册＋主包记：上次 verified 是基于旧 main 的，标了新 main 就重做（全唐文 11-20 d2）。"""
    import argparse, io, contextlib
    sp = tmp_path / "state.json"
    swap.save_state(sp, {"books": {"vol20": {"status": "verified", "main": "c1"},
                                   "vol21": {"status": "verified", "main": "d2"},
                                   "vol22": {"status": "verified"}}})
    monkeypatch.setattr(swap, "precheck", lambda ws, state, *a: None)
    monkeypatch.setattr(swap, "current_main", lambda ws, b: "d2")
    a = argparse.Namespace(workspace=str(tmp_path), state=str(sp), text_id="x", cv=str(tmp_path),
                           book_text=str(tmp_path), books="vol20-vol22", batch_size=6, dry_run=True)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        swap.cmd_run(a)
    out = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert out["todo"] == ["vol20"]          # 旧 main 的 verified 作废；同 main、没记 main 的照旧跳过


def test_auto_clean_only_removes_finished_books(tmp_path):
    from guji_manager.swap import auto_clean
    for b in ("vol01", "vol02"):
        d = tmp_path / "_packs" / "lbl" / b
        d.mkdir(parents=True)
        (d / "x").write_bytes(b"0" * 10)
    state = {"books": {"vol01": {"status": "verified"}, "vol02": {"status": "done"}}}
    auto_clean(tmp_path, state)
    assert not (tmp_path / "_packs" / "lbl" / "vol01").exists()
    assert (tmp_path / "_packs" / "lbl" / "vol02").exists()


def test_cv_supports_defer_sync(tmp_path):
    from guji_manager.swap import _cv_supports_defer_sync
    z = tmp_path / "scripts" / "zhengli"
    z.mkdir(parents=True)
    (z / "auto_cycle.py").write_text("x", encoding="utf-8")
    assert not _cv_supports_defer_sync(tmp_path)
    (z / "auto_cycle.py").write_text('ap.add_argument("--defer-sync")', encoding="utf-8")
    assert _cv_supports_defer_sync(tmp_path)


def test_publish_failure_is_not_verified(tmp_path, monkeypatch):
    """11-24 全唐文 011：proofing-sync 失败却记 verified。发站不是 success 一律 publish-mismatch。"""
    import guji_manager.swap as S
    monkeypatch.setattr(S, "audit_books", lambda *a, **k: None)
    monkeypatch.setattr(S, "publish_batch", lambda books, text_id: "failure")
    monkeypatch.setattr(S, "expected_rev", lambda ws, b, t: "011-r14")
    monkeypatch.setattr(S, "live_rev", lambda t, n: "011-r14")          # 线上碰巧是想要的版本也不算
    state = {"books": {"011": {"status": "done"}}}
    S.publish_and_verify(tmp_path, ["011"], "t", state, tmp_path / "s.json", sync=False)
    assert state["books"]["011"]["status"] == "publish-mismatch"
    monkeypatch.setattr(S, "publish_batch", lambda books, text_id: "success")
    monkeypatch.setattr(S, "wait_live_rev", lambda t, n, w, minutes=6.0: "011-r14")
    S.publish_and_verify(tmp_path, ["011"], "t", state, tmp_path / "s.json", sync=False)
    assert state["books"]["011"]["status"] == "verified"
