"""D01/D02 benchmark：把按码现算的逐格表（cells-*.tsv，D01／D02／H01 三码）对金标 `benchmark/D-gold-第7轮105格.tsv` 过一遍。

    python3 按码现算.py --codes D01,D02,H01 --books siku --vols <金标里的册> --out /tmp/d --glyph-db <glyph.db>
    python3 d_bench.py /tmp/d D-gold-第7轮105格.tsv

三条验收（全过才算判得对）：
  ① 金标类 J（图上是己已巳一族、整理本字也在组里）一格不许还在 D01／D02——应全在 H01；
  ② H01 里不许混进金标类非 J 的遮挡格（把别的字误归极难形近）；
  ③ 非 J 的遮挡格仍按有无整理本字分 D01／D02（数不变）。
"""
import csv, sys, collections
from pathlib import Path
d, gold = Path(sys.argv[1]), sys.argv[2]
cls = {(r["册"], r["格号"]): r["类"] for r in csv.DictReader(open(gold, encoding="utf-8"), delimiter="\t")}
now = {}
for f in d.glob("cells-*.tsv"):
    for r in csv.DictReader(open(f, encoding="utf-8"), delimiter="\t"):
        if (r["vol"], r["cell"]) in cls:
            now[(r["vol"], r["cell"])] = r["reason"]
tab = collections.Counter((cls[k], now.get(k, "(不在三码里)")) for k in cls)
for (c, rs), n in sorted(tab.items()):
    print(f"类 {c:2s} → {rs:20s} {n}")
bad1 = [k for k, c in cls.items() if c == "J" and now.get(k) != "hard_pair"]
bad2 = [k for k, c in cls.items() if c != "J" and now.get(k) == "hard_pair"]
print("① J 未归 H01：", len(bad1), bad1[:5])
print("② 非 J 误归 H01：", len(bad2), bad2[:5])
