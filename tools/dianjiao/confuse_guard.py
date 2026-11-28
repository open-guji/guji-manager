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


# 书级开关：纯文意字组（己已巳、日曰；殿本 11-20、全唐文 11-28 Sheldon 定）关掉，来源 context_pairs/<书>.tsv；史记全开。
# 加新的纯文意字组去 context_pairs/<书>.tsv，不要再改这里。
def _off(book: str) -> set:
    try:
        from context_pairs import load
        cp = load(book=book)
    except Exception:
        cp = {}
    return {frozenset((a, b)) for a, bs in cp.items() for b in bs}


def blocked(ai_char: str, cands, book: str = "default") -> bool:
    off = _off(book)
    return any(frozenset((ai_char, b)) not in off for b in _M.get(ai_char, set()) & set(cands))


if __name__ == "__main__":
    assert blocked("十", ["千", "十"]) and not blocked("十", ["十", "廿"])
    assert blocked("日", ["曰", "日"]) and not blocked("日", ["曰", "日"], "殿本") and blocked("十", ["千"], "殿本")
    assert not blocked("已", ["巳", "已"], "全唐文") and blocked("十", ["千"], "全唐文")
    print("ok")
