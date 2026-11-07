"""换单 driver 里不连网的部分：册号展开、分批、账本核对、auto_cycle 输出解析、状态读写。"""

import json

import pytest

from guji_manager import swap


def test_parse_books_expands_ranges_and_dedups():
    assert swap.parse_books("vol20-vol22,vol21,vol30") == ["vol20", "vol21", "vol22", "vol30"]
    with pytest.raises(SystemExit):
        swap.parse_books("20-22")


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
    monkeypatch.setattr(swap, "precheck", lambda ws, state: None)
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


def test_reset_book_text(tmp_path):
    import subprocess
    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)
    git("init", "-q")
    f = tmp_path / "x.json"
    f.write_text("a")
    git("add", "-A")
    git("commit", "-qm", "a")
    f.write_text("b")
    (tmp_path / "new.txt").write_text("keep")
    swap.reset_book_text(tmp_path)
    assert f.read_text() == "a" and (tmp_path / "new.txt").exists()
