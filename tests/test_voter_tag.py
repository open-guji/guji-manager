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
