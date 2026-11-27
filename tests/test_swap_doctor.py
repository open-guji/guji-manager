"""guji swap doctor：换单开跑前自检（A31 11-18，ZM 换单提速第 3 项）。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from guji_manager.swap import doctor as D


def test_workspace_id_instead_of_path(tmp_path):
    r = D.Report()
    assert D.check_workspace("96mid1ogzk", r) is None
    assert r.failed and "路径" in r.text()


def test_workspace_needs_yaml_and_central(tmp_path):
    r = D.Report()
    assert D.check_workspace(str(tmp_path), r) is None and "workspace.yaml" in r.text()
    (tmp_path / "workspace.yaml").write_text("x: 1\n")
    r = D.Report()
    assert D.check_workspace(str(tmp_path), r) is None and "migrate" in r.text()
    (tmp_path / ".central.json").write_text("{}")
    r = D.Report()
    assert D.check_workspace(str(tmp_path), r) == tmp_path.resolve() and not r.failed


def test_tokens_missing(monkeypatch):
    for k in ("GUJI_DATA_TOKEN", "GUJI_DATA_TOKEN_PROD", "GH_TOKEN", "GITHUB_TOKEN", "CELLREVIEW_TOKEN", "GUJI_ACTOR"):
        monkeypatch.delenv(k, raising=False)
    r = D.Report()
    D.check_tokens(r)
    t = r.text()
    assert r.failed and "GUJI_ACTOR" in t and "gsecrets" in t
    assert "⚠ 令牌 CELLREVIEW_TOKEN" in t        # 可选：只提示不算 ✗
    monkeypatch.setenv("GUJI_DATA_TOKEN_PROD", "x")
    monkeypatch.setenv("GH_TOKEN", "x")
    monkeypatch.setenv("GUJI_ACTOR", "a")
    r = D.Report()
    D.check_tokens(r)
    assert not r.failed          # 没有 CELLREVIEW_TOKEN 也过（0.5.0 起缺省读收件箱）


def test_versions_too_old_warn_not_fail():
    r = D.Report()
    D.check_versions(r, manager="0.4.35", cv="0.6.38")
    t = r.text()
    assert not r.failed and "⚠ manager 版本" in t and "⚠ cv 版本" in t and "0.4.35" in t
    r = D.Report()
    D.check_versions(r, manager="0.6.0", cv="0.9.1")
    assert "⚠" not in r.text()
    r = D.Report()
    D.check_versions(r, manager="0.6.0", cv="dev")      # 读不出版本号不报
    assert "cv 版本" not in r.text()


def test_book_text_sparse_missing_book_dir(tmp_path, monkeypatch):
    bt = tmp_path / "bt"
    bt.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "dev"], cwd=bt, check=True)
    (bt / "scripts").mkdir()
    monkeypatch.setattr(D, "book_dir_rel", lambda tid: "Book/9/6/m/96mid1ogzk")
    r = D.Report()
    D.check_book_text(str(bt), "96mid1ogzk", r, fix=False)
    assert r.failed and "Book/9/6/m/96mid1ogzk" in r.text()
    (bt / "Book/9/6/m/96mid1ogzk").mkdir(parents=True)
    r = D.Report()
    D.check_book_text(str(bt), "96mid1ogzk", r, fix=False)
    assert not r.failed


def test_cv_mismatch(tmp_path):
    (tmp_path / "open_guji_cv").mkdir(parents=True)
    (tmp_path / "open_guji_cv" / "__init__.py").write_text("")
    r = D.Report()
    D.check_cv(str(tmp_path), r)
    assert r.failed and "PYTHONPATH" in r.text()


def test_env_lines(tmp_path):
    lines = D.env_lines(tmp_path / "ws", tmp_path / "cv")
    assert any("PYTHONPATH" in x for x in lines) and any("GUJI_WORKSPACE" in x for x in lines)
