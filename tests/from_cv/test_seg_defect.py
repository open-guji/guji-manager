"""review/seg_defect：切坏检测（离线、只读）的两团字判据。"""
import numpy as np

from guji_manager.review.seg_defect import _valley_split


def _patch(parts, h=200, w=60):
    img = np.full((h, w), 255, np.uint8)
    for y0, y1 in parts:
        img[y0:y1, 10:50] = 0
    return img


def test_two_blobs_with_gap_is_merged():
    assert _valley_split(_patch([(5, 85), (115, 195)]), 100.0)


def test_inner_gap_of_one_char_not_merged():
    # 「二」「三」：字内空行，下面那团矮于 0.3 格高
    assert _valley_split(_patch([(5, 90), (110, 125)]), 100.0) is None
    assert _valley_split(_patch([(5, 195)]), 100.0) is None


def test_frame_residue_on_head_cell():
    """列首格最终字块上还留着断成几截的内框细线：frame_residue；同一字块没有全页线位就不判。"""
    from types import SimpleNamespace as NS

    import numpy as np

    from guji_manager.review.seg_defect import _frame_residue
    patch = np.full((100, 80), 255, np.uint8)
    patch[5:8, 5:35] = 0
    patch[6:9, 40:75] = 0                       # 两截、略斜
    patch[40:90, 30:50] = 0                     # 线下的字
    r = NS(bbox_col=(10.0, 20.0, 90.0, 120.0), sub=None)
    cc = NS(col=3, period=100.0, border_top=10.0, border_bottom=2000.0)
    lines = {"frame_half_lines_top": {3: [(26.5, 3.0)]}}
    assert _frame_residue(patch, r, cc, lines)
    assert _frame_residue(patch, r, cc, {}) is None
    clean = patch.copy()
    clean[:20] = 255
    assert _frame_residue(clean, r, cc, lines) is None


def test_same_char_clip():
    """同字对照：列端字比同字矮一截（宽不缩）才算 clipped；整字压扁、扁字、参照太少都不算。"""
    from guji_manager.review.seg_defect import _ink_h, same_char_clip
    ref = (75.0, 70.0, 30)
    assert same_char_clip(54, 70, ref, 80.0)            # 墨高比 0.72
    assert same_char_clip(62, 72, ref, 80.0) is None    # 0.83，宽比/高比 1.24 不到 1.30
    assert same_char_clip(62, 76, ref, 80.0)            # 0.83，宽比/高比 1.31 → 缺一截
    assert same_char_clip(62, 58, ref, 80.0) is None    # 0.83，宽也缩：整字压扁
    assert same_char_clip(70, 70, ref, 80.0) is None    # 0.93
    assert same_char_clip(8, 70, (13.0, 70.0, 300), 80.0) is None   # 扁字「一」
    assert same_char_clip(54, 70, (75.0, 70.0, 4), 80.0) is None    # 参照不到 5 个
    img = np.full((60, 40), 255, np.uint8)
    img[10:50, 5:30] = 0
    img[55, 3] = 0                                      # 一行只一个墨点不算
    assert _ink_h(img) == 40


def test_edge_line_ink():
    """列端边线压墨：列图上字块框靠版框那条边（列首 y0、列尾 y1-1）[边-2, 边+3)、框宽以内的墨占比。"""
    from guji_manager.review.seg_defect import edge_line_ink
    img = np.full((200, 100), 255, np.uint8)
    img[100:150, 45:55] = 0                             # 一竖从 y=100 起：压在列首格上沿
    box = (0.0, 100.0, 100.0, 150.0)
    assert abs(edge_line_ink(img, box, False) - 30 / 500) < 1e-6
    assert abs(edge_line_ink(img, box, True) - 30 / 500) < 1e-6   # 下沿 149：147–149 三行有墨
    assert edge_line_ink(img, (0.0, 20.0, 100.0, 60.0), False) == 0.0
    img[98:103, 10:90] = 0                              # 截口一片
    assert edge_line_ink(img, box, False) > 0.7
    assert edge_line_ink(None, box, False) == 0.0


def _framed(line_gap=True, wide=True):
    """列尾字块：60 高的竖笔字身，下面一道细横线（框线）。"""
    img = np.full((80, 80), 255, np.uint8)
    img[5:60, 30:50] = 0                                # 字身
    img[60:62, 30:50] = 0
    if not line_gap:
        img[62:75, 30:50] = 0
    x0, x1 = (5, 78) if wide else (30, 50)
    img[75:78, x0:x1] = 0                               # 框线
    return img


def test_end_band():
    """端条：最外 3 行和字身隔开（gap 小）、伸出字身左右（overhang 大）。"""
    from guji_manager.review.seg_defect import end_band
    gap, over = end_band(_framed(), True)
    assert gap == 0.0 and over > 0.6
    gap, over = end_band(_framed(line_gap=False), True)
    assert 0.2 < gap < 0.3                              # 线贴着字脚：往里的行墨＝字身宽÷线宽
    assert end_band(_framed(wide=False), True)[1] == 0.0
    assert end_band(np.full((10, 10), 255, np.uint8), True) is None


def test_same_char_frame():
    """同字对照偏高／墨宽一侧：比同字宽、不矮、端头一道隔开又伸出的横条才算带框。"""
    from guji_manager.review.seg_defect import SAME_PREFIX, same_char_frame
    ref = (60.0, 30.0, 20, 25.0)                        # 墨高中位 60、宽 30、20 个、墨宽 25
    hit = same_char_frame(_framed(), ref, 80.0, True)
    assert hit and hit.startswith(SAME_PREFIX)
    assert same_char_frame(_framed(), ref, 80.0, False) is None        # 看错了一头
    assert same_char_frame(_framed(wide=False), ref, 80.0, True) is None
    assert same_char_frame(_framed(), (60.0, 30.0, 4, 25.0), 80.0, True) is None   # 参照不到 5 个
    assert same_char_frame(_framed(), (60.0, 30.0, 20), 80.0, True) is None       # 老参照没墨宽
    assert same_char_frame(_framed(), (90.0, 30.0, 20, 25.0), 80.0, True) is None  # 比同字矮


def test_gate_rows_and_book_table(tmp_path):
    """--gate 只出同字对照命中的 clipped／frame_residue；书级表按工作区目录名的 id 段查。"""
    from guji_manager.review.seg_defect import book_id_of, book_opts, is_gate_row
    assert is_gate_row({"seg_kind": "clipped", "特征": "同字墨高 0.70 宽 1.00（参照 9 个）"})
    assert is_gate_row({"seg_kind": "frame_residue", "特征": "同字墨宽 1.20 高 1.05（参照 9 个）端条隔开 0.00 伸出 0.40"})
    assert not is_gate_row({"seg_kind": "clipped", "特征": "seam_ink=40"})
    assert not is_gate_row({"seg_kind": "frame_residue", "特征": "下线 30px"})
    assert not is_gate_row({"seg_kind": "bleed", "特征": "同字…"})
    ws = tmp_path / "96mid1ogzk-欽定四庫全書總目武英殿刻本"
    ws.mkdir()
    assert book_id_of(ws) == "96mid1ogzk"
    o = book_opts("96mid1ogzk")
    assert o["frame"] and o["review_kinds"] == ["clipped"]
    assert book_opts("nosuchbook") is None
