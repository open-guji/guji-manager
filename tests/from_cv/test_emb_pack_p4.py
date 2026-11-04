# -*- coding: utf-8 -*-
"""全字表字形向量包（hanzi 库 B2）：版本只认同规格、按字表逐位复现、以字找字取行。不装 torch 也跑。"""
from __future__ import annotations

import hashlib
import io
import json

import numpy as np
import pytest

from open_guji_cv.clustering import emb_pack as E

SPEC = {"ckpt": "glyph_cnn_r5", "ckpt_fp": "aaaaaaaaaaaa", "font_fp": "bbbbbbbbbbbb",
        "code_fp": "cccccccccccc", "extra": []}


def _npy(a) -> bytes:
    buf = io.BytesIO()
    np.save(buf, a, allow_pickle=False)
    return buf.getvalue()


def _publish(tmp_path, spec=SPEC, chars="一丁七", failed="丂", dim=4, precisions=E.PRECISIONS):
    """造一版包：三种精度的分片（每种分两片）放进假 blob 缓存，清单写进假 emb 目录。"""
    rng = np.random.default_rng(0)
    mat = rng.standard_normal((len(chars), dim)).astype(np.float32)
    files = {}
    for prec in precisions:
        arrays = E.encode(mat, prec)
        for k, sl in enumerate((slice(0, 2), slice(2, None))):          # 分两片，载入时按名拼回
            files[f"{prec}/vectors-{k:02d}.npy"] = _npy(arrays["vectors"][sl])
        if "scale" in arrays:
            files[f"{prec}/scale.npy"] = _npy(arrays["scale"])
    files.update({"chars.txt": "".join(c + "\n" for c in chars).encode(),
                  "failed.txt": "".join(c + "\n" for c in failed).encode()})
    blobs = tmp_path / "blobs"
    meta = {}
    for name, data in files.items():
        sha = hashlib.sha256(data).hexdigest()
        p = blobs / sha[:2] / f"{sha}.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        meta[name] = {"sha256": sha, "bytes": len(data)}
    m = {"version": E.version_of(spec), **spec, "dim": dim, "precisions": list(precisions), "files": meta}
    emb_dir = tmp_path / "emb"
    emb_dir.mkdir(exist_ok=True)
    (emb_dir / f"{m['version']}.json").write_text(json.dumps(m), encoding="utf-8")
    return m, mat, blobs, emb_dir


def test_pull_rare_index_writes_source_and_replaces_foreign_table(tmp_path, monkeypatch):
    """`guji cache pull-rare-index --book`：落表旁写来源；来源不同（本地现建、无记录）的旧表被替换，同来源跳过。"""
    import argparse

    from guji_manager import cli_runs
    from open_guji_cv.clustering import cnn_candidates as cc
    from open_guji_cv.clustering import rare_panel
    from open_guji_cv.steps import align_ref
    m, mat, blobs, emb_dir = _publish(tmp_path)
    monkeypatch.setattr(E, "current_spec", lambda ckpt=None: dict(SPEC))
    monkeypatch.setattr(E, "EMB_DIR", emb_dir)
    monkeypatch.setattr(E, "find", lambda spec, d=emb_dir: m)
    real_load = E.EmbPack.load.__func__
    monkeypatch.setattr(E.EmbPack, "load", classmethod(
        lambda cls, man, blob_dir=None, fetch=None, download=True, precision="int8":
        real_load(cls, man, blobs, fetch, download, precision)))
    monkeypatch.setattr(rare_panel, "book_charsets", lambda book, corpus: (tuple("七一"), (), {}))
    monkeypatch.setattr(align_ref, "book_corpus", lambda book: None)
    f = tmp_path / "emb_k.npz"
    monkeypatch.setattr(cc.CnnCandidates, "emb_index_key", lambda self, cs: ("k", f, {}))
    args = argparse.Namespace(book="b", precision=None)

    cc._save_emb_index(f, np.zeros((2, 4), np.float32), ["七", "一"])        # 本地现建的旧表，没有来源记录
    cli_runs._cmd_cache_pull_rare_index(args)
    side = json.loads(f.with_name(f.name + ".source.json").read_text(encoding="utf-8"))
    assert side == {"emb": m["version"], "precision": "int8"}
    with np.load(f) as z:
        assert list(z["chars"]) == ["七", "一"]
        assert np.array_equal(z["mat"], E.roundtrip(mat[[2, 0]], "int8"))      # 换成了包里的 8 位行
    stamp = f.stat().st_mtime_ns
    cli_runs._cmd_cache_pull_rare_index(args)                                     # 同来源：跳过
    assert f.stat().st_mtime_ns == stamp
