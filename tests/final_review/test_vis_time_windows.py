"""裁定键窗口按 seed_admit 5c（`_vis_ruling_pass`）当时的状态算（A33 11-20，全唐文 027:59:4:7）。

产物是整遍跑完的状态：5c 之后 consensus_lib 等遍放行的邻格当时还没放，stroke_veto 等遍降审的邻格当时还是放行字。
manager 算出的窗口要与 cv 在 5c 时算的一致，否则写下的裁定键重放时对不上。"""
from types import SimpleNamespace as NS

from open_guji_cv.steps.seed_admit import _clf_ctx, _demote

from guji_manager.final_review.pack import vis_windows, window_diff

W = 20


def _rec(i, ch, admit, channel=None):
    return NS(id=f"027:59:4:{i}", char=ch, admit=admit, channel=channel, provenance="match" if admit else "", doubts=[], evidence={})


def _cv_5c(seq, amap):
    am = {k: (v, None) for k, v in amap.items()}
    return {r.id: (_clf_ctx(seq, am, i, -1, W), _clf_ctx(seq, am, i, 1, W)) for i, r in enumerate(seq)}


def test_late_passes_rolled_back():
    seq = [_rec(1, "甲", True, "ref"), _rec(2, "播", False), _rec(3, "丙", True, "lib"), _rec(4, "曰", False),
           _rec(5, "戊", False), _rec(6, "己", True, "ref"), _rec(7, "庚", False)]
    amap = {"027:59:4:2": "撫", "027:59:4:4": "日", "027:59:4:5": "戊", "027:59:4:7": "康"}
    at_5c = _cv_5c(seq, amap)
    # 5c 之后：consensus_lib 放了 2（字 播）；near_knn gap 放了 5；stroke_veto 降了 3；vis_ruling 放了 7（evict 又降回）
    s = seq[1]
    s.admit, s.channel, s.provenance = True, "consensus_lib", "consensus_lib"
    s = seq[4]
    s.admit, s.channel, s.char, s.evidence = True, "near_knn", "茂", {"near_knn": {"via": "near_gap"}}
    s = seq[2]
    _demote(s, "stroke_veto")
    s.admit, s.channel, s.provenance = False, None, ""
    s = seq[6]
    s.admit, s.channel, s.char = True, "vis_ruling", "庚"
    _demote(s, "evict_review")
    s.admit, s.channel = False, None
    got = vis_windows(seq, amap, W)
    assert {k: v[:2] for k, v in got.items()} == at_5c
    assert got["027:59:4:4"][2] == "日"


def test_early_near_knn_and_early_demote_kept():
    """5c 之前的 near_knn（near 段）放行、5c 之前的降审：产物状态就是 5c 时的状态，不退。"""
    seq = [_rec(1, "甲", True, "near_knn"), _rec(2, "乙", False), _rec(3, "丙", False)]
    seq[0].evidence = {"near_knn": {"votes": 3}}
    seq[2].evidence = {"demoted_from": {"channel": "ref", "by": "witness3"}}
    amap = {"027:59:4:3": "柄"}
    assert {k: v[:2] for k, v in vis_windows(seq, amap, W).items()} == _cv_5c(seq, amap)


def test_vis_ctx_evidence_wins():
    seq = [_rec(1, "甲", True, "consensus_lib"), _rec(2, "乙", False)]
    seq[1].evidence = {"vis_ctx": {"left": "撫", "right": "", "ref": "乙"}}
    assert vis_windows(seq, {}, W)["027:59:4:2"] == ("撫", "", "乙")


def test_window_diff():
    assert window_diff("子撫", "子播", "左") == "左1 撫→播"
    assert window_diff("甲乙", "甲丙丁", "右") == "右2 乙→丙、右3 ∅→丁"
