"""纯文意字组表（通用机制，Sheldon 11-28 定、QTW 提、GM3 落地）。

有的字组刻本里混用、字形分不开（己已巳、日曰），口径定了「完全按文意判」。这类字对**不受任何形近／异体闸约束**：
异体闸（vpairs／are_variants，如 已巳 在异体表里）、易混字守卫（confuse_guard）、按刻形字对表（carve_pairs）
遇到（AI 字，候选）正好构成表里的一对，一律放过，只剩「两路 high 同字」这条放行标准。

以后再有这类字组：往 `context_pairs/<书>.tsv` 加一行（列 pair、a、b，其余随意），并在数据目录
`config/groups/pair_attribution.yaml` 里写 `attr: context`（两处同源，见 pair_attribution.py；本模块也认归属表里的 context）。
各书一张表；环境变量 `GUJI_CONTEXT_PAIRS=<tsv>[:<tsv>…]` 可盖；表缺失＝空表（不豁免任何对）。

用法（放行脚本里，所有闸之前）：
    from context_pairs import load, gate_blocked
    cp = load(book="全唐文")
    if gate_blocked(ai_char, cands, book="全唐文", gates=[...], context=cp): 不放行
    # 或只问一对是不是纯文意：is_context(cp, "已", "巳")
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent / "context_pairs"


def load(path: str | os.PathLike | None = None, book: str | None = None, attribution: str | os.PathLike | None = None) -> dict[str, set[str]]:
    """{字: 与它构成纯文意对的字集合}（对称）。attribution 给了就并上归属表里 attr=context 的对。"""
    paths: list[str] = []
    if path:
        paths.append(str(path))
    elif os.environ.get("GUJI_CONTEXT_PAIRS"):
        paths += [p for p in os.environ["GUJI_CONTEXT_PAIRS"].split(":") if p]
    elif book and (HERE / f"{book}.tsv").exists():
        paths.append(str(HERE / f"{book}.tsv"))
    m: dict[str, set[str]] = {}

    def add(a: str, b: str) -> None:
        if a and b and a != b:
            m.setdefault(a, set()).add(b)
            m.setdefault(b, set()).add(a)

    for p in paths:
        with open(p, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                add((r.get("a") or "").strip(), (r.get("b") or "").strip())
    if attribution:
        from guji_manager import pair_attribution as PA
        for k, v in PA.load(attribution).items():
            if v.get("attr") == "context":
                add(k[0], k[1])
    return m


def is_context(pairs: dict[str, set[str]], a: str, b: str) -> bool:
    return b in pairs.get(a, set())


def gate_blocked(ai_char: str, cands, gates, context: dict[str, set[str]] | None = None) -> bool:
    """gates：若干个 `f(ai_char, others) -> bool`（True＝拦）。候选里与 AI 字构成纯文意对的字先剔除，再交各闸。

    剔除按「对」：候选里有 己、已，AI 判 已 时，己 对 已 是纯文意对，不参与异体闸／守卫；候选里另有无关的字照常参与。"""
    others = [c for c in cands if not (context and is_context(context, ai_char, c))]
    return any(g(ai_char, others) for g in gates)


if __name__ == "__main__":
    cp = load(book="全唐文")
    assert is_context(cp, "已", "巳") and is_context(cp, "曰", "日") and not is_context(cp, "日", "目")
    from confuse_guard import blocked as guard
    gate = lambda ai, oth: guard(ai, oth)  # noqa: E731
    assert gate_blocked("日", ["曰", "日"], [gate]) and not gate_blocked("日", ["曰", "日"], [gate], cp)
    assert gate_blocked("十", ["千", "十"], [gate], cp)           # 不是纯文意对，照拦
    assert gate_blocked("日", ["曰", "目"], [gate], cp) is False   # 日/目 不在易混表里；曰 被剔除
    print(f"ok，{len(cp)} 个字")
