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


def blocked(ai_char: str, cands) -> bool:
    return bool(_M.get(ai_char, set()) & set(cands))


if __name__ == "__main__":
    assert blocked("十", ["千", "十"]) and not blocked("十", ["十", "廿"])
    print("ok")
