"""`guji bench run --job`：任务库单型 kind=bench（GM2 2026-11-28）。自造数据，不连库。"""
from __future__ import annotations

import argparse
import json

import pytest

from guji_manager.jobs import spec as SP

C1 = "b" * 40


def norm(**kw):
    return SP.normalize(kw, resolve=lambda ref: C1)


def test_bench_spec_normalizes_and_readonly():
    s = norm(kind="bench", cv="dev", bench={"id": "cut-2d", "book": "988g3f0wsu", "vols": "01,02", "args": {"set": "small"}})
    assert s["bench"] == {"id": "cut-2d", "book": "988g3f0wsu", "vols": ["01", "02"], "params": None,
                          "args": {"set": "small"}, "label": None, "dataset": None, "publish": False,
                          "baseline": False, "note": None}
    assert s["book"] is None and s["output"]["pack"] is False and s["run"] is None and s["base"] is None
    assert "bench cut-2d · 988g3f0wsu（01,02）" in SP.summary(s)


@pytest.mark.parametrize("extra,msg", [
    ({"book": "vol01"}, "只读"),
    ({"output": {"pack": True}}, "只读"),
    ({"run": [["eval", "run"]]}, "run 只给"),
])
def test_bench_spec_refuses_writes(extra, msg):
    with pytest.raises(SP.SpecError, match=msg):
        norm(kind="bench", cv="dev", bench={"id": "x", "book": "988g3f0wsu"}, **extra)


@pytest.mark.parametrize("b,msg", [
    ({"book": "988g3f0wsu"}, "bench.id"),
    ({"id": "x"}, "bench.book"),
    ({"id": "x", "book": "988g3f0wsu", "args": {"update": "1"}}, "update"),
    ({"id": "x", "book": "988g3f0wsu", "baseline": True}, "publish"),
    ({"id": "x", "book": "988g3f0wsu", "foo": 1}, "只收"),
])
def test_bench_spec_rejects(b, msg):
    with pytest.raises(SP.SpecError, match=msg):
        norm(kind="bench", cv="dev", bench=b)


def test_other_kinds_unchanged():
    s = norm(kind="rerun", book="vol10", cv="v0.5.16")
    assert "bench" not in s
    with pytest.raises(SP.SpecError, match="kind=bench"):
        norm(kind="rerun", book="vol10", cv="v", bench={"id": "x", "book": "988g3f0wsu"})


def test_bench_args_in_hash():
    a = norm(kind="bench", cv="v", bench={"id": "decide", "book": "988g3f0wsu", "args": {"set": "small"}})
    b = norm(kind="bench", cv="v", bench={"id": "decide", "book": "988g3f0wsu", "args": {"set": "large"}})
    assert SP.spec_hash(a) != SP.spec_hash(b)


def _job(tmp_path, bench, write_result):
    from guji_manager.jobs import runner as R
    j = object.__new__(R.Job)
    j.spec = norm(kind="bench", cv="v", bench=bench)
    j.dry, j.id, j.aid, j.ws, j.dir = False, 7, 1, None, tmp_path
    j.evs, j.res, j.calls = [], [], []
    j.ev = lambda msg, **k: j.evs.append(msg)
    j.db = lambda fn, *a, **k: j.res.append((a[2], a[3], k.get("data")))

    def guji(*args, **kw):
        j.calls.append((args, kw))
        write_result(tmp_path / "bench-results")
        return ""
    j.guji = guji
    return j


def _write(status, items=3):
    def w(root):
        out = root / "cut-2d" / "988g3f0wsu" / "20261128-120000"
        out.mkdir(parents=True)
        (out / "result.json").write_text(json.dumps({"bench": "cut-2d", "book": "988g3f0wsu", "status": status,
                                                     "primary": {"name": "col_ok", "value": 0.9}, "n": items,
                                                     "reason": "缺资源 raw" if status == "skipped" else ""}))
        (out / "report.md").write_text("# r\n")
        (out / "items.jsonl").write_text("".join(json.dumps({"id": i}) + "\n" for i in range(items)))
    return w


def test_runner_bench_writes_result(tmp_path):
    j = _job(tmp_path, {"id": "cut-2d", "book": "988g3f0wsu", "vols": ["01"], "args": {"set": "small"},
                        "params": {"x": 1}, "publish": True, "baseline": True, "note": "基线"}, _write("regressed"))
    j.run_bench()
    args, kw = j.calls[0]
    assert args[:5] == ("bench", "run", "cut-2d", "--book", "988g3f0wsu")
    assert args[args.index("--vol") + 1] == "01" and args[args.index("--arg") + 1] == "set=small"
    assert "--publish" in args and "--baseline" in args and args[args.index("--note") + 1] == "基线"
    assert kw["ok"] == (0, 1) and kw["write"] is True                 # regressed 退出码 1 也要收结果
    (kind, name, data), = j.res
    assert kind == "output" and name == "bench cut-2d · 988g3f0wsu"
    assert data["result"]["status"] == "regressed" and data["report"] == "# r\n" and data["items_total"] == 3
    assert "regressed" in j.evs[-1]


def test_runner_bench_skipped_is_blocked(tmp_path):
    from guji_manager.jobs import runner as R
    j = _job(tmp_path, {"id": "cut-2d", "book": "988g3f0wsu"}, _write("skipped"))
    with pytest.raises(R.StageError) as e:
        j.run_bench()
    assert e.value.outcome == "blocked" and "缺资源" in str(e.value)
    assert j.res and j.calls[0][1]["write"] is False                   # 结果照样写回；不发布就用读令牌


def test_runner_bench_failed(tmp_path):
    from guji_manager.jobs import runner as R
    j = _job(tmp_path, {"id": "cut-2d", "book": "988g3f0wsu"}, _write("failed"))
    with pytest.raises(R.StageError) as e:
        j.run_bench()
    assert e.value.outcome == "failed"


def test_cli_job_dry_run(capsys, monkeypatch):
    from guji_manager.bench import cli
    monkeypatch.setattr(SP, "resolve_cv", lambda ref, *a, **k: C1)
    p = argparse.ArgumentParser()
    cli.add_parser(p.add_subparsers(dest="command"))
    a = cli._fix(p.parse_args(["bench", "run", "cut-2d", "--book", "988g3f0wsu", "--vol", "01", "--arg", "set=small",
                               "--job", "--cv", "dev", "--dry-run"]))
    cli.cmd_run(a)
    out = capsys.readouterr().out
    spec = json.loads(out[:out.index("指纹")])
    assert spec["kind"] == "bench" and spec["cv"] == C1 and spec["bench"]["vols"] == ["01"]
    with pytest.raises(SystemExit, match="--job 不收"):
        cli.cmd_run(cli._fix(p.parse_args(["bench", "run", "cut-2d", "--book", "988g3f0wsu", "--job", "--cv", "dev",
                                           "--ws", "/x"])))
