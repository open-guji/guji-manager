"""`guji snap` 命令层（拆分 P2 第三批从 open-guji-cv tests/test_snap_autoimport.py、test_snap_indexes.py 搬来）。

经 cv 的 `guji` 入口（`cli_v2.main`）跑：本包经入口点 `guji.commands` 并进去，-w 等由 cv 统一处理。
夹具照抄 cv 那边（真 git、假 origin），快照逻辑本身的测试留在 cv。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from guji_manager.snap import gitio, importer as imp, indexes as idx, pack as sp, watch as sw

WS_DIR = "abcdefgh12-測試書"
BOOK = "b1"
STEPS = ["border_detect", "cell_shrink"]


def git(cwd: Path, *args: str) -> str:
    cp = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert cp.returncode == 0, cp.stderr
    return cp.stdout.strip()


def _init(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")


def write_products(products: Path, tag: str, pages=(1, 2, 3), steps=STEPS, rev="c0ffee1") -> None:
    for s in steps:
        d = products / BOOK / s
        d.mkdir(parents=True, exist_ok=True)
        lines = []
        for p in pages:
            key = f"p{p:04d}"
            (d / f"{key}.json").write_text(json.dumps({"v": tag, "page": p}), encoding="utf-8")
            lines.append(json.dumps({"key": key, "fingerprint": f"fp-{tag}-{p}", "params_hash": "ph1",
                                     "code_rev": rev, "status": "ok"}))
        (d / "_manifest.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (d / "_prev").mkdir(exist_ok=True)
        (d / "_prev" / "p0001.json").write_text("old", encoding="utf-8")


@pytest.fixture
def world(tmp_path):
    """假 origin（bare）+ 云端 clone + 服务器 clone + 服务器 cv 仓 + overview 仓。"""
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    _init(seed)
    (seed / WS_DIR / "books").mkdir(parents=True)
    (seed / WS_DIR / "books" / f"{BOOK}.yaml").write_text("id: b1\n", encoding="utf-8")
    (seed / WS_DIR / ".gitignore").write_text("products/\n", encoding="utf-8")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "seed")
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(origin))
    cloud = tmp_path / "cloud"
    server = tmp_path / "server"
    git(tmp_path, "clone", "-q", str(origin), str(cloud))
    git(tmp_path, "clone", "-q", str(origin), str(server))
    for r in (cloud, server):
        git(r, "config", "user.email", "t@t")
        git(r, "config", "user.name", "t")
    # 服务器 cv：A ← B（HEAD），另有一条分叉 X
    cv = tmp_path / "cv"
    _init(cv)
    (cv / "f").write_text("a")
    git(cv, "add", "-A"); git(cv, "commit", "-q", "-m", "A")
    a = git(cv, "rev-parse", "HEAD")
    git(cv, "checkout", "-q", "-b", "side")
    (cv / "f").write_text("x")
    git(cv, "commit", "-qam", "X")
    x = git(cv, "rev-parse", "HEAD")
    git(cv, "checkout", "-q", "main")
    (cv / "f").write_text("b")
    git(cv, "commit", "-qam", "B")
    b = git(cv, "rev-parse", "HEAD")
    overview = tmp_path / "overview"
    _init(overview)
    (overview / "README").write_text("x")
    git(overview, "add", "-A"); git(overview, "commit", "-q", "-m", "init")
    # 服务器上已有旧产物
    write_products(server / WS_DIR / "products", "old")
    return {"tmp": tmp_path, "origin": origin, "cloud": cloud, "server": server, "cv": cv,
            "A": a, "B": b, "X": x, "overview": overview, "state": tmp_path / "state" / "s.json"}


def fake_fresh(calls=None):
    def fn(ws_dir, book, pages):
        if calls is not None:
            calls.append((ws_dir, book, pages))
        n = len(list((Path(ws_dir) / "products" / book / "border_detect").glob("p*.json")))
        return {"border_detect": {"fresh": n, "stale": 0}, "cell_shrink": {"fresh": 0, "stale": n}}
    return fn


def make_pack(w, tag="new", *, stamp="20260927T2000", mode="replace-steps", cv=None, pages=None,
              supersedes=(), compatible_with=(), attachments=(), tamper=False, push=True) -> dict:
    prod = w["tmp"] / f"cloudprod-{stamp}"
    write_products(prod, tag)
    spec = sp.PackSpec(book=BOOK, products_root=prod, ws_dir=w["cloud"] / WS_DIR, pages=pages, mode=mode,
                       supersedes=list(supersedes), cv_commit=cv or w["A"],
                       compatible_with=list(compatible_with), attachments=list(attachments),
                       param_overrides={"cell_shrink": {"use_context": False}}, stamp=stamp,
                       glyph_fingerprint="fp-test", session="test-session")
    tree = w["tmp"] / f"tree-{stamp}"
    m = sp.build_tree(spec, tree)
    if tamper:
        (tree / "products" / BOOK / "border_detect" / "p0002.json").write_text("tampered", encoding="utf-8")
    sp.commit_and_push(w["cloud"], tree, m, push=push)
    return m


def run_watch(w, **kw):
    return sw.watch(ws_repo=w["server"], ws_roots=[w["server"]], cv_repo=w["cv"], state_path=w["state"],
                    overview=w["overview"], push=False, freshness_fn=kw.pop("freshness_fn", fake_fresh()), **kw)


def test_manual_import_cli_writes_state(world, monkeypatch, capsys):
    import sys
    from open_guji_cv import cli_v2
    m = make_pack(world)
    monkeypatch.setattr(imp, "default_freshness", fake_fresh())
    monkeypatch.setattr(sys, "argv", ["guji", "snap", "import", m["branch"], "--ws-repo", str(world["server"]),
                                      "--cv-repo", str(world["cv"]), "--state", str(world["state"])])
    with pytest.raises(SystemExit) as e:
        cli_v2.main()
    assert e.value.code == 0
    assert json.loads(world["state"].read_text())[m["branch"]]["status"] == imp.IMPORTED
    assert run_watch(world)["status"] == "idle"


def test_pack_cli_reads_products_of_given_workspace(world, tmp_path, monkeypatch, capsys):
    """`guji snap pack <book> -w <ws>` 读的是 <ws>/products（没设 GUJI_WORKSPACE 时也是）。"""
    import sys
    from open_guji_cv import cli_v2
    ws = world["cloud"] / WS_DIR
    write_products(ws / "products", "fromws")
    monkeypatch.delenv("GUJI_WORKSPACE", raising=False)
    monkeypatch.delenv("GUJI_PRODUCTS_DIR", raising=False)
    monkeypatch.setattr(sys, "argv", ["guji", "snap", "pack", BOOK, "-w", str(ws), "--cv-commit", world["A"],
                                      "--no-push", "--stamp", "20260927T0444"])
    cli_v2.main()
    out = json.loads(capsys.readouterr().out)
    assert out["files"] == 8 and out["branch"].endswith("T0444")


def test_pack_cli_dry_run_never_pushes(world, monkeypatch, capsys):
    """`guji snap pack --dry-run` 只打印计划：不调 commit/push、假 origin 上不出分支、本地也不建分支（#174）。"""
    import sys
    from open_guji_cv import cli_v2
    prod = world["tmp"] / "cloudprod-dry"
    write_products(prod, "dry")
    called = []
    monkeypatch.setattr(sp, "commit_and_push", lambda *a, **k: called.append("commit_and_push"))
    monkeypatch.setattr(gitio, "push_commit", lambda *a, **k: called.append("push_commit"))
    monkeypatch.delenv("GUJI_PRODUCTS_DIR", raising=False)
    monkeypatch.setattr(sys, "argv", ["guji", "snap", "pack", BOOK, "-w", str(world["cloud"] / WS_DIR),
                                      "--from-products", str(prod), "--cv-commit", world["A"],
                                      "--stamp", "20260928T0300", "--dry-run"])
    cli_v2.main()
    out = json.loads(capsys.readouterr().out)
    assert called == []
    assert out["dry_run"] is True and out["pushed"] is False and out["commit"] is None
    assert out["branch"].startswith("snap/") and out["pages"] == 3 and out["files"] > 0
    assert git(world["origin"], "branch", "--list", "snap/*") == ""
    assert git(world["cloud"], "branch", "--list", "snap/*") == ""


