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
import time
from pathlib import Path

SECTION = "rounds"
WHO = "A31"
#: detail 里认的字段（多余的丢掉，免得把大清单写进库）
FIELDS = ("kind", "date", "cv", "pack", "vols", "cells", "pending", "net_queue", "gain", "regress",
          "released", "audit", "top", "human_min", "verdict", "note", "auto")


def round_of(pack_label: str) -> str | None:
    """包标签里的轮次：cv0.6.2-c30-g19-r4-a2 → r4、…-qtw07-r9b → r9b；没有 -rN 段返回 None"""
    m = re.search(r"(?:^|-)(r\d+[a-z]?)(?:-a\d+)?$", str(pack_label or ""))
    return m.group(1) if m else None


def round_key(label: str) -> str:
    """r5 / 第5轮 / 5 / r10b / 包标签 → r5 / r5 / r5 / r10b / 包里的 rN"""
    r = round_of(label)
    if r:
        return r
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
        # metric.section 外键要求先登记栏目；网站把 rounds 从侧栏隐去，只在总览各书的「迭代轮次」页显示
        conn.execute("INSERT INTO progress.section (section, title, owner, description, sort) VALUES (%s, %s, %s, %s, 90)"
                     " ON CONFLICT (section) DO NOTHING",
                     (SECTION, "迭代轮次", WHO, "每本书每轮粗校迭代的首审人审率与轮记录（总览各书展开看）"))
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


# ---- 自动收轮：标 main 后从后台各册的包口径汇总成这一轮（不用手跑 round-report）----

def aggregate(vols: list[dict], label: str, prev: dict | None = None) -> dict | None:
    """vols：progress.volume 行（含 extra、cv_version）。label 是轮次（r5）或包标签；取包口径（★main 包，
    run.py --pick main 写的 cv.pack）属于这一轮的册汇总。
    prev：上一轮记录（detail＋key），册数相同时算轮收益。没有这样的册返回 None。"""
    rnd = round_key(label)
    cells = pending = 0
    n, cvs, packs = 0, set(), set()
    for v in vols:
        p = (v.get("extra") or {}).get("cv.pack") or {}
        if round_of(p.get("label")) != rnd or p.get("pick", "main") != "main" or not p.get("cells"):
            continue
        packs.add(str(p["label"]))
        n += 1
        cells += int(p["cells"])
        pending += int(p.get("review") or 0)
        cv = re.match(r"cv([\w.]+?)-c", str(p["label"]))
        if cv:
            cvs.add(cv.group(1))
    if not n:
        return None
    rec = {"key": rnd, "label": rnd, "rate": pending / cells, "cells": cells, "pending": pending,
           "vols": n, "pack": rnd if len(packs) > 1 else packs.pop(), "verdict": "main", "date": time.strftime("%Y-%m-%d", time.localtime()), "auto": True}
    if len(cvs) == 1:
        rec["cv"] = cvs.pop()
    if prev and prev.get("vols") == n and isinstance(prev.get("pending"), int):
        rec["gain"] = prev["pending"] - pending
    return rec


def auto_round(book: str, label: str, write_db: bool = True) -> dict | None:
    """读后台这本书各册与已有轮次，汇总 label 这一轮写回（保留人工/轮报告已写的字段，只更新自动字段）。"""
    from .._cv import connect
    with connect() as conn:
        vols = [dict(zip(("vol", "extra", "cv_version"), r)) for r in conn.execute(
            "SELECT vol, extra, cv_version FROM progress.volume WHERE book_id = %s", (book,)).fetchall()]
        got = conn.execute(
            "SELECT key, detail, label FROM progress.metric WHERE book_id = %s AND vol = '' AND section = %s AND key <> 'target'",
            (book, SECTION)).fetchall()
    old = {r[0]: (r[1] or {}) for r in got}
    labels = {r[0]: r[2] for r in got if len(r) > 2 and r[2]}
    key = round_key(label)
    if not round_of(label) and not re.fullmatch(r"r?\d+[a-z]?", str(label)):
        return None                                  # 包标签里没有轮次（如 job207），不自动收轮
    earlier = sorted((k for k in old if _sort(k) < _sort(key) and old[k].get("verdict") != "rejected"), key=_sort)
    prev = dict(old[earlier[-1]], key=earlier[-1]) if earlier else None
    rec = aggregate(vols, label, prev)
    if not rec:
        return None
    merged = dict(old.get(key) or {})
    keep = ("date", "verdict") if merged else ()       # 已有记录的日期、结论不被自动覆盖
    merged.update({k: v for k, v in rec.items() if k not in ("key", "label", "rate") + tuple(k2 for k2 in keep if k2 in merged)})
    out = dict(merged, key=key, label=labels.get(key) or label_of(key), rate=rec["rate"])
    if write_db:
        write(rows(book, [out]))
    return out


def label_of(key: str) -> str:
    """r5 → 第5轮（同回填的显示名）"""
    m = re.fullmatch(r"r(\d+[a-z]?)", key)
    return f"第{m.group(1)}轮" if m else key


def auto_main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="从后台各册包口径汇总一轮，写进「迭代轮次」（标 main 后自动调）")
    ap.add_argument("--book", required=True, help="套书 id")
    ap.add_argument("--label", required=True, help="包标签（＝★main 标签，如 r5）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    r = auto_round(a.book, a.label, write_db=not a.dry_run)
    print(json.dumps(r, ensure_ascii=False) if r else f"{a.book} 还没有 main＝{a.label} 且包口径已统计的册")
    return 0


def note_main_round(book: str, label: str) -> bool:
    """标 main 后统计人审率的环境不全时（没 ai-team 检出等），也在看板「迭代轮次」占一条：这一轮已标 main、人审率待统计。
    已有这一轮的记录就不动（统计出来后 auto-round 会补全）。写库失败只返回 False，不抛。"""
    key = round_key(label)
    if not (round_of(label) or re.fullmatch(r"r?\d+[a-z]?", str(label))):
        return False
    try:
        from .._cv import connect
        with connect() as conn:
            if conn.execute("SELECT 1 FROM progress.metric WHERE book_id = %s AND vol = '' AND section = %s AND key = %s",
                            (book, SECTION, key)).fetchone():
                return True
        write(rows(book, [{"key": key, "label": label_of(key), "rate": None, "verdict": "pending", "auto": True,
                           "date": time.strftime("%Y-%m-%d", time.localtime()),
                           "note": "已标 main，人审率待统计（标 main 的机器上没跑成包口径统计）"}]))
        return True
    except Exception as e:  # noqa: BLE001
        print(f"（看板没占上这一轮：{e}）")
        return False
