# -*- coding: utf-8 -*-
"""guji start new：新书仓初始文件。"""
import argparse

import yaml

from guji_manager import cli_new, steps


def _args(tmp_path, **kw):
    d = dict(book_id="98y6h42f41", title="朱楓林集", workspace=str(tmp_path), work_id="d59f2nk861hf",
             ws_repo="guji-workspace/x", project="明别集", force=False, dry_run=False)
    d.update(kw)
    return argparse.Namespace(**d)


def test_new_writes_files_and_valid_yaml(tmp_path):
    assert cli_new.cmd_new(_args(tmp_path)) == 0
    for rel in ("workspace.yaml", ".gitignore", "README.md", "开书进度.yaml", "开书经验.md",
                "layout_profile.yaml", "实验记录/README.md", "日志.md", "tools/.gitkeep"):
        assert (tmp_path / rel).exists(), rel
    assert yaml.safe_load((tmp_path / "workspace.yaml").read_text(encoding="utf-8"))["id"] == "98y6h42f41"
    prog = yaml.safe_load((tmp_path / "开书进度.yaml").read_text(encoding="utf-8"))
    assert prog["book_id"] == "98y6h42f41" and prog["steps"]["1a"]["db_init"]["status"] == "pending"
    yaml.safe_load((tmp_path / "layout_profile.yaml").read_text(encoding="utf-8"))
    ig = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert all(x in ig for x in ("_packs/", "reports/", "perf/"))


def test_new_does_not_overwrite_without_force(tmp_path):
    (tmp_path / "README.md").write_text("mine", encoding="utf-8")
    cli_new.cmd_new(_args(tmp_path))
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "mine"
    cli_new.cmd_new(_args(tmp_path, force=True))
    assert "新会话怎么起" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_new_rejects_bad_id_and_dry_run(tmp_path, capsys):
    assert cli_new.cmd_new(_args(tmp_path, book_id="XYZ")) == 2
    cli_new.cmd_new(_args(tmp_path, dry_run=True))
    assert not (tmp_path / "workspace.yaml").exists()


def test_new_is_start_step_command():
    assert steps.STEP_OF["new"] == "start"
