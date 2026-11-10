from guji_manager.swap.resolve import (resolve, detect_flaws, SAME, HUMAN_KEEP, HUMAN_RESTORE, PROTECTED_CONFLICT,
                                       HUMAN_INVALID, NEW_ADMIT, MACHINE_CHANGE, RETURN_TO_BLANK, MACHINE_FLAW,
                                       REMOVED, KEEP, ADOPT, REVIEW, REVERT, PENDING_SAME, PENDING_NO_CHOICE, PENDING_KEEP, EVICT_REVIEW)


def test_human_beats_machine():
    d = resolve("甲", "乙", human="甲")
    assert (d.kind, d.action, d.result, d.auto) == (PROTECTED_CONFLICT, REVIEW, "甲", False)


def test_human_keep_and_restore():
    assert resolve("甲", "甲", human="甲").kind == HUMAN_KEEP
    d = resolve("乙", "甲", human="甲")
    assert (d.kind, d.result) == (HUMAN_RESTORE, "甲")


def test_new_blank_does_not_conflict_with_human():
    # 新包退回 □ 也不能覆盖人裁，保持人裁字
    assert resolve("甲", "□", human="甲").kind == HUMAN_KEEP


def test_human_invalid_goes_to_review():
    d = resolve("甲", "乙", human_invalid=True)
    assert (d.kind, d.action, d.result) == (HUMAN_INVALID, REVIEW, "甲")


def test_new_admit():
    for cur in ("□", None):
        d = resolve(cur, "字")
        assert (d.kind, d.action, d.result) == (NEW_ADMIT, ADOPT, "字")


def test_machine_change_default_admit():
    d = resolve("日", "曰")
    assert (d.kind, d.action, d.result, d.auto) == (MACHINE_CHANGE, ADOPT, "曰", True)


def test_return_to_blank_review_keeps_text():
    d = resolve("字", "□")
    assert (d.kind, d.action, d.result) == (RETURN_TO_BLANK, REVIEW, "字")


def test_flaw_reverts():
    d = resolve("甲", "乙", flaw=True)
    assert (d.kind, d.action, d.result) == (MACHINE_FLAW, REVERT, "甲")


def test_same_and_removed():
    assert resolve("甲", "甲").kind == SAME
    assert resolve("□", "□").action == KEEP
    assert resolve("甲", None).kind == REMOVED


def test_detect_flaws():
    # 99:2:8 式：新包把相邻格都出成「雯」
    assert detect_flaws(list("甲雯乙"), list("甲雯雯")) == {2}
    assert detect_flaws(["甲", "乙"], ["甲", ""]) == {1}
    assert detect_flaws(list("甲乙"), list("甲乙")) == set()


def test_pending_same_first_choice_no_text_change():
    d = resolve("甲", "甲", new_pending=True)
    assert (d.kind, d.action, d.result, d.to_review) == (PENDING_SAME, KEEP, "甲", True)


def test_pending_without_first_choice_keeps_text():
    for new in (None, "", "□"):
        d = resolve("甲", new, new_pending=True)
        assert (d.kind, d.result, d.to_review) == (PENDING_NO_CHOICE, "甲", True)


def test_pending_different_first_choice_keeps_current_text():
    """现行有字、待审首选字不同：文本不动，人裁后再改（sheldon 11-10）。"""
    d = resolve("日", "曰", new_pending=True)
    assert (d.kind, d.action, d.result, d.to_review) == (PENDING_KEEP, KEEP, "日", True)


def test_pending_on_blank_writes_first_choice():
    for cur in ("□", None):
        d = resolve(cur, "曰", new_pending=True)
        assert (d.result, d.to_review) == ("曰", True)


def test_pending_does_not_conflict_with_human():
    d = resolve("甲", "乙", human="甲", new_pending=True)
    assert d.kind == HUMAN_KEEP


def test_true_lacuna_from_machine_goes_to_review():
    d = resolve("字", "□", new_lacuna=True)
    assert (d.kind, d.action, d.result) == (RETURN_TO_BLANK, REVIEW, "字")


def test_evict_review_keeps_current_char():
    # 撤库重审格（sheldon 11-10）：新包放行别的字、退回□、待审，现行有字都不动，进复审单
    for kw in ({}, {"new_pending": True}, {"new_lacuna": True}):
        new = "□" if kw.get("new_lacuna") else "乙"
        d = resolve("甲", new, evict_review=True, **kw)
        assert (d.kind, d.action, d.result, d.to_review) == (EVICT_REVIEW, KEEP, "甲", True)


def test_evict_review_blank_writes_first_choice_and_human_wins():
    d = resolve("□", "乙", evict_review=True)
    assert (d.result, d.to_review) == ("乙", True)
    d = resolve(None, "□", evict_review=True, new_lacuna=True)
    assert (d.kind, d.result) == (PENDING_NO_CHOICE, None)
    d = resolve("甲", "乙", human="乙", evict_review=True)   # 人已再裁
    assert (d.kind, d.result) == (HUMAN_RESTORE, "乙")
