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


def _code(body):
    from guji_manager.voter import _CODE_ALPHABET as A, _CODE_WEIGHTS as W
    return body + A[sum(w * A.index(c) for w, c in zip(W, body)) % 32]


def test_rules_policy(tmp_path, monkeypatch):
    import json
    ed, owner, mem, mem2 = _code("AAAAAAA"), _code("BBBBBBB"), _code("CCCCCCC"), _code("DDDDDDD")
    anon = "0123456789abcdef"
    f = tmp_path / "roster.json"
    f.write_text(json.dumps({ed: "editor", owner: {"tier": "member", "books": ["bk1"]}}), encoding="utf-8")
    monkeypatch.setenv("GUJI_MEMBER_ROSTER", str(f))
    votes = [_v("1", ed),                       # editor：一票即落
             _v("2", owner),                    # 负责 bk1：在 bk1 落
             _v("3", mem), _v("3", mem2),       # 普通会员：缺省不开 quorum，不落
             _v("4", anon)]                     # 匿名：不落
    ok, wait = LP.apply_policy(LP.get_policy("rules"), votes, "bk1")
    assert {v["a"] for v in ok} == {"1", "2"} and [w[0] for w in wait] == ["3", "4"]
    ok, wait = LP.apply_policy(LP.get_policy("rules"), votes, "bk2")     # 别的书：负责人规则不生效
    assert {v["a"] for v in ok} == {"1"}


def test_rules_quorum_excludes_anon(tmp_path):
    import json
    mem, mem2 = _code("CCCCCCC"), _code("DDDDDDD")
    rf = tmp_path / "rules.json"
    rf.write_text(json.dumps({"quorum": 2}), encoding="utf-8")
    pol = LP.get_policy(f"rules:{rf}")
    assert pol.decide("3", [_v("3", mem), _v("3", mem2)]).land
    assert not pol.decide("3", [_v("3", mem), _v("3", "0123456789abcdef")]).land    # 匿名不计入
    rf.write_text(json.dumps({"nope": 1}), encoding="utf-8")
    import pytest
    with pytest.raises(SystemExit):
        LP.get_policy(f"rules:{rf}")


def test_scope_work_and_collection(tmp_path, monkeypatch):
    import json
    a, b, c = _code("EEEEEEE"), _code("FFFFFFF"), _code("GGGGGGG")
    (tmp_path / "r.json").write_text(json.dumps({
        a: {"tier": "member", "books": ["work:W1"]},          # 作品：管名下所有版本
        b: {"tier": "member", "books": ["collection:C9"]},    # 丛书
        c: {"tier": "member", "books": ["ed3"]}}), encoding="utf-8")   # 单个版本
    (tmp_path / "l.json").write_text(json.dumps({
        "ed1": {"work": "W1", "collections": ["C9"]}, "ed2": {"work": "W1"}, "ed3": {"work": "W2"}}), encoding="utf-8")
    monkeypatch.setenv("GUJI_MEMBER_ROSTER", str(tmp_path / "r.json"))
    monkeypatch.setenv("GUJI_BOOK_LINEAGE", str(tmp_path / "l.json"))
    pol = LP.get_policy("rules")
    land = lambda who, book: pol.decide("1", [_v("1", who)], book).land
    assert land(a, "ed1") and land(a, "ed2") and not land(a, "ed3")     # 作品 W1 管 ed1、ed2
    assert land(b, "ed1") and not land(b, "ed2")                        # 丛书 C9 只管 ed1
    assert land(c, "ed3") and not land(c, "ed1")                        # 版本只管自己
    assert not land(a, "unknown")                                       # 查不到归属：只认版本项
