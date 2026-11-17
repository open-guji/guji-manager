from guji_manager.swap.booktext import _retarget_left_punct

CHAR = {"pages": [{"columns": [{"cells": [
    {"a": "92:2:13", "c": "古"}, {"a": "92:2:14a", "c": "川"}, {"a": "92:2:14b", "c": "□"},
    {"a": "92:2:15", "c": "無"}, {"a": "143:9:7", "c": "日"}]}]}]}


def _p(anchor, pre):
    return {"punctuations": [{"mark": "，", "anchor": anchor, "pre_char": pre}]}


def test_lacuna_recognized_same_anchor():
    p = _p("143:9:7", "□")
    left, done = _retarget_left_punct(p, CHAR, [("punct", "#0", "143:9:7", "143:9:7", "，", "ANCHOR_MISS｜校验字变了（非单字替换，也找不到平移位置）：□→日")])
    assert not left and done[0][5] == "□识出字"
    assert p["punctuations"][0] == {"mark": "，", "anchor": "143:9:7", "pre_char": "日"}


def test_lacuna_wrong_char_not_moved():
    p = _p("143:9:7", "□")
    row = ("punct", "#0", "143:9:7", "143:9:7", "，", "ANCHOR_MISS｜校验字变了：□→月")
    left, done = _retarget_left_punct(p, CHAR, [row])
    assert left == [row] and not done and p["punctuations"][0]["pre_char"] == "□"


def test_split_cell_goes_to_last_new_cell():
    p = _p("92:2:14", "則")
    left, done = _retarget_left_punct(p, CHAR, [("punct", "#0", "92:2:14", "", "，", "ADD_DEL｜旧格无对应（删除格）")])
    assert not left and done[0][3] == "92:2:14b"
    assert p["punctuations"][0]["anchor"] == "92:2:14b" and p["punctuations"][0]["pre_char"] == "□"


def test_unrelated_left_stays():
    p = _p("1:1:1", "古")
    row = ("punct", "#0", "1:1:1", "", "，", "ADD_DEL｜旧格无对应（删除格）")
    left, done = _retarget_left_punct(p, CHAR, [row])
    assert left == [row] and not done
