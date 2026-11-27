"""国内书影（COS srcbw）：命名与网站仓一致、宽度解析、闸、计划、出图、账与出口核。"""
import hashlib
import io
import zipfile

import pytest
from PIL import Image, ImageDraw

from guji_manager.datastore import cos_tier as C
from guji_manager.datastore.pagemeta import table_sha


def _bw_page(w=400, h=600, seed=0):
    im = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(im)
    for i in range(8):
        x = 30 + i * 45 + seed
        d.rectangle([x, 40, x + 12, h - 60], fill=0)
        d.rectangle([x - 8, 100 + i * 30, x + 20, 112 + i * 30], fill=0)
    return im


def _png(im):
    b = io.BytesIO()
    im.convert("RGB").save(b, "PNG")
    return b.getvalue()


def test_slugs_match_web_repo():
    assert C.src_slug("WYG-SKQS-0001.djvu#235") == "WYG-SKQS-0001-235"
    assert C.src_slug("s1:0243_0006.tif") == "s1-0243-0006-tif"
    assert C.src_slug("s1:vol01_0004.jp2") == "s1-vol01-0004-jp2"
    assert C.page_slug("0105a") == "p0105a"
    assert C.cos_key("bk", "01", "x", 1600) == "iiif/bk/01/srcbw/x/full/1600,/0/default.webp"


def test_matrix_matches_live_shiji_manifest():
    # 史記 01 册 0006a 线上 manifest 的 bim:cos（3840 宽，网站仓脚本出的）
    H = [[1, 0, 824], [0, 1, 360], [0, 0, 1]]
    s, w, h = C.scaled_size(4296, 6065, 3840)
    assert (w, h) == (3840, 5421)
    assert C.cos_matrix(H, s) == [1.11875, 0.0, -824.0, 0.0, 1.11875, -360.0, 0.0, 0.0, 1.0]
    assert C.scaled_size(1000, 1500, 3840) == (1.0, 1000, 1500)     # 不放大


def test_resolve_width():
    wyg = {"sources": [{"commons_title": "File:文淵閣四庫全書 0243冊.djvu"}]}
    other = {"sources": [{"commons_title": "File:NAJDA-303-0050 脈経1.pdf"}]}
    assert C.resolve_width(wyg) == (1600, "缺省（文淵閣）")
    assert C.resolve_width(other) == (3840, "缺省")
    assert C.resolve_width(wyg, book_cfg={"src_w": 2400}) == (2400, "书配置 src_w")
    assert C.resolve_width(wyg, 1200, {"src_w": 2400}) == (1200, "--width")


def test_gate():
    ok = C.encode(C.to_bw(_bw_page(), 3840))
    assert C.gate(ok, 3840) == (400, 600)
    with pytest.raises(C.GateError, match="超过"):
        C.gate(ok, 300)
    with pytest.raises(C.GateError, match="尺寸"):
        C.gate(ok, 3840, (400, 601))
    lossy = io.BytesIO()
    _bw_page().save(lossy, "WEBP", quality=80)
    with pytest.raises(C.GateError, match="无损"):
        C.gate(lossy.getvalue(), 3840)
    gray = io.BytesIO()
    Image.new("L", (10, 10), 128).save(gray, "WEBP", lossless=True)
    with pytest.raises(C.GateError, match="黑白"):
        C.gate(gray.getvalue(), 3840)
    with pytest.raises(C.GateError):
        C.gate(b"\x89PNG....", 3840)


def test_to_bw_scales_and_binarizes():
    im = _bw_page(800, 1200)
    out = C.to_bw(im, 400)
    assert out.size == (400, 600)
    assert {v for _, v in out.getcolors(256)} <= {0, 255}
    g = Image.new("L", (100, 100), 200)
    ImageDraw.Draw(g).rectangle([20, 20, 60, 60], fill=40)
    out = C.to_bw(g.convert("RGB"), 3840)
    assert out.size == (100, 100) and out.getpixel((40, 40)) == 0 and out.getpixel((5, 5)) == 255


def _tables():
    page = _png(_bw_page())
    sha = hashlib.sha256(page).hexdigest()
    single = {"book_id": "bk0001", "vol": "005", "rev": 1, "status": "final", "sources": [],
              "pages": [{"seq": "0002", "page": 1, "sha256": sha, "w": 400, "h": 600}]}
    meta_single = {"v": 1, "pages": {"0002": {"src": {"id": f"sha256:{sha}", "w": 400, "h": 600},
                                              "H": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "content": [0, 0, 400, 600]}}}
    return page, sha, single, meta_single


