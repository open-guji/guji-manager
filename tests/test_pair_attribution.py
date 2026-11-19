"""形近字对归属表（`pair_attribution.py`）：格式校验、缺省、与另四处的一致性核对。"""
import pytest

from guji_manager import pair_attribution as PA


def _t(**pairs):
    return PA.parse({"schema": PA.SCHEMA, "pairs": pairs})


def test_unlisted_pair_defaults_to_shape_and_key_is_order_free():
    t = _t(**{"曰日": {"attr": "context"}})
    assert PA.attr_of(t, "日", "曰")["attr"] == "context"
    assert PA.attr_of(t, "淸", "清") == {"attr": "shape"}
    assert PA.pair_key("清", "淸") == PA.pair_key("淸", "清")


@pytest.mark.parametrize("pairs, msg", [
    ({"日日": {"attr": "context"}}, "两个不同的字"),
    ({"日曰": {"attr": "ctx"}}, "attr"),
    ({"簡𥳑": {"attr": "merge"}}, "to"),
    ({"簡𥳑": {"attr": "merge", "to": "間"}}, "to"),
    ({"日曰": {"attr": "context", "to": "日"}}, "merge"),
    ({"日曰": {"attr": "context", "who": "x"}}, "不认的字段"),
])
def test_parse_rejects_bad_rows(pairs, msg):
    with pytest.raises(ValueError, match=msg):
        _t(**pairs)


def test_parse_rejects_same_pair_twice_and_wrong_schema():
    with pytest.raises(ValueError, match="两遍"):
        _t(**{"日曰": {"attr": "context"}, "曰日": {"attr": "context"}})
    with pytest.raises(ValueError, match="schema"):
        PA.parse({"pairs": {}})


def test_load_missing_file_is_empty_table(tmp_path):
    assert PA.load(tmp_path / "no.yaml") == {}
    f = tmp_path / "t.yaml"
    f.write_text("schema: pair_attribution/1\npairs:\n  簡𥳑: {attr: merge, to: 𥳑}\n", encoding="utf-8")
    assert PA.attr_of(PA.load(f), "簡", "𥳑") == {"attr": "merge", "to": "𥳑"}


def test_check_codepoints_both_directions():
    t = _t(**{"簡𥳑": {"attr": "merge", "to": "𥳑"}, "候𠋫": {"attr": "merge", "to": "候"}, "疏䟽": {"attr": "merge", "to": "䟽"}})
    probs = PA.check(t, codepoints={"簡": "𥳑", "候": "𠋫", "內": "内"})
    got = {(p["pair"], p["problem"][:6]) for p in probs}
    assert (PA.pair_key("候", "𠋫"), "码位表统一记") in got            # 方向反了
    assert (PA.pair_key("內", "内"), "码位表把 內") in got             # 码位表有、归属表没列
    assert any(p["pair"] == PA.pair_key("疏", "䟽") and "码位表没有" in p["problem"] for p in probs)   # 归属表有、码位表没有
    assert not any(p["pair"] == PA.pair_key("簡", "𥳑") for p in probs)


def test_check_classifier_context_list_and_tier():
    clf = {"context": ["日曰", "千干"],
           "pairs": {"淸清": {"a": "淸", "b": "清", "tier": 3}, "壞壤": {"a": "壞", "b": "壤", "tier": "context"},
                     "木本": {"a": "木", "b": "本", "tier": 3}}}
    t = _t(**{"日曰": {"attr": "context"}, "本木": {"attr": "context"}})
    probs = {p["pair"]: p["problem"] for p in PA.check(t, clf=clf)}
    assert "不是文意" in probs[PA.pair_key("千", "干")]
    assert "够终判" in probs[PA.pair_key("木", "本")]
    assert "要人定" in probs[PA.pair_key("壞", "壤")]
    assert PA.pair_key("日", "曰") not in probs and PA.pair_key("淸", "清") not in probs


def test_check_step7_groups():
    t = _t(**{"侯候": {"attr": "context"}, "彝𢑱": {"attr": "merge", "to": "彝"}})
    probs = PA.check(t, ctx_only_groups={"hou": {"侯", "候"}, "mb": {"木", "本"}, "big": {"一", "二", "三"}},
                     provisional={"yi": "彝", "xx": "甲"}, group_members={"yi": {"彝", "𢑱"}, "xx": {"甲", "由"}})
    got = {(p["pair"], p["where"]) for p in probs}
    assert got == {(PA.pair_key("木", "本"), "第 7 步组 mb"), (PA.pair_key("甲", "由"), "暂归一兜底 xx")}


def test_check_nothing_given_checks_nothing():
    assert PA.check(_t(**{"日曰": {"attr": "context"}})) == []
