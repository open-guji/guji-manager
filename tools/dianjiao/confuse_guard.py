"""易混字守卫（三书通用，SJ 册29–38 单路放行 53 格出 1 真错：十/千）。

规则：AI 判出的字属于易混对，且候选里含该对的另一方 → 不放行，交 B 路／看图。
与 vpairs/are_variants 异体闸并列用：异体闸管「是不是同一字的写法」，本守卫管「形近、不同字、数字或虚字易错」。
用法：from confuse_guard import blocked; blocked("十", ["千", "十"]) -> True
表可扩：往 PAIRS 加一行，两个字即可（自动对称）。
"""
PAIRS = ["十千", "于干", "七十", "未末", "己已", "已巳", "己巳", "日曰", "戊戌", "戍戌", "戊戍", "刀力", "人入", "大太", "土士", "木本", "末未", "千干", "午牛", "王玉"]
_M: dict[str, set[str]] = {}
for p in PAIRS:
    for a in p:
        _M.setdefault(a, set()).update(b for b in p if b != a)


# 书级开关：殿本（ZM）按文意判日曰、己已巳（sheldon 11-20 口径），这两对关掉；史记、全唐文全开。
OFF_PAIRS = {"殿本": {"日曰", "己已", "已巳", "己巳"}, "default": set()}


def blocked(ai_char: str, cands, book: str = "default") -> bool:
    off = {frozenset(p) for p in OFF_PAIRS.get(book, OFF_PAIRS["default"])}
    return any(frozenset((ai_char, b)) not in off for b in _M.get(ai_char, set()) & set(cands))


if __name__ == "__main__":
    assert blocked("十", ["千", "十"]) and not blocked("十", ["十", "廿"])
    assert blocked("日", ["曰", "日"]) and not blocked("日", ["曰", "日"], "殿本") and blocked("十", ["千"], "殿本")
    print("ok")
