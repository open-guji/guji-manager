"""每轮滚动抽检台账（T9）：放行后每轮抽 30 格，记对错，累计错误率（框架第五节第 4 条）。

台账 `audit/<书>/ledger.tsv`，列 `round  vol  cell  cls  verdict  checker  note  date`；verdict 为 ok / bad / skip（看不清不算）。
cls＝放行类别（如 `L2:group_abstain`、`L1:ref_lacuna_text`）。

  guji-manager iterate audit sample --root audit --book sj --round r5 --cls L2:group_abstain --released 放行.tsv --n 30 --out 抽检.tsv
        # 从本轮放行里抽 30 格（排除以前抽过的），列 vol cell char，拿去盲读/看图
  guji-manager iterate audit add --root audit --book sj --round r5 --cls L2:group_abstain --results 结果.tsv --checker A31
        # 结果文件 vol cell verdict [note]
  guji-manager iterate audit summary --root audit --book sj --out 台账.md
        # 每类：本轮 n/bad、累计 n/bad、错误率 95% 上界；本轮有 bad → 红灯（停标 main，收紧后重测）
退出码：summary 有红灯时 2。
"""
from __future__ import annotations

import argparse
import datetime
import random
import sys
from collections import defaultdict
from pathlib import Path

from .common import binom_upper, cell_key, read_tsv, write_tsv

COLS = ["round", "vol", "cell", "cls", "verdict", "checker", "note", "date"]
VERDICTS = ("ok", "bad", "skip")


def ledger_path(root: Path, book: str) -> Path:
    return root / book / "ledger.tsv"


def load(root: Path, book: str) -> list[dict]:
    p = ledger_path(root, book)
    return read_tsv(p) if p.exists() else []


def cmd_sample(a) -> int:
    done = {(r["cls"],) + cell_key(r) for r in load(a.root, a.book)}
    pool = [r for r in read_tsv(a.released) if (a.cls,) + cell_key(r) not in done]
    rnd = random.Random(a.seed)
    rnd.shuffle(pool)
    pick = pool[:a.n]
    write_tsv(a.out, ["vol", "cell", "char"], pick)
    print(f"{a.cls}: 放行 {len(pool)} 格可抽，抽 {len(pick)} 格 → {a.out}")
    return 0


def cmd_add(a) -> int:
    rows, bad = load(a.root, a.book), []
    today = datetime.date.today().isoformat()
    seen = {(r["round"], r["cls"]) + cell_key(r) for r in rows}
    n = 0
    for r in read_tsv(a.results):
        v = (r.get("verdict") or "").strip()
        k = cell_key(r)
        if v not in VERDICTS:
            bad.append(f"{k} verdict 须为 {VERDICTS}：{v!r}")
            continue
        if (a.round, a.cls) + k in seen:
            bad.append(f"{k} 本轮本类已记过")
            continue
        rows.append({"round": a.round, "vol": k[0], "cell": k[1], "cls": a.cls, "verdict": v,
                     "checker": a.checker, "note": r.get("note", ""), "date": today})
        n += 1
    if bad:
        for b in bad:
            print("✗", b)
        return 1
    write_tsv(ledger_path(a.root, a.book), COLS, rows)
    print(f"记入 {n} 格 → {ledger_path(a.root, a.book)}")
    return 0


def summarize(rows: list[dict]) -> dict:
    by = defaultdict(lambda: defaultdict(lambda: {"ok": 0, "bad": 0, "skip": 0}))
    rounds: list[str] = []
    for r in rows:
        by[r["cls"]][r["round"]][r["verdict"]] += 1
        if r["round"] not in rounds:
            rounds.append(r["round"])
    out = {}
    for cls, rd in by.items():
        last = [x for x in rounds if x in rd][-1]
        n_all = sum(v["ok"] + v["bad"] for v in rd.values())
        bad_all = sum(v["bad"] for v in rd.values())
        n_last, bad_last = rd[last]["ok"] + rd[last]["bad"], rd[last]["bad"]
        out[cls] = {"last_round": last, "n_last": n_last, "bad_last": bad_last, "n_all": n_all, "bad_all": bad_all,
                    "upper_all": binom_upper(n_all, bad_all) if n_all else 1.0,
                    "light": "red" if bad_last else ("yellow" if n_last < 30 else "green")}
    return out


def render(s: dict, book: str) -> str:
    L = [f"# 抽检台账：{book}", "", "| 类别 | 最近一轮 | 本轮 抽/错 | 累计 抽/错 | 错误率 95% 上界 | 灯 |", "|---|---|---|---|---|---|"]
    for cls, x in sorted(s.items()):
        L.append(f"| `{cls}` | {x['last_round']} | {x['n_last']}/{x['bad_last']} | {x['n_all']}/{x['bad_all']} | {x['upper_all'] * 100:.1f}% | "
                 + {"red": "🔴 有错：停标 main，收紧后重测", "yellow": "🟡 本轮不足 30 格", "green": "🟢"}[x["light"]] + " |")
    L += ["", "> 0/30 只说明错误率上界约 10%；累计越多上界越小。skip（看不清）不计入。", ""]
    return "\n".join(L)


def cmd_summary(a) -> int:
    s = summarize(load(a.root, a.book))
    md = render(s, a.book)
    if a.out:
        a.out.write_text(md, encoding="utf-8")
    print(md)
    return 2 if any(x["light"] == "red" for x in s.values()) else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="iterate audit", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("sample", "add", "summary"):
        p = sub.add_parser(name)
        p.add_argument("--root", type=Path, default=Path("audit"))
        p.add_argument("--book", required=True)
        if name != "summary":
            p.add_argument("--round", required=name == "add")
            p.add_argument("--cls", required=True)
        if name == "sample":
            p.add_argument("--released", type=Path, required=True); p.add_argument("--n", type=int, default=30)
            p.add_argument("--seed", type=int, default=1); p.add_argument("--out", type=Path, required=True)
        if name == "add":
            p.add_argument("--results", type=Path, required=True); p.add_argument("--checker", default="A31")
        if name == "summary":
            p.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    return {"sample": cmd_sample, "add": cmd_add, "summary": cmd_summary}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
