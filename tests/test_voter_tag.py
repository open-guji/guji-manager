"""会员 voter（UUIDv7）短标识取随机段，匿名 16 位原样（网站 #924）。"""
from guji_manager.voter import is_member, voter_tag
from guji_manager.opinions.ingest import _hidden


def test_anon_unchanged():
    assert voter_tag("0123456789abcdef") == "0123456789abcdef"
    assert voter_tag(None) == "" and not is_member("0123456789abcdef")


def test_member_uses_random_tail():
    a = "019abc12-3456-7def-8123-456789abcdef"
    b = "019abc12-3456-7aaa-9fff-000000000001"     # 同一阵注册：前 6 位相同
    assert is_member(a) and a[:6] == b[:6]
    assert voter_tag(a) == "f8123456789abcdef"[-16:] and len(voter_tag(a)) == 16
    assert voter_tag(a)[:6] != voter_tag(b)[:6]


def test_hidden_matches_public_member_tag():
    a = "019abc12-3456-7def-8123-456789abcdef"
    hidden = {f"cf|001|v1|3:4:5|{a}"}
    assert _hidden(hidden, "cf|001|v1|3:4:5", a)                  # 中心库全值
    assert _hidden(hidden, "cf|001|v1|3:4:5", voter_tag(a)[:6])   # 公开读短标识
    assert not _hidden(hidden, "cf|001|v1|3:4:5", "zzzzzz")


def test_voter_prev_ident():
    from guji_manager.voter import voter_ident
    from guji_manager.feedback.web_votes import latest_votes
    uid = "01a21b61-03b1-7c9d-bc6a-153a060e15ba"
    old = {"book": "b", "rev": "r1", "a": "1:2:3", "choice": "char", "char": "甲", "voter": uid, "ts": 5}
    new = {**old, "voter": "K7QM2XR9", "voter_prev": uid}
    assert voter_ident(new) == uid and voter_ident({"voter": "K7QM2XR9"}) == "K7QM2XR9"
    got, _ = latest_votes([old, new], "b", "r1")
    assert len(got) == 1


def _code(body: str) -> str:
    from guji_manager.voter import _CODE_ALPHABET as A, _CODE_WEIGHTS as W
    return body + A[sum(w * A.index(c) for w, c in zip(W, body)) % 32]


def test_member_code_recognised_and_distinct_from_anon():
    from guji_manager.voter import is_member_code
    c = _code("K7QM2XR")
    assert len(c) == 8 and is_member_code(c) and is_member(c)
    assert not is_member_code(c[:-1] + ("0" if c[-1] != "0" else "1"))   # 校验位错
    assert not is_member_code("0123456789abcdef") and not is_member("0123456789abcdef")


def test_voter_by_and_draft_row_provenance():
    from guji_manager.voter import voter_by
    from guji_manager.feedback.web_votes import Draft
    c = _code("K7QM2XR")
    uid = "01a21b61-03b1-7c9d-bc6a-153a060e15ba"
    m = {"voter": c, "voter_prev": uid}
    a = {"voter": "0123456789abcdef"}
    assert voter_by(m) == f"member:{c}"                      # 迁移后的票取会员号，不取 voter_prev
    assert voter_by({"voter": uid}).startswith("member:") and len(voter_by({"voter": uid})) == 7 + 16
    assert voter_by(a) == "anon:0123456789abcdef"
    row = Draft("v:1:2:3", "1:2:3", {"v": "confirm"}, [m, a, {"voter": c}]).row("网站精校意见")
    assert row["level"] == "human" and row["channel"] == "web_vote"
    assert row["by"] == f"member:{c}、anon:0123456789abcdef"
    assert row["voters"] == {"member": 2, "anon": 1}
