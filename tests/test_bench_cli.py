"""`guji bench`（bench/cli.py、resources.py）：no_gold、缺资源报 skipped、跑完落统一结果、ab 翻转、不收 update。自造数据。"""
from __future__ import annotations

import argparse
import json

import pytest

pytest.importorskip("open_guji_cv.eval.bench")
from open_guji_cv.eval import bench as B  # noqa: E402

from guji_manager.bench import cli, legacy  # noqa: E402
from guji_manager.bench import resources as R  # noqa: E402


@pytest.fixture
def fake(tmp_path, monkeypatch):
    ds = tmp_path / "ds"
    (ds / "fake" / "bk").mkdir(parents=True)
    (ds / "fake" / "bk" / "items.json").write_text(json.dumps([{"id": 1, "ok": True}, {"id": 2, "ok": True}]))

    def run(ctx):
        return ctx.work

    def score(ctx, pred):
        items = json.loads((__import__("pathlib").Path(ctx.res["gold"]) / "items.json").read_text())
        if ctx.params:
            items[0]["ok"] = False
        acc = sum(x["ok"] for x in items) / len(items)
        return B.BenchResult("t-fake", ctx.book, ctx.vols, {"acc": acc, "bad": len(items) - acc * len(items)}, "acc",
                             items=items)
    spec = B.BenchSpec(id="t-fake", title="假", steps=("s",), owner="CV0", gold={"bk": "fake/bk"}, needs=("gold",),
                       primary="acc", run=run, score=score, guards=(B.Guard("bad", "max", 0),))
    B._load()
    monkeypatch.setitem(B._REGISTRY, "t-fake", spec)
    return spec, ds, tmp_path


def _args(ds, tmp, **kw):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command")
    cli.add_parser(sub)
    argv = ["bench", kw.pop("action", "run"), *kw.pop("bench", ["t-fake"]), "--dataset", str(ds),
            "--cache", str(tmp / "cache"), "--out", str(tmp / "out"), *kw.pop("extra", [])]
    return p.parse_args(argv)


def test_run_writes_result(fake):
    spec, ds, tmp = fake
    a = cli._fix(_args(ds, tmp, extra=["--book", "bk"]))
    r, out = cli.run_one(spec, "bk", a)
    assert r.status == "ok" and r.metrics["acc"] == 1.0
    d = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert d["schema"] == B.SCHEMA and d["primary"] == {"name": "acc", "value": 1.0} and d["env"]["book"] == "bk"
    assert (out / "items.jsonl").exists() and (out / "report.md").exists()
    r2, _ = cli.run_one(spec, "bk", a, against=out)
    assert r2.against["worse"] == 0 and r2.against["better"] == 0


def test_no_gold_and_missing(fake, monkeypatch):
    spec, ds, tmp = fake
    a = cli._fix(_args(ds, tmp, extra=["--book", "zz"]))
    r, _ = cli.run_one(spec, "zz", a)
    assert r.status == "no_gold"
    monkeypatch.setattr(R, "check_env", lambda needs: [R.Missing("torch", "没装 torch")])
    r, _ = cli.run_one(spec, "bk", a)
    assert r.status == "skipped" and "torch" in r.reason


def test_ab_flags_worse(fake):
    spec, ds, tmp = fake
    a = cli._fix(_args(ds, tmp, action="ab", extra=["--book", "bk", "--params", '{"x": 1}']))
    with pytest.raises(SystemExit) as e:
        cli.cmd_ab(a)
    assert e.value.code == 1
    runs = sorted((tmp / "out" / "t-fake" / "bk").glob("*-B"))
    d = json.loads((runs[-1] / "result.json").read_text(encoding="utf-8"))
    assert d["against"]["worse"] == 1 and d["status"] == "regressed"


def test_run_refuses_update(fake):
    _, ds, tmp = fake
    a = cli._fix(_args(ds, tmp, extra=["--book", "bk", "--arg", "update=1"]))
    with pytest.raises(SystemExit) as e:
        cli.cmd_run(a)
    assert "不写正式数据" in str(e.value.code)


def test_legacy_detection(fake):
    assert not legacy.is_legacy("t-fake")
    assert not legacy.is_legacy("no-such-thing")


def test_registered_and_in_pipeline_step():
    from guji_manager import commands, steps
    assert "bench" in commands.COMMANDS and steps.STEP_OF["bench"] == "pipeline"


def test_publish_to_sqlite(fake, monkeypatch):
    spec, ds, tmp = fake
    monkeypatch.setenv("GUJI_DATA_SQLITE", str(tmp / "c.db"))
    from guji_manager.bench import publish as P
    from guji_manager.datastore import d1conn
    a = cli._fix(_args(ds, tmp, extra=["--book", "bk"]))
    r, out = cli.run_one(spec, "bk", a)
    conn = d1conn.connect()
    rid = P.publish(out, conn=conn, baseline=True, note="基线")
    assert P.publish(out, conn=conn) == rid                  # 同一次再发不重写
    h = P.history("t-fake", "bk", conn=conn)
    assert len(h) == 1 and h[0]["baseline"] == 1 and h[0]["primary_value"] == 1.0 and h[0]["status"] == "ok"


def test_guard_fails_on_unverified(fake, monkeypatch):
    spec, ds, tmp = fake
    import dataclasses
    s2 = dataclasses.replace(spec, guards=(B.Guard("not_there", "max", 0),))
    monkeypatch.setattr(B, "all_specs", lambda: [s2])
    a = cli._fix(_args(ds, tmp, action="guard", bench=[]))
    with pytest.raises(SystemExit) as e:
        cli.cmd_guard(a)
    assert e.value.code == 1


def test_baseline_keeps_only_latest(fake, monkeypatch):
    spec, ds, tmp = fake
    monkeypatch.setenv("GUJI_DATA_SQLITE", str(tmp / "c2.db"))
    from guji_manager.bench import publish as P
    from guji_manager.datastore import d1conn
    a = cli._fix(_args(ds, tmp, extra=["--book", "bk"]))
    conn = d1conn.connect()
    _, o1 = cli.run_one(spec, "bk", a, tag="x")
    _, o2 = cli.run_one(spec, "bk", a, tag="y")
    P.publish(o1, conn=conn, baseline=True)
    P.publish(o2, conn=conn, baseline=True)
    h = {x["run_id"].rsplit("-", 1)[1]: x["baseline"] for x in P.history("t-fake", "bk", conn=conn)}
    assert h == {"x": 0, "y": 1}
