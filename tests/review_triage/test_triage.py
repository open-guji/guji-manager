"""review_triage：格号、分流规则、几何特征、模型（全用合成数据）。"""
import json

import numpy as np
import pytest

from guji_manager.review_triage.cells import CellId, patch_path, skip_reason
from guji_manager.review_triage.rules import is_han, route

cv2 = pytest.importorskip("cv2")
from guji_manager.review_triage.geometry import FEATURE_NAMES, edge_frame_line, features  # noqa: E402


def test_cell_id_and_patch_name(tmp_path):
    c = CellId.parse("02:122:4:11b")
    assert (c.book, c.page, c.col, c.slot, c.half) == ("02", 122, 4, 11, "b")
    assert c.patch_name == "p0122c04s11b.png"
    assert patch_path(tmp_path, "02:122:4:11b") == tmp_path / "02/char_patch/p0122c04s11b.png"
    assert patch_path(tmp_path, "02:122:4:11b", "flat") == tmp_path / "02/p0122c04s11b.png"


def test_skip_reason():
    assert skip_reason("01:5:3:1") == "col_head"
    assert skip_reason("01:5:3:21") == "col_tail"
    assert skip_reason("01:5:3:21", col_len=None) is None
    assert skip_reason("01:5:3:7a") == "jiazhu"
    assert skip_reason("01:5:3:7") is None


def test_is_han():
    assert is_han("史") and is_han("𤣥")
    assert not is_han(None) and not is_han("") and not is_han("\U000f0f5e") and not is_han("ခ")


@pytest.mark.parametrize("cid,ref,p,ocr,want", [
    ("01:5:3:1", "王", 0.0, "王", "skip"),        # 列首
    ("01:5:3:7a", "王", 0.0, "王", "skip"),       # 小注
    ("01:5:3:7", None, 0.0, None, "skip"),        # 无参校字
    ("01:5:3:7", "曰", 0.0, "曰", "skip"),        # 己已巳日曰
    ("01:5:3:7", "王", 0.001, "玉", "pass"),      # 模型有把握，OCR 不同也放
    ("01:5:3:7", "王", 0.5, "玉", "withdraw"),
    ("01:5:3:7", "王", 0.5, "王", "review"),
])
def test_route(cid, ref, p, ocr, want):
    assert route(cid, ref, p, ocr, threshold=0.02)[0] == want


def _char(h=120, w=100):
    g = np.full((h, w), 255, np.uint8)
    g[30:110, 47:53] = 0
    g[70:76, 25:75] = 0
    return g


def test_edge_frame_line():
    g = _char()
    assert edge_frame_line(g) == []
    g[2:8, 5:95] = 0
    assert edge_frame_line(g) == ["top"]
    s = _char(); s[20:26, 25:75] = 0              # 字的上横，紧贴字身
    assert edge_frame_line(s) == []


def test_features_shape():
    f = features(_char())
    assert list(f) == FEATURE_NAMES and all(isinstance(v, float) for v in f.values())
    assert features(np.full((30, 30), 255, np.uint8))["ink"] == 0.0


def test_model_and_threshold(tmp_path):
    pytest.importorskip("sklearn")
    from guji_manager.review_triage.model import Model, cv_scores, table, threshold_for_recall, train
    rng = np.random.default_rng(0)
    rows = []
    for i in range(200):
        g = _char()
        bad = i % 5 == 0
        if bad:
            g[2:8, 5:95] = 0
        rows.append({"id": f"01:{i // 10}:1:{i % 10 + 2}", "label": "bad" if bad else "ok",
                     "f": features(g) | {"ocr_eq": float(rng.random() > 0.3)}})
    y = np.array([r["label"] == "bad" for r in rows])
    p = cv_scores(rows, [r["id"].split(":")[1] for r in rows], use_ocr=True)
    t = threshold_for_recall(p, y, 0.9)
    assert ((p >= t) & y).sum() >= 0.9 * y.sum()
    assert table(p, y, (0.9,))[0]["bad"] == 40
    m = train(rows, True, t)
    m.save(tmp_path / "m.pkl")
    assert Model.load(tmp_path / "m.pkl").score(rows[:3]).shape == (3,)


def test_labels(tmp_path):
    from guji_manager.review_triage.labels import load_review_dir
    (tmp_path / "a.json").write_text(json.dumps({"ok": [["01:2:3:4", "王"]], "bad": ["01:2:3:5"]}))
    assert load_review_dir(tmp_path) == {"01:2:3:4": "ok", "01:2:3:5": "bad"}


def test_sheet(tmp_path):
    from guji_manager.review_triage.sheet import build
    (tmp_path / "01").mkdir()
    for s in (2, 3, 4):
        cv2.imwrite(str(tmp_path / "01" / f"p0005c03s{s}.png"), _char())
    cells = [{"id": f"01:5:3:{s}", "ref": "王"} for s in (2, 3, 4)]
    routes = {"01:5:3:2": {"route": "review", "p_bad": 0.1}, "01:5:3:3": {"route": "pass", "p_bad": 0.0},
              "01:5:3:4": {"route": "review", "p_bad": 0.05}}
    st = build(cells, routes, tmp_path, "t1", tmp_path / "o.html", layout="flat")
    assert st == {"tiles": 2, "chars": 1, "pages": 1, "missing_patch": 0}
    html = (tmp_path / "o.html").read_text(encoding="utf-8")
    assert '"book": "t1"' in html and "/*DATA*/null" not in html
