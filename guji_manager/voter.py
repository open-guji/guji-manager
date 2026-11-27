"""网站投票人（voter）的短标识。

voter 两种形（网站 #924 起）：匿名是 16 位十六进制（随机）；登录会员是成员 uid＝36 位 UUIDv7（跨设备同一个）。
manager 多处只拿 voter 前几位当身份（意见 id 尾巴、刷票同源、去重、人裁事件里的「意见来源」）。UUIDv7 开头 12 位是
毫秒时间戳，前 6 位相同的范围约 4.6 小时，同一阵注册的会员会撞；所以 UUID 形改取尾部随机段（去掉连字符后的后 16 位）。
匿名形原样不动，已有的 id、事件文字都不变。网站公开接口给的 ``who``（短标识）要用同一规则：``voter_tag(voter)[:6]``。
"""
from __future__ import annotations

import re

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def is_member(voter: str | None) -> bool:
    return bool(voter) and bool(_UUID.match(voter))


def voter_tag(voter: str | None) -> str:
    """取短标识用的串：会员 uid 取去连字符后的后 16 位（随机段），其余原样。调用方再按需截前 6／16 位。"""
    v = voter or ""
    if _UUID.match(v):
        return v.replace("-", "").lower()[-16:]
    return v
