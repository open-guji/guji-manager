from guji_manager.feedback import landing_policy as LP


def _v(a, voter, choice="char", char="字"):
    return {"a": a, "voter": voter, "choice": choice, "char": char}


def test_auto_lands_everything():
    votes = [_v("1:1:1", "u1"), _v("1:1:2", "u2")]
    ok, wait = LP.apply_policy(LP.get_policy("auto"), votes)
    assert ok == votes and wait == []


def test_quorum_solo_tier_and_two_member_agreement(tmp_path, monkeypatch):
    import json
    f = tmp_path / "tiers.json"
    f.write_text(json.dumps({"boss": "owner"}), encoding="utf-8")
    monkeypatch.setenv("GUJI_REVIEWER_TIERS", str(f))
    votes = [_v("1:1:1", "boss"),                                   # 高等级一票即定
             _v("1:1:2", "m1"),                                     # 一个普通会员：等
             _v("1:1:3", "m1"), _v("1:1:3", "m2"),                  # 两人同字：落
             _v("1:1:4", "m1", char="甲"), _v("1:1:4", "m2", char="乙")]  # 两人不同字：等
    ok, wait = LP.apply_policy(LP.get_policy("quorum:2"), votes)
    assert {v["a"] for v in ok} == {"1:1:1", "1:1:3"}
    assert [w[0] for w in wait] == ["1:1:2", "1:1:4"]


def test_bad_policy_spec():
    import pytest
    with pytest.raises(SystemExit):
        LP.get_policy("vote")