def test_plan_single_and_spread():
    _, sha, single, meta = _tables()
    objs, pages = C.plan(single, meta, 3840)
    assert list(objs) == ["p0002"] and objs["p0002"]["kind"] == "page" and objs["p0002"]["sha256"] == sha
    assert pages["0002"]["matrix"] == [1, 0, 0, 0, 1, 0, 0, 0, 1] and pages["0002"]["width"] == 400
    spread = {"book_id": "bk0002", "vol": "01", "rev": 2, "sources": [{"key": "s1", "file": "x.zip", "sha256": ""}],
              "pages": [{"seq": "0006a", "sha256": "a", "w": 100, "h": 200},
                        {"seq": "0006b", "sha256": "b", "w": 100, "h": 200}]}
    m = {"pages": {"0006a": {"src": {"id": "s1:x_0006.tif", "w": 3000, "h": 2000}, "H": [[1, 0, 1500], [0, 1, 0], [0, 0, 1]]},
                   "0006b": {"src": {"id": "s1:x_0006.tif", "w": 3000, "h": 2000}, "H": [[1, 0, 0], [0, 1, 0], [0, 0, 1.0]]}}}
    m["pages"]["0006b"]["H"] = [[1, 0, 10], [0, 1, 0], [0, 0, 1]]
    objs, pages = C.plan(spread, m, 1500)
    assert list(objs) == ["s1-x-0006-tif"] and objs["s1-x-0006-tif"]["seqs"] == ["0006a", "0006b"]
    assert (objs["s1-x-0006-tif"]["w"], objs["s1-x-0006-tif"]["h"]) == (1500, 1000)
    assert pages["0006a"]["matrix"] == [2.0, 0.0, -1500.0, 0.0, 2.0, 0.0, 0.0, 0.0, 1.0]
    with pytest.raises(ValueError, match="旁车缺"):
        C.plan(spread, {"pages": {"0006a": m["pages"]["0006a"]}}, 1500)


def test_src_ref_and_zip_render(tmp_path):
    t = {"sources": [{"key": "s1", "file": "leaves.zip"}, {"key": "s2", "file": "WYG-0001.djvu"},
                     {"key": "s3", "file": "a.pdf"}]}
    assert C.src_ref(t, "s1:abc_0007.tif")[1] == "abc_0007.tif"
    assert C.src_ref(t, "WYG-0001.djvu#235") == (t["sources"][1], 235)
    assert C.src_ref(t, "s3:vol01_0004.jp2")[1] == 4
    with pytest.raises(ValueError):
        C.src_ref(t, "s9:x_0001.tif")
    z = tmp_path / "leaves.zip"
    b = io.BytesIO()
    _bw_page(800, 1200).save(b, "TIFF")
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("abc_0007.tif", b.getvalue())
    out = C.render_src(z, "abc_0007.tif", 800, 1200, 400)
    assert out.size == (400, 600)
    with pytest.raises(ValueError, match="旁车记的"):
        C.render_src(z, "abc_0007.tif", 801, 1200, 400)


class FakeCos:
    def __init__(self):
        self.store = {}

    def etag(self, key):
        d = self.store.get(key)
        return hashlib.md5(d).hexdigest() if d else None

    def put(self, key, body):
        self.store[key] = body


def test_build_ledger_and_check(tmp_path):
    page, _, single, meta = _tables()
    cos = FakeCos()
    objs = C.build(None, single, meta, 3840, cache=tmp_path, page_png=lambda s: page, upload=cos, log=lambda m: None)
    assert list(cos.store) == ["iiif/bk0001/005/srcbw/p0002/full/3840,/0/default.webp"]
    _, pages = C.plan(single, meta, 3840)
    led = C.make_ledger(single, meta, 3840, "缺省", objs, pages, by="t", why="t", how="upload")
    assert led["table_sha256"] == table_sha(single) and led["objects"]["p0002"]["md5"]
    get = cos.store.get
    assert C.check(single, meta, led, online=1, iou=1, page_png=lambda s: page, get=get) == []
    # 重传同内容跳过
    C.build(None, single, meta, 3840, cache=tmp_path, page_png=lambda s: page, upload=cos, log=lambda m: None)
    # 没账、没旁车
    assert "没有国内书影账" in C.check(single, meta, None)[0]
    assert "旁车" in C.check(single, None, led)[0]
    # 线上被换成别的图
    cos.store[led["objects"]["p0002"]["key"]] = C.encode(C.to_bw(_bw_page(seed=7), 3840))
    errs = C.check(single, meta, led, online=1, get=get)
    assert any("md5" in e for e in errs)
    # 页表多了一页、账没跟上
    t2 = {**single, "pages": single["pages"] + [{**single["pages"][0], "seq": "0003", "page": 2}]}
    m2 = {"pages": {**meta["pages"], "0003": meta["pages"]["0002"]}}
    errs = C.check(t2, m2, led)
    assert any("table_sha256" in e for e in errs) and any("对象数" in e for e in errs)


def test_adopt_reads_online_and_gates():
    _, _, single, meta = _tables()
    good = C.encode(C.to_bw(_bw_page(), 3840))
    objs, bad = C.adopt(single, meta, 3840, get=lambda k: good, log=lambda m: None)
    assert not bad and objs["p0002"]["md5"] == hashlib.md5(good).hexdigest()
    _, bad = C.adopt(single, meta, 3840, get=lambda k: None, log=lambda m: None)
    assert "线上没有" in bad[0]


def test_ink_iou_catches_misplacement():
    P = _bw_page(1000, 1500)
    s, _, _ = C.scaled_size(1000, 1500, 500)
    cos = C.encode(C.to_bw(P, 500))
    M = C.cos_matrix([[1, 0, 0], [0, 1, 0], [0, 0, 1]], s)
    assert C.ink_iou(_png(P), cos, M) > 0.9
    shifted = list(M)
    shifted[2] += 25
    assert C.ink_iou(_png(P), cos, shifted) < 0.5


def test_cos_put_refuses_non_srcbw(monkeypatch):
    monkeypatch.setenv("COS_SECRET_ID", "a")
    monkeypatch.setenv("COS_SECRET_KEY", "b")
    monkeypatch.setenv("COS_BUCKET", "bk-1")
    with pytest.raises(C.GateError):
        C.Cos().put("iiif/bk/01/src/x/full/2400,/0/default.webp", b"x")
