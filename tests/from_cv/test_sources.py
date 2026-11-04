"""原图页图（datastore/sources.py）：生成、发布、换页、取回，全部用假 Worker 与本地缓存，不上网。"""
import io
import json
import zipfile

import pytest
from PIL import Image

from open_guji_cv.datastore import sources as S
from open_guji_cv.datastore.client import BlobCache, CentralError


class FakeSrc:
    """只认 /v1/packs（正式桶），按名字只增不改，同名再存回 409。"""
    branch = "main"

    def __init__(self):
        self.objs = {}

    def _call(self, method, path, query=None, data=None, raw=False, **kw):
        import urllib.parse
        assert query["bucket"] == "main"
        if path == "/v1/packs":
            pre = query["prefix"]
            return {"packs": [{"key": k, "bytes": len(v)} for k, v in sorted(self.objs.items()) if k.startswith(pre)]}
        key = urllib.parse.unquote(path[len("/v1/packs/"):])
        if method == "PUT":
            if key in self.objs:
                raise CentralError(409, "exists", key)
            self.objs[key] = data
            return {"key": key}
        if key not in self.objs:
            raise CentralError(404, "not_found", key)
        return self.objs[key]


def _tif(w, h, mode="1", ink=(5, 5)):
    im = Image.new(mode, (w, h), 1 if mode == "1" else 255)
    im.putpixel(ink, 0)
    b = io.BytesIO()
    im.save(b, "TIFF")
    return b.getvalue()


def _zip(tmp_path, leaves):
    p = tmp_path / "x_tif.zip"
    with zipfile.ZipFile(p, "w") as z:
        for i, data in enumerate(leaves, 1):
            z.writestr(f"x_tif/x_{i:04d}.tif", data)
    return p


def _publish(src, pages, blobs, uploaded, **kw):
    t = S.new_table("96mid1ogzk", "11", ws="ws-x", book="vol11", sources=[], pages=pages, **kw)
    return S.publish(src, t, blobs, by="test", why="t", upload=lambda b: uploaded.update(b))


def test_spreads_finds_fold_in_margins(tmp_path):
    """对开图：书脊折痕在天头地脚里是唯一的暗线；版框里另画一条更黑的竖线，不能被它带偏。"""
    from PIL import ImageDraw

    from guji_manager.datastore import spreads as SP
    W, H, fold = 1000, 700, 520
    im = Image.new("L", (W, H), 225)
    d = ImageDraw.Draw(im)
    d.rectangle([60, 100, fold - 8, 620], outline=20, width=6)           # 右半叶版框
    d.rectangle([fold + 8, 100, W - 60, 620], outline=20, width=6)       # 左半叶版框
    d.line([(fold - 30, 100), (fold - 30, 620)], fill=0, width=8)        # 版框里的栏线（更黑）
    d.line([(fold, 0), (fold, H)], fill=150, width=3)                    # 折痕（浅）
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "PNG")
    cover = io.BytesIO()
    Image.new("RGB", (400, 700), "white").save(cover, "PNG")
    z = tmp_path / "leaves.zip"
    with zipfile.ZipFile(z, "w") as zz:
        zz.writestr("s_0001.png", cover.getvalue())                     # 书衣单页：不拆
        zz.writestr("s_0002.png", buf.getvalue())
    rows, diag = SP.detect(z, "01")
    assert [r["canvas_seq"] for r in rows] == ["0002a", "0002b"]
    x = rows[1]["xywh"][2]
    assert abs(x - fold) <= 4 and rows[0]["xywh"] == [x, 0, W - x, H]
    assert not diag[0]["weak"]
    SP.sheet(z, diag, tmp_path / "sheet.png")
    assert (tmp_path / "sheet.png").exists()