def _npz(tmp: Path, name: str, n: int = 2600) -> Path:
    p = tmp / name
    p.write_bytes(bytes((i * 7) % 256 for i in range(n)))
    return p


def _rare(tmp: Path, key: str) -> idx.IndexFile:
    return idx.IndexFile("rare_emb", key, _npz(tmp, f"emb_{key}.npz"), f"models/r5/emb_{key}.npz", f"t {key}")


def test_import_index_cli_by_branch_name(world, capsys):
    """`guji snap import-index idx/<kind>/<key>`：不经 snap 包直接落位，第二次报已在。"""
    import argparse

    from open_guji_cv import cli_v2
    a = _rare(world["tmp"], "abcdefabcdefabcd")
    idx.publish(world["cloud"], [a], cv_commit=world["A"])
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    cli_v2.register_subcommands(sub)
    argv = ["snap", "import-index", f"idx/rare_emb/{a.key}", "--ws-repo", str(world["server"]),
            "--cv-repo", str(world["cv"])]
    cli_v2.COMMANDS_V2["snap"](parser.parse_args(argv + ["--dry-run"]))
    assert json.loads(capsys.readouterr().out)["status"] == idx.WOULD_PLACE
    cli_v2.COMMANDS_V2["snap"](parser.parse_args(argv))
    assert json.loads(capsys.readouterr().out)["status"] == idx.PLACED
    assert (world["cv"] / a.dest).read_bytes() == a.src.read_bytes()
    cli_v2.COMMANDS_V2["snap"](parser.parse_args(argv))
    assert json.loads(capsys.readouterr().out)["status"] == idx.PRESENT
