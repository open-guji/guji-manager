"""网站投票人（voter）的短标识。

voter 两种形（网站 #924 起）：匿名是 16 位十六进制（随机）；登录会员是成员 uid＝36 位 UUIDv7（跨设备同一个）。
manager 多处只拿 voter 前几位当身份（意见 id 尾巴、刷票同源、去重、人裁事件里的「意见来源」）。UUIDv7 开头 12 位是
毫秒时间戳，前 6 位相同的范围约 4.6 小时，同一阵注册的会员会撞；所以 UUID 形改取尾部随机段（去掉连字符后的后 16 位）。
匿名形原样不动，已有的 id、事件文字都不变。网站公开接口给的 ``who``（短标识）要用同一规则：``voter_tag(voter)[:6]``。
"""
from __future__ import annotations

import re

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


#: 会员号（网站 docs/membership.md）：8 位＝7 位随机＋1 位校验，Crockford Base32 去 I L O U；与网站 `codeCheckChar` 同算法。
_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_CODE_WEIGHTS = (1, 3, 5, 7, 9, 11, 13)


def is_member_code(voter: str | None) -> bool:
    """是不是会员号（紧凑形，大写、无横线，校验位对）。匿名 voter 是 16 位十六进制，长度就不同，不会混。"""
    c = voter or ""
    if len(c) != 8 or any(ch not in _CODE_ALPHABET for ch in c):
        return False
    return _CODE_ALPHABET[sum(w * _CODE_ALPHABET.index(ch) for w, ch in zip(_CODE_WEIGHTS, c[:7])) % 32] == c[7]


def is_member(voter: str | None) -> bool:
    """登录会员的票：新形＝会员号（8 位），旧形＝成员 uid（UUIDv7，11-27 前有数小时的票）。"""
    return bool(voter) and (bool(_UUID.match(voter)) or is_member_code(voter))


def voter_tag(voter: str | None) -> str:
    """取短标识用的串：会员 uid 取去连字符后的后 16 位（随机段），其余原样。调用方再按需截前 6／16 位。"""
    v = voter or ""
    if _UUID.match(v):
        return v.replace("-", "").lower()[-16:]
    return v


def voter_ident(v: dict) -> str:
    """一票的投票人身份：网站会员号迁移（11-27，36 位 uid → 8 位会员号）后的票带 ``voter_prev``＝原 uid，
    按原值认，与迁移前已导入的票、人裁事件「意见来源」对得上；没有 ``voter_prev`` 就是 ``voter``。"""
    return str(v.get("voter_prev") or v.get("voter") or "")


def voter_by(v: dict) -> str:
    """裁定事件 ``payload.by`` 里这位投票人的写法：会员＝``member:<会员号>``（紧凑形，后台按号反查邮箱）；
    旧 uid 形（没迁成会员号的）＝``member:<uid 随机段 16 位>``；匿名＝``anon:<voter 前 16 位>``。
    会员号只认票上现在的 ``voter``（不取 ``voter_prev``：那是迁移前的 uid）。"""
    voter = str(v.get("voter") or "")
    if is_member_code(voter):
        return f"member:{voter}"
    if is_member(voter):
        return f"member:{voter_tag(voter)}"
    return f"anon:{voter_tag(voter_ident(v))[:16]}"
