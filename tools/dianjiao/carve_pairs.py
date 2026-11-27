"""按刻形记的字对表（通用机制，QTW 11-27 提、GM3 落地）。

各书口径定了「按刻形记」（异体字写刻本字形、不归一）的字对，AI 按文意分不出刻本刻的是哪个形，
**即使两次判断一致且都高置信也不放行，留人看图**（wiki「AI分析两层做法与待审格摘要」第三节例外）。

字对表：TSV，首行表头，至少有 a、b 两列（其余列随意，全唐文见 carve_pairs/全唐文.tsv）。
各书可挂自己的表：`load(path)`，或设环境变量 `GUJI_CARVE_PAIRS=<tsv路径>[:<tsv路径>…]`，或 `load(book="全唐文")` 读本目录 carve_pairs/<书>.tsv。
用法（放行脚本里，与 confuse_guard.blocked 并列）：
    from carve_pairs import load, blocked
    pairs = load(book="全唐文")
    if blocked(ai_char, cands, pairs): 不放行，留人审
口径：判出字与候选（或书文现字）里的另一方构成一对才拦。QTW 原话是「候选字或判出字落在任一对里就不放行」，按字拦会把表里 日/目、木/本 的日、木全拦掉（日曰组也受牵连），所以改按「对」拦。
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent / "carve_pairs"


def load(path: str | os.PathLike | None = None, book: str | None = None) -> dict[str, set[str]]:
    """读字对表，返回 {字: 与它成对的字集合}（对称）。path 缺省读环境变量 GUJI_CARVE_PAIRS（冒号分隔多张），再缺省读 book 对应表；都没有返回空表。"""
    paths: list[str] = []
    if path:
        paths.append(str(path))
    elif os.environ.get("GUJI_CARVE_PAIRS"):
        paths += [p for p in os.environ["GUJI_CARVE_PAIRS"].split(":") if p]
    elif book:
        paths.append(str(HERE / f"{book}.tsv"))
    m: dict[str, set[str]] = {}
    for p in paths:
        with open(p, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                a, b = (r.get("a") or "").strip(), (r.get("b") or "").strip()
                if a and b:
                    m.setdefault(a, set()).add(b)
                    m.setdefault(b, set()).add(a)
    return m


def blocked(ai_char: str, cands, pairs: dict[str, set[str]], cur: str = "") -> bool:
    """判出字与候选（或书文现字 cur）里另一方构成按刻形记的一对 → True（不放行，留人看图）。

    按「对」判，不按「字」判：表里有 日/目，日曰组的日不能因此全拦；只有候选里真有 目 才拦。"""
    others = set(cands) | ({cur} if cur else set())
    return bool(pairs.get(ai_char, set()) & others)


if __name__ == "__main__":
    pr = load(book="全唐文")
    assert blocked("刺", ["剌", "刺"], pr) and blocked("刺", ["刺"], pr, cur="剌")
    assert not blocked("日", ["曰", "日"], pr) and blocked("日", ["日", "目"], pr)
    print(f"ok，{len(pr)} 个字")
