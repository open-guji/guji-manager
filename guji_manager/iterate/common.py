"""几个工具共用的小函数。"""
from __future__ import annotations

import csv
import math
from pathlib import Path


def read_tsv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_tsv(path: Path, cols: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])


def cell_key(row: dict) -> tuple[str, str]:
    """(册, 格号)。册号补零到 3 位，免得 20 与 020 对不上。"""
    v = str(row.get("vol", "")).strip()
    return (v.zfill(3) if v.isdigit() else v, str(row.get("cell", "")).strip())


def col_of(cell: str) -> str:
    """格号 `页:列:行` → `页:列`。"""
    p = cell.split(":")
    return ":".join(p[:2]) if len(p) >= 2 else cell


def page_of(cell: str) -> str:
    return cell.split(":")[0]


def binom_upper(n: int, k: int, conf: float = 0.95) -> float:
    """Clopper–Pearson 单侧上界：n 格里错了 k 个，真实错误率以 conf 概率不超过它。k=0 时≈3/n。"""
    if n <= 0:
        return 1.0
    if k >= n:
        return 1.0
    alpha = 1 - conf

    def cdf(p: float) -> float:   # P(X<=k | n,p)
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))

    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if cdf(mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def required_sample(n_released: int) -> int:
    """新放行类别上线前，金标/盲读抽样量（框架第五节第 2 条）：<100 抽 30；>300 抽 100；>1000 抽 200。
    100–300 文档未写，这里取 60（线性过渡，A31 假设）；放行格不足 30 则全抽。"""
    if n_released > 1000:
        return 200
    if n_released > 300:
        return 100
    if n_released >= 100:
        return 60
    return min(30, n_released)
