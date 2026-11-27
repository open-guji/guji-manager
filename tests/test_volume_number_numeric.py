"""册号按数值认（用户 11-27 定册号位数按全书册数统一：1–9 册 1 位、10–99 两位、100 起三位）。

迁移前后 1、01、001 并存，比对册号的地方一律按数值认。"""
from guji_manager import pending_stats as ps
from guji_manager.ops.exit_check import find_chapter
from guji_manager.review.vis_review import _by_number


def test_nonbody_lookup_any_width():
    nb = {"001": {"39": "roster"}}
    assert ps._nonbody_for(nb, "001", "001") == {"39": "roster"}
    assert ps._nonbody_for(nb, "1", "1") == {"39": "roster"}
    assert ps._nonbody_for(nb, "01", "01") == {"39": "roster"}
    assert ps._nonbody_for(nb, "002", "002") == {}
    assert ps._nonbody_for(None, "1", "1") == {}
    assert ps.vol_key("007") == "7"


def test_vis_review_by_number():
    lists = {"001": {"cells": [1]}, "012": {"cells": [2]}}
    assert _by_number(lists, "1") == {"cells": [1]}
    assert _by_number(lists, "vol12") == {"cells": [2]}
    assert _by_number(lists, "3") is None


def test_exit_check_find_chapter_any_width():
    index = {"chapters": [{"n": 1, "file": "001"}, {"n": 2, "file": "002"}]}
    assert find_chapter(index, "001")["file"] == "001"
    assert find_chapter(index, "1")["file"] == "001"
    assert find_chapter(index, "02")["file"] == "002"
    assert find_chapter(index, "3") is None
    assert find_chapter({"chapters": [{"n": 5, "file": "5"}]}, "005")["file"] == "5"
