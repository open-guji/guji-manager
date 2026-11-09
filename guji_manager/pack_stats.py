"""存包时算好这册的人审率分子分母，写进中心库看板（A31，2026-11-08，Sheldon：数据要随 pipeline 跑完自动更新，网站直接读中心库）。

以前人审率是另一台机器上的统计脚本（ai-team `按包统计人审率/run.py`）事后下包重算再写的，哪一步没跑成看板就停在旧数
（11-08：第 6／7 轮人审率「待统计」、顶栏停在第 5 轮）。其实这两个数存包的那一刻就在手边：
  全册格 ＝ seed_admit 各页 `columns[].chars[]` 的格数，待审格 ＝ 其中 `admit` 为假、且人没定过的格数（`is_pending`）。

11-09 用户定：排除名单上的格（切坏／裁坏，图块不进库）人已给了字的（`evidence.human_char`），文本层照出人给的字
（cv `report/slots._to_slot`），不再算待审；人判原刻残（`damaged`）、非字（`not_a_char`）的也是人定过的。
排除名单上没人给字的（多为管线 `gate:crop_defect`）仍算待审。vol01 g20 包 252 格里 203 格是前一种。

`record(book, label, root)`：整册存包成功后调用（`datastore.packs.push_products`），把
  progress.volume.extra['cv.packs'][<包标签>] = {cells, review, rate, at}
写进库（每册只留最近 8 个标签）。网站按 ★main 的标签取这一条，不用等任何事后统计；标 main 的钩子也据此直接收一轮。
只写看板、永远不抛：没连库、没有 seed_admit（只存了几步的包）、册号认不出都静默跳过。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

KEEP = 8                    # 每册看板里留最近几个包标签的数
KEY = "cv.packs"


def is_pending(c: dict) -> bool:
    """seed_admit 的一格算不算待审：没放行，且不是「排除名单上人已定过」的格。口径见模块头。"""
    if c.get("admit"):
        return False
    if "excluded" in (c.get("doubts") or []):
        ev = c.get("evidence") or {}
        why = str(ev.get("excluded") or "")
        if ev.get("human_char") or ev.get("damaged") or why in ("human:not_a_char", "human:damaged", "human:figure"):
            return False
    return True


def count(root: Path | str, book: str) -> dict | None:
    """本机产物目录里这册 seed_admit 的 {cells, review}；没有 seed_admit 返回 None。"""
    files = sorted((Path(root) / book / "seed_admit").glob("p*.json"))
    if not files:
        return None
    cells = review = 0
    for f in files:
        try:
            sa = json.loads(f.read_text(encoding="utf-8"))["seed_admit"]
        except (OSError, ValueError, KeyError):
            return None            # 有一页读不了，数就不准，宁可不写
        for col in sa.get("columns") or []:
            for c in col.get("chars") or []:
                cells += 1
                if is_pending(c):
                    review += 1
    return {"cells": cells, "review": review}


def merged(old: dict | None, label: str, stat: dict, at: str) -> dict:
    """把这个标签的数并进已有的 cv.packs，只留最近 KEEP 个标签（按写入时间）。"""
    d = dict(old or {})
    d[label] = {"cells": stat["cells"], "review": stat["review"],
                "rate": round(stat["review"] / stat["cells"], 5) if stat["cells"] else None, "at": at}
    if len(d) > KEEP:
        for k in sorted(d, key=lambda k: str((d[k] or {}).get("at") or ""))[: len(d) - KEEP]:
            d.pop(k, None)
    return d


def record(book: str, label: str, root: Path | str, steps: list[str] | None = None) -> bool:
    """存包后写看板。返回是否写了；永远不抛。"""
    try:
        if steps:                   # 只打了几步的包不算整册，不记人审率
            return False
        if not (os.environ.get("NEON_DATABASE_URL") or os.environ.get("GUJI_DATA_PG_DSN")):
            return False
        stat = count(root, book)
        if not stat or not stat["cells"]:
            return False
        from .online_lists import ident
        bid, ch = ident(book, os.environ.get("GUJI_WORKSPACE"))
        if not (bid and ch):
            return False
        from ._cv import connect
        at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with connect() as conn:
            row = conn.execute("SELECT extra->%s::text FROM progress.volume WHERE book_id = %s AND vol = %s", (KEY, bid, ch)).fetchone()
            old = row[0] if row else None
            payload = json.dumps({"extra": {KEY: merged(old if isinstance(old, dict) else None, label, stat, at)}}, ensure_ascii=False)
            conn.execute("SELECT progress.put_volume(%s, %s, %s::jsonb, %s)", (bid, ch, payload, "pipeline"))
        print(f"  ✓ 人审率已随包写看板：{book} {label} 待审 {stat['review']} / {stat['cells']} 格")
        return True
    except Exception as e:     # noqa: BLE001 —— 看板是附带的，写不了不影响存包
        print(f"  ⓘ 人审率没写进看板（{e}）；之后 `guji-manager progress-sync --fix` 会补")
        return False


def pack_of(extra: dict | None, label: str | None) -> dict | None:
    """看板某册的 extra 里，label 这个包的 {cells, review}（先看随包写的 cv.packs，再看旧的 cv.pack）。"""
    ex = extra or {}
    if not label:
        return None
    p = (ex.get(KEY) or {}).get(label)
    if isinstance(p, dict) and p.get("cells"):
        return {"label": label, **p}
    old = ex.get("cv.pack") or {}
    if old.get("label") == label and old.get("cells"):
        return {"label": label, "cells": old["cells"], "review": old.get("review", 0), "at": old.get("at")}
    return None
