"""页面范围旁车（`datastore/pagemeta.py`）：几何、检测、校验、旁车版本与并入页表。"""
from __future__ import annotations

import json

import numpy as np
import pytest

from guji_manager.datastore import pagemeta as PM

# 殿本四庫總目 vol05 r004 第 4 页（文淵閣，左半叶），取自线上页表
WYG_ROW = {
    "seq": "0004", "page": 4, "sha256": "12" * 32, "bytes": 1, "w": 1835, "h": 2605, "src": "wyg1", "ops": [],
    "djvu_page": 235, "leaf": "上", "half": "左", "printed_page": "1-185",
    "frame": {"pts": {"t_R": [3955.2, 448.4], "t_xr": [2254.1, 436.4], "t_xl": [2081.0, 435.2], "t_L": [369.0, 423.2],
                      "b_R": [3934.6, 2976.9], "b_xr": [2249.0, 2967.1], "b_xl": [2068.9, 2966.1], "b_L": [367.9, 2956.2]},
              "pad": {"t": 36, "b": 36, "o": 36}, "banxin": "pair", "how": "frame"},
}
SOURCES = [{"key": "wyg1", "kind": "commons", "file": "WYG-SKQS-0001.djvu", "commons_title": "File:文淵閣四庫全書 0001冊.djvu"}]


def _table(rows, rev=4):
    return {"schema": "guji-pages/1", "book_id": "96mid1ogzk", "vol": "05", "rev": rev, "status": "final",
            "sources": SOURCES, "pages": rows}


class FakeSrc:
    """只会 list/get/put 的 Worker 替身（`sources._list/_get/_put` 走 `_call`）。"""
    def __init__(self):
        self.k = {}

    def _call(self, method, path, query=None, data=None, raw=False, content_type=None, tries=1):
        import urllib.parse
        if method == "GET" and path == "/v1/packs":
            pre = query["prefix"]
            return {"packs": [{"key": k} for k in self.k if k.startswith(pre)]}
        key = urllib.parse.unquote(path[len("/v1/packs/"):])
        if method == "PUT":
            self.k[key] = data
            return {}
        return self.k[key]


def test_homography_matches_opencv():
    cv2 = pytest.importorskip("cv2")
    q = [(10.5, 12.0), (990.0, 20.0), (1000.0, 1500.0), (5.0, 1490.0)]
    d = [(0, 0), (900, 0), (900, 1400), (0, 1400)]
    assert np.allclose(PM.homography(q, d), cv2.getPerspectiveTransform(np.float32(q), np.float32(d)), atol=1e-4)


def test_wyg_page_matrix_and_inverse():
    T, (W, H), rect = PM.wyg_geometry(WYG_ROW)
    assert (W, H) == (1835, 2605)            # 与页表 w×h 一致
    # 版框四角（含 pad）→ 页图里的版框矩形
    q = PM._quad(WYG_ROW["frame"]["pts"], "左")
    for pt, tgt in zip(q, [(rect[0], rect[1]), (rect[0] + rect[2], rect[1]),
                           (rect[0] + rect[2], rect[1] + rect[3]), (rect[0], rect[1] + rect[3])]):
        assert PM.apply_h(T, *pt) == pytest.approx(tgt, abs=1e-6)
    meta = PM.build_page(WYG_ROW, _table([WYG_ROW]), src_size=lambda sid: (4296, 6064) if sid == "WYG-SKQS-0001.djvu#235" else None)
    assert meta["src"] == {"id": "WYG-SKQS-0001.djvu#235", "w": 4296, "h": 6064}
    # H 是 P→S：页图 (pad,pad) 角落回到版框左上角 t_L
    assert PM.apply_h(meta["H"], rect[0], rect[1]) == pytest.approx(WYG_ROW["frame"]["pts"]["t_L"], abs=0.01)
    assert PM.validate_page(WYG_ROW, meta) == []
    # content 是版框外扩 1.5% 短边，夹在页图内
    x, y, w, h = meta["content"]
    assert 0 <= x < rect[0] and 0 <= y < rect[1] and x + w <= 1835 and y + h <= 2605


def test_wyg_needs_src_size_and_catches_size_mismatch():
    with pytest.raises(ValueError, match="宽高没给"):
        PM.build_page(WYG_ROW, _table([WYG_ROW]))
    bad = dict(WYG_ROW, w=1800)
    with pytest.raises(ValueError, match="差超过 2 像素"):
        PM.build_page(bad, _table([bad]), src_size=lambda sid: (4296, 6064))


