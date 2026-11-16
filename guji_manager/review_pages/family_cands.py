"""审字卡候选并上 5b 首位的异体族（2026-11-16）。

依据：ai-team `domain/CV/字形领域/大字符集候选召回-2026-11-15/README.md` 2.2、2.3——5b 首位「错」的最大一块
（三书类外字 19–33 个点）是给了金标的同族另一个码位（內／内、步／歩、候／𠋫）；前 10 名并上首位的族，
类外字候选召回 +2 到 +4.5 个点，比直接给前 30 名划算。

族取自 cv 关系库 `hanzi.shared().family`（异体、部分义项异体、字形微差、部件对应；不含通假、钓鱼形近、简繁，
人审定 distinct 的已剔）。cv 的 `clustering.rare_family.expand_family` 合进 dev 并登记到 manager_api 后，
把 `family_of` 换成调它（`_cv._FALLBACK` 现在登记不了：旧 cv 没有那个模块，守卫测试会红）。

排法：族里来源越多的排越前（多家字书都说是异体的更可信），其次「异体」先于「部件对应」，再按码位。

不做简体否决（Sheldon 11-16 定：刻本图里有时就是简体形）。5b 那条否决（cv `charset_spec` 的 `no-simplified`，
判据 OpenCC `s2t(c) != c`）是 9-17 为了挡机器候选里 s2t／异体扩展造出来的简体字定的，判据把刻本常见的俗写和
新旧字形（内、别、吕、黄、横、册）以及本来就是另一个字的（余、台、后、于）都算成简体：三书人裁金标里
4.4%–5.0% 的格（类外字 6.7%–12.8%）金标字被它判成简体。审字卡是人看图点，多给几个不会自动放错，所以这里不挡；
取消后族块平均只多 0.3 个字（6.6→6.9）。
"""
from __future__ import annotations

import unicodedata
import warnings
from collections.abc import Callable

FAMILY_SRC = "5b首位同族"
FAMILY_MAX = 12

_WARNED = False


def family_of(ch: str) -> list[str]:
    """ch 的异体族，强的在前，不含 ch 自己。cv 或关系库取不到时返回 []（只警告一次，出页不因此失败）。"""
    global _WARNED
    if not ch:
        return []
    try:
        from .._cv import hanzi_shared
        fam = hanzi_shared().family(ch)
    except Exception as e:  # noqa: BLE001 —— 没装 cv、关系库没灌：候选照旧，不并族
        if not _WARNED:
            _WARNED = True
            warnings.warn(f"取不到 cv 关系库，审字卡候选不并异体族：{e!r}", RuntimeWarning, stacklevel=2)
        return []

    def key(item):
        m, edges = item
        strong = sum(1 for e in edges if e.rel != "related")
        return (-len({e.src for e in edges}), -strong, ord(m[0]), m)

    # 兼容汉字（如 U+2F81D）折回去就是 ch 自己的不要：卡上会多一个看着一样的按钮
    return [m for m, _ in sorted(fam.items(), key=key) if unicodedata.normalize("NFKC", m) != ch]


def with_family(cands: list[list[str]], top: str, family: Callable[[str], list[str]] | None = family_of,
                limit: int = FAMILY_MAX) -> list[list[str]]:
    """cands＝[[字, 来源]…]（首位是 5b 首位 `top`）→ 在 `top` 之后并上它的族，标 `FAMILY_SRC`，族块最多 `limit` 个。

    族里已经在 cands 里的字（参校本、库首位、5b 次选）挪进族块最前，来源写成「5b首位同族、原来源」，
    也算在 `limit` 里；其余按 `family` 给的顺序补。`family=None` 或族为空时原样返回。"""
    if not family or not top or not cands or cands[0][0] != top or limit <= 0:
        return cands
    fam = [m for m in family(top) if m and m != top]
    if not fam:
        return cands
    have = {c[0]: c[1] for c in cands[1:]}
    fs = set(fam)
    block = [[c[0], f"{FAMILY_SRC}、{c[1]}"] for c in cands[1:] if c[0] in fs]
    block += [[m, FAMILY_SRC] for m in fam if m not in have]
    block = block[:limit]
    moved = {b[0] for b in block}
    return [cands[0]] + block + [c for c in cands[1:] if c[0] not in moved]
