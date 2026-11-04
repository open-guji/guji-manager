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


def test_template_bank_takes_rows_from_pack(tmp_path, monkeypatch):
    from open_guji_cv.clustering import cnn_candidates as cc
    from guji_manager.review.alt_cands import TemplateBank
    m, mat, blobs, _ = _publish(tmp_path)
    pk = E.EmbPack.load(m, blob_dir=blobs, precision="fp32")

    class FakeCnn:
        ckpt = tmp_path / "other.pt"                                        # 不是现役模型：不挂包
        _net = _dev = None

    bank = TemplateBank(FakeCnn())
    assert bank._pack is None
    bank._pack = pk
    built = []
    monkeypatch.setattr(cc, "build_emb_matrix",
                        lambda net, dev, cs, extra, render: (built.append(cs) or
                                                             (np.zeros((len(cs), 4), np.float32), list(cs))))
    got = bank.vectors(["一", "丂", "万"])
    assert np.array_equal(got["一"], mat[0]) and "丂" not in got           # 失败的字不现算
    assert built == [("万",)]                                              # 只有包外的字现场渲染


