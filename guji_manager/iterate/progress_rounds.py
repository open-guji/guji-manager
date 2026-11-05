"""把每轮记录写进后台进度库（open-guji.com/admin/text「迭代轮次」页）。

一轮一条书级指标：progress.metric section='rounds'、vol=''、key='r<N>'，value＝首审人审率（小数，unit=%），
detail＝这一轮的记录（字段见 open-guji-site docs/text-progress.md「迭代轮次」）；key='target' 是目标人审率。

  # 每轮验收后（round-report 里带 --push-progress 也会调这里）
  guji-manager iterate round-report --cur … --prev … --label r5 --push-progress 96mid1ogzk --kind D --cv v0.6.3 --verdict main
  # 回填历史 / 改目标（json 形如 ai-team domain/CV/质检/迭代降人审框架/历史轮次.json）
  guji-manager iterate push-rounds --json 历史轮次.json [--book 96mid1ogzk] [--write]

缺省只打印，--write 才写库（连 NEON_DATABASE_URL，同 pending-stats）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SECTION = "rounds"
WHO = "A31"
#: detail 里认的字段（多余的丢掉，免得把大清单写进库）
FIELDS = ("kind", "date", "cv", "pack", "vols", "cells", "pending", "net_queue", "gain", "regress",
          "released", "audit", "top", "human_min", "verdict", "note")


def round_key(label: str) -> str:
    """r5 / 第5轮 / 5 / r10b → r5 / r5 / r5 / r10b"""
    m = re.search(r"(\d+[a-z]?)", str(label))
    return f"r{m.group(1)}" if m else str(label)


def _sort(key: str) -> int:
    m = re.match(r"r(\d+)([a-z]?)", key)
    return int(m.group(1)) * 10 + (ord(m.group(2)) - 96 if m.group(2) else 0) if m else 1000


def from_report(res: dict, label: str, **extra) -> dict:
    """round_report.compare 的结果 → 一轮记录"""
    top = sorted((r for r in res["reasons"] if r["delta"]), key=lambda r: -abs(r["delta"]))[:5]
    rec = {"key": round_key(label), "label": label,
           "rate": res["n"] / res["cells_total"] if res.get("cells_total") else None,
           "cells": res.get("cells_total") or None, "pending": res["n"], "net_queue": res["net"],
           "gain": res["prev_n"] - res["n"], "regress": len(res["regress"]),
           "vols": len(res.get("by_vol") or []) or None,
           "top": [{"reason": r["reason"], "delta": r["delta"], "n": r["cur"]} for r in top]}
    rec.update({k: v for k, v in extra.items() if v not in (None, "")})
    return rec


def rows(book: str, rounds: list[dict], target: float | None = None) -> list[tuple]:
    out = []
    if target is not None:
        out.append((book, "target", "目标人审率", float(target), None, 0))
    for r in rounds:
        key = r.get("key") or round_key(r.get("label", ""))
        detail = {k: r[k] for k in FIELDS if r.get(k) is not None}
        rate = r.get("rate")
        out.append((book, key, r.get("label") or key, None if rate is None else float(rate), detail, _sort(key)))
    return out


def write(rs: list[tuple]) -> int:
    from .._cv import connect
    with connect() as conn:
        for book, key, label, value, detail, sort in rs:
            conn.execute("SELECT progress.put_metric(%s, '', %s, %s, %s, %s, '%%', %s, NULL, %s::jsonb, %s)",
                         (book, SECTION, key, label, value, WHO,
                          json.dumps(detail, ensure_ascii=False) if detail else None, sort))
    return len(rs)


def show(rs: list[tuple]) -> None:
    for book, key, label, value, detail, _ in rs:
        print(f"{book}\t{key}\t{label}\t{'' if value is None else f'{value * 100:.3f}%'}\t{json.dumps(detail or {}, ensure_ascii=False)[:160]}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="回填／改写后台的迭代轮次记录")
    ap.add_argument("--json", type=Path, required=True, help="{books:{<book_id>:{target, rounds:[…]}}}")
    ap.add_argument("--book", help="只推这一本")
    ap.add_argument("--write", action="store_true", help="真写库（缺省只打印）")
    a = ap.parse_args(argv)
    data = json.loads(a.json.read_text(encoding="utf-8"))
    rs = []
    for book, x in (data.get("books") or {}).items():
        if a.book and book != a.book:
            continue
        rs += rows(book, x.get("rounds") or [], x.get("target"))
    show(rs)
    if a.write:
        print(f"写入 {write(rs)} 条 → progress.metric section={SECTION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
