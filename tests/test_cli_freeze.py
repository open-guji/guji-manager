"""`guji freeze` 命令层（拆分 P2 第二批从 open-guji-cv tests/test_freeze_register.py 搬来；冻结登记本身的测试留在 cv）。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from open_guji_cv.datastore import packs as PK
from open_guji_cv.ops import freeze_register as FR


def _products(tmp: Path) -> Path:
    root = tmp / "products"
    (root / "vol05" / "seed_admit").mkdir(parents=True)
    (root / "vol05" / "seed_admit" / "p0001.json").write_text('{"a": 1}', encoding="utf-8")
    (root / "vol05" / "seed_admit" / "_manifest.jsonl").write_text("{}\n", encoding="utf-8")
    (root / "vol05" / "_prev").mkdir()
    (root / "vol05" / "_prev" / "old.json").write_text("x", encoding="utf-8")
    return root


def _repo(tmp: Path, *, push: bool = True, tag: bool = True) -> Path:
    origin, repo = tmp / "origin.git", tmp / "cv"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        subprocess.run(["git", "-C", str(repo), "config", k, v], check=True)
    (repo / "f.txt").write_text("1", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "c"], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(origin)], check=True)
    if tag:
        subprocess.run(["git", "-C", str(repo), "tag", "v0.5.10"], check=True)
    if push:
        subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", "HEAD:refs/heads/main"], check=True)
        subprocess.run(["git", "-C", str(repo), "fetch", "-q", "origin"], check=True)
    return repo


def test_cli_repo_points_plan_at_other_checkout(tmp_path, monkeypatch, capsys):
    from guji_manager import cli_freeze
    root = _products(tmp_path)
    repo = _repo(tmp_path)
    monkeypatch.setattr(PK, "_ws_name", lambda: "demo-ws")
    monkeypatch.setattr("open_guji_cv.core.book._book_yaml_path", lambda b: tmp_path / f"{b}.yaml")
    args = SimpleNamespace(book="vol05", version="1.0.0", text_id="96mid1ogzk", text_dir=None, root=str(root),
                           note=None, tag_via=None, execute=False, json=True, repo=str(repo))
    cli_freeze.cmd_freeze(args)
    p, _ = json.JSONDecoder().raw_decode(capsys.readouterr().out)
    assert p["cv"]["version"] == "0.5.10" and p["record"]["cv_commit"] == p["cv"]["commit"]


def test_cli_plan_only(tmp_path, monkeypatch, capsys):
    from guji_manager import cli_freeze
    root = _products(tmp_path)
    monkeypatch.setattr(PK, "_ws_name", lambda: "demo-ws")
    monkeypatch.setattr("open_guji_cv.core.book._book_yaml_path", lambda b: tmp_path / f"{b}.yaml")
    monkeypatch.setattr(FR, "cv_state", lambda repo=None: {"version": "0.5.10", "commit": "c" * 40, "dirty": False, "on_remote": True})
    args = SimpleNamespace(book="vol05", version="1.0.0", text_id="96mid1ogzk", text_dir=None, root=str(root),
                           note=None, tag_via=None, execute=False, json=False)
    cli_freeze.cmd_freeze(args)
    out = capsys.readouterr().out
    assert "只出计划" in out and "freeze/96mid1ogzk-vol05-" in out
    with pytest.raises(SystemExit):
        cli_freeze.cmd_freeze(SimpleNamespace(**{**vars(args), "version": "1"}))
