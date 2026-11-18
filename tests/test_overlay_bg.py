"""叠图底图切换（彩图／二值／灰度）与二值体检可疑区（cv `utils/binqc.py`，11-18）。"""
import json

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from guji_manager import _cv
from guji_manager.render import overlay as O


class _B:
    id = "tb"


@pytest.fixture
def page(tmp_path, monkeypatch):
    img = np.zeros((120, 200, 3), np.uint8)
    img[:] = (170, 215, 230)
    img[30:60, 120:160] = (40, 40, 200)
    raw = tmp_path / "1.png"
    cv2.imwrite(str(raw), img)
    binp = tmp_path / "bin1.png"
    cv2.imwrite(str(binp), np.full((120, 200), 255, np.uint8))
    binp.with_suffix(".qc.json").write_text(json.dumps(
        {"page": 1, "size": [200, 120], "regions": [{"bbox": [120, 30, 160, 60], "reason": "color_mark", "score": 0.5}]}))
    monkeypatch.setattr(O, "effective_raw_path", lambda b, p: raw)
    monkeypatch.setattr(_cv, "binarized_or_none", lambda book, p: binp, raising=False)
    return img


def test_color_default_is_raw(page):
    assert np.array_equal(O.overlay_base(_B(), 1), page)


def test_bin_and_gray(page):
    b = O.overlay_base(_B(), 1, "bin")
    assert b.shape == page.shape and (b == 255).all()
    g = O.overlay_base(_B(), 1, "gray")
    assert (g[:, :, 0] == g[:, :, 2]).all()


def test_bin_falls_back_when_missing(page, monkeypatch):
    monkeypatch.setattr(_cv, "binarized_or_none", lambda book, p: None, raising=False)
    assert np.array_equal(O.overlay_base(_B(), 1, "bin"), page)


def test_bad_bg_rejected(page):
    with pytest.raises(Exception):
        O.overlay_base(_B(), 1, "sepia")


def test_draw_qc(page):
    img = page.copy()
    assert O.draw_qc(img, "tb", 1) == 1
    assert not np.array_equal(img, page)
