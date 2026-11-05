# -*- coding: utf-8 -*-
"""借库的借法（借库参照方案缺口 1、2，2026-11-05）：``workspace.yaml`` 的 ``glyph_lib.borrow`` 条目写对象
``{from, scope, pin}``：只借人裁、钉被借库的字形库快照 g<N>。

不连中心库：被借库用本机造的字形库，钉号副本用假的 source／缓存拼。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from guji_manager.datastore import workcopy as wc
from guji_manager.datastore.workcopy import (BorrowSpec, borrow_dir, borrow_entries, borrow_specs,
                                            local_borrow_stores, parse_borrow, pinned_lender_copy, pinned_tag)


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home"))
    for k in ("GUJI_WORKSPACE", "GUJI_GLYPH_DB", "GUJI_GLYPH_STORE", "GUJI_FEEDBACK_DIR"):
        monkeypatch.delenv(k, raising=False)


def _ws(tmp_path, borrow, central="own-ws"):
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    (ws / "workspace.yaml").write_text("id: own-ws\nglyph_lib:\n  borrow: " + json.dumps(borrow, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    (ws / ".central.json").write_text(json.dumps({"ws": central, "branch": "main"}), encoding="utf-8")
    return ws


def test_parse_borrow_forms():
    assert parse_borrow("qkp") == BorrowSpec("qkp", "all", None)
    assert parse_borrow({"from": "qtw", "scope": "human", "pin": 3}) == BorrowSpec("qtw", "human", 3)
    assert parse_borrow({"from": "qtw"}) == BorrowSpec("qtw")
    assert BorrowSpec("qtw", "human", 3).dir_name == "qtw@g3" and BorrowSpec("qtw").dir_name == "qtw"


@pytest.mark.parametrize("bad, pat", [
    ({"scope": "human"}, "缺 from"),
    ({"from": "x", "color": 1}, "只认 from"),
    ({"from": "x", "scope": "some"}, "scope"),
    ({"from": "x", "pin": 0}, "pin"),
    ({"from": "x", "pin": "3"}, "pin"),
    ({"from": "x", "pin": True}, "pin"),
    ({"from": "/abs/path/store", "pin": 2}, "路径写法不能钉"),
])
def test_parse_borrow_rejects(bad, pat):
    with pytest.raises(SystemExit, match=pat):
        parse_borrow(bad)


def test_borrow_entries_stay_names(tmp_path):
    ws = _ws(tmp_path, ["siku", {"from": "qtw", "scope": "human", "pin": 3}])
    assert borrow_entries(ws) == ["siku", "qtw"]
    assert [b.dir_name for b in borrow_specs(ws)] == ["siku", "qtw@g3"]


def test_borrow_dir_pinned_is_separate_copy(tmp_path):
    ws = _ws(tmp_path, ["siku", {"from": "siku", "pin": 2}])
    live, pinned = (borrow_dir(b, ws) for b in borrow_specs(ws))
    assert live.parts[-3] == "siku" and pinned.parts[-3] == "siku@g2"
    assert live != pinned


def _png(k: int) -> bytes:
    img = np.full((64, 64), 255, np.uint8)
    cv2.rectangle(img, (8 + k, 8), (54, 54 - k), 0, 3)
    return cv2.imencode(".png", img)[1].tobytes()


def _lender(tmp_path):
    """被借库：一例人裁、一例机器入库。"""
    from open_guji_cv.clustering.glyph_db import GlyphDB, export_store
    db = GlyphDB(tmp_path / "lender.db")
    db.set_book_edition("book-lend")
    db.admit_instance("v2:v009:1:1:1", "以", _png(0), provenance="human")
    db.admit_instance("v2:v009:1:1:2", "取", _png(1), provenance="match")
    out = tmp_path / "lender_store"
    export_store(db, out)
    db.close()
    return out


def _own(tmp_path):
    from open_guji_cv.clustering.glyph_db import GlyphDB, export_store
    db = GlyphDB(tmp_path / "own.db")
    db.set_book_edition("book-own")
    db.admit_instance("v2:v001:1:1:1", "令", _png(3), provenance="human")
    out = tmp_path / "own_store"
    export_store(db, out)
    db.close()
    return out


def test_local_borrow_stores_scope_flows_into_rebuild(tmp_path):
    """条目写 scope: human，本机副本照样只借人裁；缺省借法是普通路径。"""
    from open_guji_cv.clustering.glyph_db import GlyphDB, rebuild_from_store
    from open_guji_cv.steps.glyph_match import borrow_fingerprint
    ws = _ws(tmp_path, [{"from": "lend", "scope": "human"}])
    lender = _lender(tmp_path)
    root = wc.borrowed_root("lend", "main") / "output"
    root.mkdir(parents=True)
    (root / "glyph_store").symlink_to(lender, target_is_directory=True)
    extras = local_borrow_stores(ws)
    assert getattr(extras[0], "scope", "all") == "human"
    rebuild_from_store(_own(tmp_path), tmp_path / "m.db", extra_stores=extras)
    db = GlyphDB(tmp_path / "m.db")
    assert {r[0] for r in db.conn.execute("SELECT instance_id FROM borrowed")} == {"v2:v009:1:1:1"}
    db.close()
    assert borrow_fingerprint(tmp_path / "m.db") == "lend#human"
    # 缺省借法：普通路径、全借、库名不带记号
    ws2 = _ws(tmp_path, ["lend"])
    plain = local_borrow_stores(ws2)
    assert type(plain[0]).__name__.endswith("Path") and getattr(plain[0], "scope", "all") == "all"
    rebuild_from_store(_own(tmp_path), tmp_path / "p.db", extra_stores=plain)
    assert borrow_fingerprint(tmp_path / "p.db") == "lend"


def test_local_borrow_stores_missing_copy_asks_for_pull(tmp_path):
    ws = _ws(tmp_path, ["lend"])
    with pytest.raises(SystemExit, match="db pull"):
        local_borrow_stores(ws)


# ---- 钉被借库快照 ----

class _Cache:
    def __init__(self, d: Path):
        self.d = d
        d.mkdir(parents=True, exist_ok=True)

    def put(self, b: bytes) -> str:
        sha = hashlib.sha256(b).hexdigest()
        (self.d / sha).write_bytes(b)
        return sha

    def has(self, sha):
        return (self.d / sha).is_file()

    def path(self, sha):
        return self.d / sha

    def ensure(self, src, shas, bucket="main", ext="txt"):
        return {"missing": [s for s in shas if not self.has(s)]}


def _manifest_for(store: Path, cache: _Cache, *, drop_png: bool = False) -> dict:
    items = []
    for p in sorted(store.rglob("*")):
        if not p.is_file():
            continue
        if drop_png and p.suffix == ".png":
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
        else:
            sha = cache.put(p.read_bytes())
        items.append({"root": "gs", "path": p.relative_to(store).as_posix(), "sha256": sha,
                      "size": p.stat().st_size, "type": "png" if p.suffix == ".png" else "txt"})
    items.append({"root": "borrow:other", "path": "x.jsonl", "sha256": "0" * 64, "size": 1, "type": "txt"})
    return {"version": 1, "n": 3, "digest": "glyph-lenderdigest", "items": items}


@pytest.fixture
def fake_materialize(monkeypatch):
    calls = []

    def fake(src, ws, dest, prefixes, **kw):
        calls.append((ws, prefixes))
        man = src["manifests"].get(prefixes[0])
        if man is None:
            from guji_manager.datastore.materialize import MaterializeError
            raise MaterializeError(f"库里工作区 {ws} 没有 {prefixes} 下的文件")
        p = Path(dest) / prefixes[0]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(man), encoding="utf-8")
        return {}
    import guji_manager.datastore.materialize as M
    monkeypatch.setattr(M, "materialize", fake)
    return calls


def test_pinned_lender_copy_builds_snapshot_store_once(tmp_path, fake_materialize):
    lender = _lender(tmp_path)
    cache = _Cache(tmp_path / "cache")
    src = {"manifests": {"config/glyph-pack/g3/manifest.json": _manifest_for(lender, cache)}}
    d = pinned_lender_copy(src, "lend", 3, "main", cache=cache)
    assert d == "glyph-lenderdigest"
    root = wc.borrowed_root("lend@g3", "main")
    got = sorted(p.relative_to(root / "output" / "glyph_store").as_posix()
                 for p in (root / "output" / "glyph_store").rglob("*") if p.is_file())
    want = sorted(p.relative_to(lender).as_posix() for p in lender.rglob("*") if p.is_file())
    assert got == want                                    # root=gs 的条目全到位，borrow:other 不传递
    assert not (root / "output" / "glyph_store" / "x.jsonl").exists()
    # 第二次不连网（号不变、副本在）
    n = len(fake_materialize)
    assert pinned_lender_copy({"manifests": {}}, "lend", 3, "main", cache=cache) == "glyph-lenderdigest"
    assert len(fake_materialize) == n


def test_pinned_lender_copy_missing_manifest_is_clear(tmp_path, fake_materialize):
    with pytest.raises(SystemExit, match="snapshot"):
        pinned_lender_copy({"manifests": {}}, "lend", 9, "main", cache=_Cache(tmp_path / "c"))
    assert not wc.borrowed_root("lend@g9", "main").exists()


def test_pinned_lender_copy_missing_blob_leaves_nothing(tmp_path, fake_materialize):
    lender = _lender(tmp_path)
    cache = _Cache(tmp_path / "cache")
    src = {"manifests": {"config/glyph-pack/g3/manifest.json": _manifest_for(lender, cache, drop_png=True)}}
    with pytest.raises(SystemExit, match="取不到"):
        pinned_lender_copy(src, "lend", 3, "main", cache=cache)
    assert not wc.borrowed_root("lend@g3", "main").exists()


def test_borrow_stores_pinned_end_to_end(tmp_path, fake_materialize):
    """pin + scope：签名带快照 digest 与 #human；目录是 BorrowedStore；重建出的库指纹带 ~digest。"""
    from open_guji_cv.clustering.glyph_db import rebuild_from_store
    from open_guji_cv.steps.glyph_match import borrow_fingerprint
    lender = _lender(tmp_path)
    cache = _Cache(tmp_path / "cache")
    src = {"manifests": {"config/glyph-pack/g3/manifest.json": _manifest_for(lender, cache)}}
    ws = _ws(tmp_path, [{"from": "lend", "scope": "human", "pin": 3}])
    dirs, sig = wc.borrow_stores(src, ws, cache=cache)
    assert sig == ["lend@g3:glyph-lenderdigest#human"]
    assert (dirs[0].scope, dirs[0].tag) == ("human", "glyph-lenderdigest")
    assert pinned_tag(borrow_specs(ws)[0], ws) == "glyph-lenderdigest"
    rebuild_from_store(_own(tmp_path), tmp_path / "m.db", extra_stores=dirs)
    assert borrow_fingerprint(tmp_path / "m.db") == "lend@g3#human~glyph-lenderdigest"


def test_borrow_stores_pin_on_path_entry_refused(tmp_path):
    ws = tmp_path / "ws2"
    ws.mkdir()
    (ws / "workspace.yaml").write_text("id: x\n", encoding="utf-8")
    # 没迁到中心库的工作区、被借库给了 pin：不静默当成最新
    (ws / "workspace.yaml").write_text("id: x\nglyph_lib:\n  borrow:\n    - {from: lend, pin: 2}\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="钉号"):
        wc.borrow_stores({"manifests": {}}, ws)