def test_identity_and_crop():
    row = {"seq": "0001", "page": 1, "sha256": "ab" * 32, "w": 800, "h": 1200, "src": "s1:x/1.tif", "ops": []}
    m = PM.build_page(row, _table([row]))
    assert m["H"] == [[1, 0, 0], [0, 1, 0], [0, 0, 1]] and m["src"] == {"id": "sha256:" + "ab" * 32, "w": 800, "h": 1200}
    assert m["content"] == [0, 0, 800, 1200] and m["how"] == "whole"
    crop = {"seq": "0105a", "page": 105, "sha256": "cd" * 32, "w": 2102, "h": 2913, "src": "s1:06061302.cn_tif/06061302.cn_0105.tif",
            "ops": [{"crop": [2096, 0, 2102, 2913]}]}
    with pytest.raises(ValueError, match="宽高没给"):
        PM.build_page(crop, _table([crop]))
    m = PM.build_page(crop, _table([crop]), src_size=lambda sid: (4198, 2913))
    assert m["H"] == [[1, 0, 2096], [0, 1, 0], [0, 0, 1]] and m["how"] == "crop"
    assert PM.validate_page(crop, m) == []


def _page_with_frame(w=1000, h=1400, frame=(100, 120, 800, 1160), text=True):
    g = np.full((h, w), 255, np.uint8)
    x, y, fw, fh = frame
    g[y:y + 6, x:x + fw] = 0                      # 上框线
    g[y + fh - 6:y + fh, x:x + fw] = 0            # 下框线
    g[y:y + fh, x:x + 6] = 0                      # 左
    g[y:y + fh, x + fw - 6:x + fw] = 0            # 右
    if text:
        for cx in range(x + 60, x + fw - 60, 90):
            g[y + 40:y + fh - 40, cx:cx + 30] = 0  # 一列列「字」
    return g


def test_detect_content_finds_frame_and_whole_without_lines():
    g = _page_with_frame()
    x, y, w, h = PM.detect_content(g)
    m = 0.015 * 1000
    assert abs(x - (100 - m)) <= 8 and abs(y - (120 - m)) <= 8
    assert abs((x + w) - (900 + m)) <= 8 and abs((y + h) - (1280 + m)) <= 8
    blank = np.full((1400, 1000), 255, np.uint8)
    assert PM.detect_content(blank) == [0, 0, 1000, 1400]


def test_validate_page_catches_bad_geometry_and_boxes():
    row = {"seq": "0001", "page": 1, "sha256": "ab" * 32, "w": 800, "h": 1200}
    ok = {"src": {"id": "s", "w": 800, "h": 1200}, "H": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "content": [10, 10, 700, 1100]}
    assert PM.validate_page(row, ok) == []
    off = dict(ok, H=[[1, 0, 500], [0, 1, 0], [0, 0, 1]])
    assert "落到源图外" in PM.validate_page(row, off)[0]
    assert "越出页图" in PM.validate_page(row, dict(ok, content=[10, 10, 900, 1100]))[0]
    assert "没罩住字框" in PM.validate_page(row, ok, boxes=[(5, 50, 30, 30)])[0]
    assert PM.validate_page(row, ok, boxes=[(20, 50, 30, 30)]) == []


def test_publish_versions_and_merge():
    row = {"seq": "0001", "page": 1, "sha256": "ab" * 32, "w": 800, "h": 1200, "src": "s1:x", "ops": []}
    table = dict(_table([row]), vol="05")
    src = FakeSrc()
    pages = PM.build_pages(table)
    m1 = PM.publish_pagemeta(src, table, pages, by="t", why="first")
    assert m1["v"] == 1 and PM.versions(src, "96mid1ogzk", "05", 4) == [1]
    pages["0001"]["content"] = [20, 30, 700, 1100]
    pages["0001"]["how"] = "manual"
    m2 = PM.publish_pagemeta(src, table, pages, by="t", why="manual 覆盖")
    assert m2["v"] == 2 and m2["prev_v"] == 1
    got = PM.read_pagemeta(src, "96mid1ogzk", "05", 4)
    merged = PM.merge_into_table(json.loads(json.dumps(table)), got)
    assert merged["pages"][0]["extent"]["content"] == [20, 30, 700, 1100]
    assert set(merged["pages"][0]["extent"]) == {"src", "H", "content"}
    # 页表那一版换了（页图 sha 变）：旁车不认亲，不静默并
    other = json.loads(json.dumps(table))
    other["pages"][0]["sha256"] = "ef" * 32
    with pytest.raises(ValueError, match="table_sha256"):
        PM.merge_into_table(other, got)
    # 没有旁车：原样返回
    assert "extent" not in PM.merge_into_table(json.loads(json.dumps(table)), None)["pages"][0]
    # 页表 key 的正则不会把旁车当成页表版本
    from guji_manager.datastore import sources as S
    src.k[S.table_key("96mid1ogzk", "05", 4)] = b"{}"
    assert S.revisions(src, "96mid1ogzk", "05") == [4]


def test_publish_refuses_invalid():
    row = {"seq": "0001", "page": 1, "sha256": "ab" * 32, "w": 800, "h": 1200, "src": "s1:x", "ops": []}
    table = _table([row])
    pages = PM.build_pages(table)
    pages["0001"]["H"] = [[1, 0, 900], [0, 1, 0], [0, 0, 1]]
    with pytest.raises(ValueError, match="没过校验"):
        PM.publish_pagemeta(FakeSrc(), table, pages, by="t", why="x")
