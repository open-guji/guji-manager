"""回库事后核：下一轮跑完，把新增待审和新放行按库首位归到回库字上，只害不帮的回库字撤库（2026-11-18，Sheldon 定）。

## 为什么

放行格回库（`ops/lib_backfill.py`）补进来的少见字／异体，标签看图都对，却会抢常用字格的库首位（史記 g26 回库
9,678 例，r80 多出 987 格待审，482 格是首位换成回库字）。回库前的核验都分不开好坏：只看形状的门槛拦害字和拦有用字
的比例差不多，模拟回库（`steal_check`）在真格上也只拦中四分之一的害字（`放行格回库.md` 第三节）。

能分清好坏的是**下一轮的实际结果**。SJ 出 g27 就是这样做的：r79→r80 新增的待审格看库首位换成了哪个回库字（害），
新放行的格看是哪个回库字救回来的（帮），只害不帮的 403 字整字撤掉，收回约 690 格新待审、只丢 1 格新放行。
本模块把这一套做成命令，三本书每轮跑完都能用。

## 做什么

输入：同一批册的前后两轮产物根（前一轮＝回库前的库跑的，后一轮＝回库后的库跑的），各取 `seed_admit`、`glyph_match`。
回库字＝现库里带 `backfill: true` 的机器刻例的字（`--batches` 可只认某几个批次）。两轮都有的格（按格键）逐格比：

- **害**：前一轮放行、后一轮没放行的格。后一轮库首位是回库字、且与前一轮首位不同 → 记在那个字的「抢首位」下；
  否则后一轮前 `top` 名里新进了回库字（前一轮前 `top` 名没有）→ 记在那个字的「进前几」下。
- **帮**：前一轮没放行、后一轮放行的格。放行字本身是回库字 → 记在它下面；否则后一轮库首位是回库字、且与前一轮不同 → 记在它下面。
- **撤库单**：有害、没有帮的回库字，这个字全部回库刻例（`provenance=auto`、`backfill`）。

`--apply`：对撤库单逐例追加 `glyph_audit` 撤库事件（`source=回库事后核`），直接处理并导出字形库账本；人裁刻例不动。
之后照常 `guji db sync` 推上中心库；钉快照的书（史記）要出新快照改钉才生效。
撤过的格 `lib_backfill` 不会再选（查 `evictions`）。

格键是按切分编号的，两轮切分变了的格会对不上号；只比两轮都有的格，换切分的轮次结果会偏少，报告里记两边格数。
"""
from __future__ import annotations
from ..products_io import decide_dir

import collections
import datetime
import json
import sqlite3
from pathlib import Path

TOP = 5


def backfill_chars(db_path: Path | str, batches: set[str] | None = None) -> dict[str, list[str]]:
    """现库里的回库刻例：字 → 刻例 id。只认机器来路、带 `backfill` 标、还在库里的（撤过的不算）。"""
    out: dict[str, list[str]] = collections.defaultdict(list)
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as c:
        evicted = {r[0] for r in c.execute("SELECT instance_id FROM evictions")}
        for iid, ch, prov, ev in c.execute("SELECT instance_id, char, provenance, evidence FROM admissions"):
            if prov != "auto" or iid in evicted:
                continue
            try:
                e = json.loads(ev or "{}")
            except ValueError:
                continue
            if not e.get("backfill"):
                continue
            if batches and e.get("batch") not in batches:
                continue
            out[ch].append(iid)
    return dict(out)


def _top(rec: dict | None, n: int) -> list[str]:
    """`glyph_match` 一格的候选字（每字取一次，按原序），前 n 个。"""
    seen: list[str] = []
    for c, _v in (rec or {}).get("candidates") or []:
        if c not in seen:
            seen.append(c)
        if len(seen) >= n:
            break
    return seen


def compare(before_sa: dict, before_gm: dict, after_sa: dict, after_gm: dict, bf: set[str], *,
            top: int = TOP) -> dict:
    """一册前后两轮逐格比。纯函数。→ {"harm_top1": {字: [格键]}, "harm_topn": {...}, "help": {...}, "stat": Counter}"""
    harm1: dict[str, list] = collections.defaultdict(list)
    harmn: dict[str, list] = collections.defaultdict(list)
    helped: dict[str, list] = collections.defaultdict(list)
    stat: collections.Counter = collections.Counter()
    stat["前一轮格"] += len(before_sa)
    stat["后一轮格"] += len(after_sa)
    for k, ra in after_sa.items():
        rb = before_sa.get(k)
        if rb is None:
            continue
        stat["两轮都有"] += 1
        b_ad, a_ad = bool(rb.get("admit")), bool(ra.get("admit"))
        if b_ad == a_ad:
            continue
        bt, at = _top(before_gm.get(k), top), _top(after_gm.get(k), top)
        b0, a0 = (bt or [None])[0], (at or [None])[0]
        if b_ad and not a_ad:
            stat["新增待审"] += 1
            if a0 in bf and a0 != b0:
                harm1[a0].append(k)
                stat["新增待审·首位换成回库字"] += 1
            else:
                new = [c for c in at if c in bf and c not in bt]
                if new:
                    harmn[new[0]].append(k)
                    stat["新增待审·前几名新进回库字"] += 1
        else:
            stat["新放行"] += 1
            ch = ra.get("char")
            if ch in bf:
                helped[ch].append(k)
                stat["新放行·放行字是回库字"] += 1
            elif a0 in bf and a0 != b0:
                helped[a0].append(k)
                stat["新放行·首位换成回库字"] += 1
    return {"harm_top1": dict(harm1), "harm_topn": dict(harmn), "help": dict(helped), "stat": stat}


