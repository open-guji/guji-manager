"""存包时产物与铺底包一字不差（取包后一页没跑）记 unchanged_from，标 main 时拦（11-26 全唐文 055、史記 11/28/31/34 空跑）。"""
from __future__ import annotations

import json

import pytest
from test_products_diff_pack import FakeSrc


def test_unchanged_pack_blocked_from_main(tmp_path, monkeypatch):
    from guji_manager.datastore import packs as PK
    monkeypatch.setattr(PK, "_ws_name", lambda: "ws-x")
    root = tmp_path / "products"
    d = root / "055" / "row_segment"
    d.mkdir(parents=True)
    (d / "_manifest.jsonl").write_text('{"page": 1}\n')
    src = FakeSrc()
    vers = {"cv": "0.9.4", "cv_commit": "c" * 40, "corpus": None, "glyph_pin": None, "human_fp": None}
    PK.write_mark(root, "055", "base-a5", "fetch")                     # 铺底：取包后记摘要
    PK.push_products("055", root, label="same", src=src, vers=vers)   # 一页没跑就存
    man = json.loads(src.objs["products/ws-x/055/same/manifest.json"])
    assert man["unchanged_from"] == "base-a5"
    with pytest.raises(ValueError, match="一字不差"):
        PK.promote("055", "same", src=src)
    PK.promote("055", "same", src=src, why="GM2 知情：只换标签")
    ptr = [json.loads(v) for k, v in src.objs.items() if "/main-ptr/" in k]
    assert ptr and ptr[-1]["unchanged_from"] == "base-a5"
    # 跑过（manifest 追加）再存：不记、照常标
    with (d / "_manifest.jsonl").open("a") as f:
        f.write('{"page": 1, "run": 2}\n')
    PK.push_products("055", root, label="ran", src=src, vers=vers)
    assert "unchanged_from" not in json.loads(src.objs["products/ws-x/055/ran/manifest.json"])
    PK.promote("055", "ran", src=src)
