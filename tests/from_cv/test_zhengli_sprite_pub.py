# -*- coding: utf-8 -*-
"""scripts/zhengli/sprite_pub.py 与 republish.py add-sprites（GUJI-675）：自造原图／cord／待审单，上传换成桩。"""
from __future__ import annotations

from cv_paths import CV_REPO  # cv 仓根（本测试从 cv tests/ 搬来）
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image

SCRIPTS = CV_REPO / "scripts" / "zhengli"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"zl_{name}", SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sp = _load("sprite_pub")
rp = _load("republish")


def _sheet(dir_: Path, name: str, color: int) -> bytes:
    Image.new("L", (96, 96), color).save(dir_ / name, "WEBP", quality=80)
    return (dir_ / name).read_bytes()


def test_upload_fails_loudly_when_a_sheet_is_missing(tmp_path, monkeypatch):
    import guji_manager.datastore.r2 as r2
    monkeypatch.setattr(r2, "upload_files", lambda imgs, bucket, ext: {"uploaded": 1, "put_403": 1})
    with pytest.raises(RuntimeError, match="没传完"):
        sp.upload([{"name": "a.webp", "sha256": "0" * 64}], tmp_path)
    monkeypatch.setattr(r2, "upload_files", lambda imgs, bucket, ext: {"uploaded": 1, "exists": 1})
    assert sp.upload([{"name": "a.webp", "sha256": "0" * 64}], tmp_path)["exists"] == 1


def _ws(tmp_path, monkeypatch):
    ws = tmp_path / "abc123-书"
    raw = tmp_path / "raw-vol06"
    raw.mkdir(parents=True)
    monkeypatch.setattr(rp, "raw_dir", lambda ws_, book: raw)       # 原图目录在工作区里，测试不去拼那个路径
    im = Image.new("L", (200, 300), 255)
    im.paste(0, (20, 20, 40, 40))
    im.save(raw / "1.png")
    export = ws / "reports" / "vol06" / "_export"
    export.mkdir(parents=True)
    boxes = ([10, 10, 40, 40], [10, 60, 40, 40])
    cord = {"pages": [{"page": 1, "image": {"width": 200, "height": 300},
                       "cells": [{"a": "1:1:1", "box": boxes[0]}, {"a": "1:1:2", "box": boxes[1]}]}]}
    (export / "006.cord.json").write_text(json.dumps(cord), encoding="utf-8")
    online = ws / "feedback" / "lists" / "proofing" / "abc123" / "006.pending.json"
    online.parent.mkdir(parents=True)
    online.write_text(json.dumps({"rev": "006-r3", "cells": [
        {"cell": "1:1:1", "review": "pending", "img": {"s": "p0001.webp", "x": 0, "y": 0, "w": 96, "h": 96}},
        {"cell": "1:1:2", "review": "pending", "img": {"s": "p0001.webp", "x": 96, "y": 0, "w": 96, "h": 96}}]}), encoding="utf-8")
    return ws, export, online


