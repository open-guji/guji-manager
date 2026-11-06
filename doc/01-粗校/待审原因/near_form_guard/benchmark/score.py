#!/usr/bin/env python3
"""N01 放行基准：拿金标（人裁格）给「放行规则」打分。用法：python score.py gold_human.tsv
规则＝只看 参校字、库首位、候选、类 的纯函数；放行字取参校字或库首位。要装 open-guji-cv（读形近表）。
输出每本书、每条规则：放行格数、错数、错率、95% 上界（三之规则近似 3/n，0 错时）。0 错且样本够才可考虑做成放行通道（准确率守则）。"""
import csv, sys, collections, math
from open_guji_cv.clustering.confusable import NEVER_MATCH_FAMILIES, partners

P = partners()
FAM = collections.defaultdict(set)
for a, b in NEVER_MATCH_FAMILIES:
    FAM[a].add(b); FAM[b].add(a)
HARD = set("己已巳日曰")


def plain(ref):
    """参校字是 CJK 基本区常用字、不是己已巳日曰、自己没有形近伙伴（排除 〓、私用码、生僻异写、形近对）。"""
    return bool(ref) and 0x3400 <= ord(ref[0]) <= 0x9FFF and ref not in HARD and not P.get(ref) and not FAM.get(ref)


RULES = {
    "R0 全部跟参校字": lambda r: r["参校字"],
    "R1 只 B 类跟参校字": lambda r: r["参校字"] if r["类"] == "B" else None,
    "R2 B 类＋参校字平常（排除〓/私用/己已巳日曰/有形近伙伴）": lambda r: r["参校字"] if r["类"] == "B" and plain(r["参校字"]) else None,
    "R3 B+C 类＋参校字平常": lambda r: r["参校字"] if r["类"] in "BC" and plain(r["参校字"]) else None,
    "R4 全部跟库首位": lambda r: r["库首位"],
}


def main(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8"), delimiter="\t"))
    print("| 书 | 规则 | 放行格 | 错 | 错率 | 0 错时 95% 上界 |\n|---|---|---:|---:|---:|---:|")
    for book in ("殿本", "史記", "全唐文"):
        R = [r for r in rows if r["书"] == book]
        for name, f in RULES.items():
            rel = [(r, f(r)) for r in R]
            rel = [(r, c) for r, c in rel if c]
            err = [r for r, c in rel if c != r["真字(人裁)"]]
            n = len(rel)
            ub = f"{3 / n:.1%}" if n and not err else "—"
            print(f"| {book} | {name} | {n} | {len(err)} | {(len(err) / n if n else 0):.1%} | {ub} |")


if __name__ == "__main__":
    main(sys.argv[1])
