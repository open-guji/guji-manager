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