def withdraw_list(harm_top1: dict, harm_topn: dict, helped: dict) -> list[str]:
    """有害（抢首位或进前几）、没有帮的回库字。纯函数。"""
    return sorted((set(harm_top1) | set(harm_topn)) - set(helped))


def run(books: list[str], before: str | Path, after: str | Path, *, batches: set[str] | None = None,
        top: int = TOP, apply: bool = False, batch: str | None = None, report: str | None = None,
        log=None) -> dict:
    from .._cv import glyph_db_path
    from .lib_backfill import _seed_cells
    say = log or (lambda *_: None)
    before, after = Path(before), Path(after)
    dbp = glyph_db_path()
    bfmap = backfill_chars(dbp, batches)
    bf = set(bfmap)
    harm1: dict[str, list] = collections.defaultdict(list)
    harmn: dict[str, list] = collections.defaultdict(list)
    helped: dict[str, list] = collections.defaultdict(list)
    stat: collections.Counter = collections.Counter()
    missing = []
    for b in books:
        if not decide_dir(before, b).is_dir() or not decide_dir(after, b).is_dir():
            missing.append(b)
            continue
        r = compare(_seed_cells(before, b, "seed_admit"), _seed_cells(before, b, "glyph_match"),
                    _seed_cells(after, b, "seed_admit"), _seed_cells(after, b, "glyph_match"), bf, top=top)
        for src, dst in ((r["harm_top1"], harm1), (r["harm_topn"], harmn), (r["help"], helped)):
            for ch, ks in src.items():
                dst[ch].extend(ks)
        stat.update(r["stat"])
        say(f"  {b}: 新增待审 {r['stat']['新增待审']}，新放行 {r['stat']['新放行']}")
    wl = withdraw_list(harm1, harmn, helped)
    rows = [{"char": ch, "harm_top1": len(harm1.get(ch, [])), "harm_topn": len(harmn.get(ch, [])),
             "instances": bfmap[ch], "cells": (harm1.get(ch, []) + harmn.get(ch, []))[:20]} for ch in wl]
    rows.sort(key=lambda x: -(x["harm_top1"] + x["harm_topn"]))
    batch = batch or f"backfill-audit-{datetime.date.today():%Y%m%d}"
    rep = {"db": str(dbp), "books": books, "missing": missing, "before": str(before), "after": str(after),
           "batches": sorted(batches) if batches else None, "top": top, "batch": batch, "apply": apply,
           "backfill_chars": len(bf), "backfill_instances": sum(len(v) for v in bfmap.values()),
           "stat": dict(stat),
           "harm_chars": len(set(harm1) | set(harmn)), "help_chars": len(helped),
           "harm_cells": sum(len(v) for v in harm1.values()) + sum(len(v) for v in harmn.values()),
           "help_cells": sum(len(v) for v in helped.values()),
           "withdraw": rows,
           "withdraw_instances": sum(len(x["instances"]) for x in rows),
           "kept_help_harm": sorted(set(helped) & (set(harm1) | set(harmn)))}
    if apply and rows:
        rep["applied"] = _apply(rows, batch, dbp)
    if report:
        Path(report).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep


def _apply(rows: list[dict], batch: str, dbp) -> dict:
    from .._cv import EventLog, EventTarget, GlyphDB, export_store, glyph_store_path, make_event
    from ..feedback.glyph_audit import glyph_audit
    elog = EventLog()
    base = elog.latest_seq(batch)
    evs = []
    for r in rows:
        for iid in r["instances"]:
            key = iid[3:] if iid.startswith("v2:") else iid
            tgt = EventTarget(step="glyph_audit", unit="cell", key=iid, book=key.split(":")[0])
            p = {"v": "evict", "instance_id": iid, "char_self": r["char"],
                 "source": f"回库事后核:只害不帮（抢首位 {r['harm_top1']}、进前几 {r['harm_topn']}）"}
            evs.append(make_event(batch, base + len(evs) + 1, "glyph_audit", tgt, p, actor="model"))
    if not evs:
        return {"lib_events": 0}
    elog.append(evs)
    res = glyph_audit([(e, None) for e in evs], db_path=str(dbp))
    elog.mark_consumed("glyph_audit", evs, note="回库事后核：已直接处理")
    db = GlyphDB(str(dbp))
    try:
        export_store(db, glyph_store_path())
    finally:
        db.close()
    return {"lib_events": len(evs), "lib_errors": len(res.errors), "errors": res.errors[:20]}


def summary(rep: dict) -> str:
    s = rep["stat"]
    line = (f"回库字 {rep['backfill_chars']}（{rep['backfill_instances']} 例）；两轮都有的格 {s.get('两轮都有', 0)}，"
            f"新增待审 {s.get('新增待审', 0)}（首位换成回库字 {s.get('新增待审·首位换成回库字', 0)}、"
            f"前几名新进回库字 {s.get('新增待审·前几名新进回库字', 0)}），"
            f"新放行 {s.get('新放行', 0)}（靠回库字 {rep['help_cells']}）；"
            f"有害的字 {rep['harm_chars']}、有帮的字 {rep['help_chars']}，"
            f"只害不帮要撤 {len(rep['withdraw'])} 字 {rep['withdraw_instances']} 例")
    if rep.get("missing"):
        line += f"（⚠ 缺产物没比的册：{','.join(rep['missing'])}）"
    if "applied" in rep:
        a = rep["applied"]
        line += f"；已追加撤库事件 {a['lib_events']} 条（出错 {a.get('lib_errors', 0)}），批次 {rep['batch']}"
    return line
