"""失联（租约过期）前几次不占重试额度：执行机整机暂停是平台行为，不是单子的错。"""
from guji_manager.jobs.store import lost_exhausted


def test_lost_within_free_does_not_burn_budget():
    assert not lost_exhausted(3, 3, 3, free=5)       # 3 次全是失联：免计后 0 次


def test_lost_beyond_free_counts():
    assert not lost_exhausted(4, 3, 4, free=2)       # 4-2=2 < 3
    assert lost_exhausted(5, 3, 5, free=2)           # 5-2=3 ≥ 3 用完


def test_real_failures_still_count():
    assert not lost_exhausted(3, 3, 1, free=5)       # 2 次真失败＋1 次失联
    assert lost_exhausted(3, 3, 0, free=5)           # 3 次都不是失联


def test_free_zero_is_old_behaviour():
    assert lost_exhausted(3, 3, 3, free=0)
    assert not lost_exhausted(2, 3, 2, free=0)
