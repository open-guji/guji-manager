# -*- coding: utf-8 -*-
"""（拆分 P5 2026-11-04 从 open-guji-cv tests/test_model_pack.py 搬来：上传挪进 `guji_manager.ops.model_upload`。）"""
from __future__ import annotations

import pytest

from open_guji_cv.core import model_pack as mp
from guji_manager.ops import model_upload


@pytest.fixture
def ws(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "models" / "partition_unet_v2").mkdir(parents=True)
    (repo / "models" / "partition_unet_v2" / "model.pt").write_bytes(b"unet")
    (repo / "models" / "README.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(mp, "REPO_ROOT", repo)
    w = tmp_path / "book1"
    (w / "config" / "groups" / "l2model").mkdir(parents=True)
    (w / "config" / "groups" / "l2model" / "jys.json").write_text('{"w": 1}', encoding="utf-8")
    monkeypatch.delenv(mp.DRIFT_ENV, raising=False)
    mp._TOKEN.clear()
    mp._CLEAN.clear()
    return w


def test_upload_refuses_stale(ws):
    mp.build(ws)
    plan = model_upload.upload(ws, 1)
    assert plan["local"] == 2 and not plan["executed"]
    (ws / "config" / "groups" / "l2model" / "jys.json").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        model_upload.upload(ws, 1)


def test_upload_registry_dry_run_matches_repo():
    """cv 自带模型表的文件都在本机时，干跑计划列全表、不上传。"""
    plan = model_upload.upload_registry(kind="model")
    assert plan["registry"] >= 1 and not plan["executed"]
