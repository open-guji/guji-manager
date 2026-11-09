"""pack_stats：存包时算好人审率分子分母；pack_of 取某包标签的数；progress_sync 认得「存包时已算好的」。"""
import json

from guji_manager import pack_stats as PS
from guji_manager import progress_sync as SY


def mk(root, book, pages):
    d = root / book / "seed_admit"
    d.mkdir(parents=True)
    for i, chars in enumerate(pages):
        (d / f"p{i:03d}.json").write_text(json.dumps({"seed_admit": {"columns": [{"chars": [{"id": f"{i}:{j}", "admit": a} for j, a in enumerate(chars)]}]}}), encoding="utf-8")


def test_count(tmp_path):
    mk(tmp_path, "vol1", [[True, True, False], [False, True]])
    assert PS.count(tmp_path, "vol1") == {"cells": 5, "review": 2}
    assert PS.count(tmp_path, "nope") is None
    (tmp_path / "vol1" / "seed_admit" / "p009.json").write_text("{坏", encoding="utf-8")
    assert PS.count(tmp_path, "vol1") is None       # 有一页读不了，数不准就不写


def test_merged_keeps_recent():
    old = {f"r{i}": {"cells": 10, "review": 1, "at": f"2026-11-0{i}T00:00:00Z"} for i in range(1, 9)}
    d = PS.merged(old, "r9", {"cells": 1000, "review": 2}, "2026-11-09T00:00:00Z")
    assert len(d) == PS.KEEP and "r1" not in d and d["r9"]["rate"] == 0.002


def test_record_skips_partial_and_no_db(tmp_path, monkeypatch):
    mk(tmp_path, "vol1", [[True]])
    monkeypatch.delenv("NEON_DATABASE_URL", raising=False)
    monkeypatch.delenv("GUJI_DATA_PG_DSN", raising=False)
    assert PS.record("vol1", "x", tmp_path) is False
    monkeypatch.setenv("NEON_DATABASE_URL", "postgres://x")
    assert PS.record("vol1", "x", tmp_path, steps=["seed_admit"]) is False   # 只存了几步的包不算整册


def test_pack_of():
    ex = {"cv.packs": {"r7": {"cells": 100, "review": 2, "at": "t"}}, "cv.pack": {"label": "r5", "cells": 90, "review": 3}}
    assert PS.pack_of(ex, "r7")["review"] == 2
    assert PS.pack_of(ex, "r5")["review"] == 3 and PS.pack_of(ex, "r6") is None and PS.pack_of(None, "r7") is None


def test_find_stale_marks_from_packs():
    v = {"book": "b", "vol": "001", "ws": None, "pending_rev": "001-r1",
         "extra": {"a31.main": {"label": "r7"}, "cv.pack": {"label": "r5"}, "cv.packs": {"r7": {"cells": 100, "review": 2}}}}
    st = SY.find_stale([v], {}, {})
    assert st["packs"][0]["from_packs"] is True
    v["extra"].pop("cv.packs")
    assert SY.find_stale([v], {}, {})["packs"][0]["from_packs"] is False


def test_is_pending_excluded_with_human_char():
    """排除名单上人已给字／判残／判非字的不算待审；没人给字的排除格仍算（11-09 用户定）。"""
    ex = lambda **ev: {"admit": False, "doubts": ["excluded"], "evidence": ev}
    assert PS.is_pending({"admit": True}) is False
    assert PS.is_pending({"admit": False, "doubts": ["库 unsure"]}) is True
    assert PS.is_pending(ex(excluded="human:seg_defect", human_char="學")) is False
    assert PS.is_pending(ex(excluded="gate:crop_defect", human_char="開")) is False
    assert PS.is_pending(ex(excluded="human:not_a_char")) is False
    assert PS.is_pending(ex(excluded="human:damaged", damaged=True)) is False
    assert PS.is_pending(ex(excluded="gate:crop_defect")) is True
