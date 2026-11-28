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
    h = {x["run_id"].rsplit("-", 2)[1]: x["baseline"] for x in P.history("t-fake", "bk", conn=conn)}
    assert h == {"x": 0, "y": 1}


# ── 取资源层（GM2 审 #1269 后改） ──────────────────────────────────────
def test_publish_run_id_suffix_utc_and_history_filter(fake, monkeypatch):
    spec, ds, tmp = fake
    monkeypatch.setenv("GUJI_DATA_SQLITE", str(tmp / "c2.db"))
    from guji_manager.bench import publish as P
    from guji_manager.datastore import d1conn
    a = cli._fix(_args(ds, tmp, extra=["--book", "bk"]))
    _, out = cli.run_one(spec, "bk", a)
    row = P.row_of(out)
    assert row["run_id"].startswith(f"t-fake/bk/{out.name}-") and len(row["run_id"].rsplit("-", 1)[1]) == 8
    assert row["ran_at"].endswith("Z") and "T" in row["ran_at"]
    conn = d1conn.connect()
    P.publish(out, conn=conn)
    r2, out2 = cli.run_one(spec, "nobook", a)                # 没金标 → no_gold，也能发，但缺省 history 不列
    assert r2.status == "no_gold"
    P.publish(out2, conn=conn)
    assert P.history("t-fake", "nobook", conn=conn) == []
    assert len(P.history("t-fake", "nobook", conn=conn, all_status=True)) == 1


def test_lock_serializes(tmp_path):
    import threading
    import time as _t
    seen = []

    def hold(tag):
        with R.lock(tmp_path, "bk"):
            seen.append(f"{tag}+")
            _t.sleep(0.3)
            seen.append(f"{tag}-")
    ts = [threading.Thread(target=hold, args=(i,)) for i in "ab"]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert seen[0][0] == seen[1][0] and seen[2][0] == seen[3][0]   # 一个放了另一个才进


def test_book_ws_pull_failure_is_missing(tmp_path, monkeypatch):
    p = tmp_path / "books" / "bk"
    (p / ".git").mkdir(parents=True)                         # 假仓：git pull 一定失败
    with pytest.raises(R.Missing) as e:
        R.book_ws("bk", tmp_path, None, update=True)
    assert e.value.kind == "code"
    assert R.book_ws("bk", tmp_path, None, update=False) == p   # --offline 明说用缓存


def test_drift_blocks_code_warns_cv(monkeypatch, tmp_path):
    import guji_manager.jobs.precheck as PC
    monkeypatch.setattr(PC, "code_problems", lambda n, ws: [f"k{n} 有 drift"] if n == 3 else [])
    pv = {"v1": {"code": [3, "基础配置"], "cv_version": ["0.9.1", "基础配置"]},
          "v2": {"code": [3, "基础配置"], "cv_version": ["0.9.1", "基础配置"]}}
    bad, warn = R.drift(tmp_path, tmp_path, pv, "0.9.16")
    assert bad == ["k3 有 drift"] and warn and "0.9.16" in warn[0]
    bad, warn = R.drift(tmp_path, tmp_path, {"v1": {"code": [None, ""], "cv_version": ["0.9.16", "x"]}}, "0.9.16")
    assert bad == [] and warn == []


def test_central_rebuilds_glyph_db(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("guji_manager._cv.central_marker", lambda ws: {"ws": "w1", "branch": "main"}, raising=False)

    class _R:
        returncode = 0
        stdout = stderr = ""
    monkeypatch.setattr(R.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or _R())
    R.central(tmp_path, tmp_path / "dh", glyph=True)
    R.central(tmp_path, tmp_path / "dh", glyph=False)
    assert "--no-rebuild" not in calls[0] and "--no-glyph" not in calls[0]
    assert "--no-rebuild" in calls[1] and "--no-glyph" in calls[1]


def test_products_fetch_via_tmp(monkeypatch, tmp_path):
    from guji_manager.datastore import packs as P

    def fetch(vol, root, label=None):
        (root / vol).mkdir(parents=True)
        (root / vol / "x.json").write_text("{}")
    monkeypatch.setattr(P, "main_label", lambda vol: "L1")
    monkeypatch.setattr(P, "fetch_products", fetch)
    root, lab = R.products(tmp_path, "bk", "v1", tmp_path)
    assert lab == "L1" and (root / "v1" / "x.json").exists()
    assert not list(root.parent.glob(".tmp-*"))

    def broken(vol, root, label=None):
        (root / vol).mkdir(parents=True)
        raise OSError("断了")
    monkeypatch.setattr(P, "fetch_products", broken)
    with pytest.raises(OSError):
        R.products(tmp_path, "bk", "v2", tmp_path)
    assert not (root / "v2").exists() and not list(root.parent.glob(".tmp-*"))


def test_versions_use_cv_own_describe(monkeypatch):
    """cv 版本走 cv 自己的 describe，不读 importlib.metadata（可编辑安装下是旧号，CV0 11-28）。"""
    import importlib.metadata as md
    from guji_manager import _cv
    monkeypatch.setattr(md, "version", lambda d: "0.0.0-stale")
    monkeypatch.setattr(_cv.core_cv_version, "describe", lambda repo=None: ("9.9.9", "c" * 40))
    v = cli._versions()
    assert v["cv"] == "9.9.9" and v["manager"] != "0.0.0-stale"


def test_dataset_auto_sparse_clone(tmp_path, monkeypatch):
    """没有测试集仓又给了缓存：自动稀疏克隆，只检出要的分片与 guards/；钉了提交就检出那一版。"""
    import subprocess as sp
    src = tmp_path / "src"
    for rel in ("a/bk/x.json", "b/y.json", "guards/g.yaml"):
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text("1")
    g = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(src)]
    sp.run(["git", "init", "-q", str(src)], check=True)
    sp.run([*g, "add", "-A"], check=True)
    sp.run([*g, "commit", "-qm", "1"], check=True)
    c1 = sp.run([*g, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    (src / "a" / "bk" / "x.json").write_text("2")
    sp.run([*g, "commit", "-qam", "2"], check=True)
    sp.run([*g, "config", "uploadpack.allowFilter", "true"], check=True)
    sp.run([*g, "config", "uploadpack.allowAnySHA1InWant", "true"], check=True)
    monkeypatch.setattr(R, "DATASET_REPO", f"file://{src}")
    monkeypatch.setenv("GUJI_DATASET_DIR", str(tmp_path / "nope"))
    d = R.dataset_root(None, cache=tmp_path / "cache", rels=["a/bk"])
    assert (d / "a" / "bk" / "x.json").read_text() == "2" and (d / "guards" / "g.yaml").exists()
    assert not (d / "b").exists()
    d = R.dataset_root(None, cache=tmp_path / "cache", rels=["b"], ref=c1)
    assert (d / "a" / "bk" / "x.json").read_text() == "1" and (d / "b" / "y.json").exists()
    with pytest.raises(R.Missing):
        R.dataset_root(None, rels=["a/bk"])                    # 不给缓存：照旧报缺


def test_bench5b_missing(monkeypatch, tmp_path):
    from guji_manager.eval import bench_bundle as BB
    monkeypatch.setattr(BB, "ensure_bench", lambda *a, **k: (False, "冻结包不在 /x"))
    with pytest.raises(R.Missing) as e:
        R.bench5b()
    assert e.value.kind == "bench5b" and "冻结包不在" in str(e.value)
