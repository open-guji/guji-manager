# -*- coding: utf-8 -*-
"""把 AI 判定分析（浅层文意或联网深搜，放行与不确定都写）落成旁路 notes，待审单上显示（GM3 11-26）。

输入 TSV（UTF-8，首行表头），列：
  册  u  格号  AI判  置信(high|mid|low)  状态  理由  出处  [候选]
  - 状态：released（已放行写了裁定）｜pending（没放行，留人审）｜unsure（判不了）
  - 理由：判为何字、文意依据、为何没放行，≤约 350 字；
  - 出处：多条用「 | 」分隔，每条「URL 原句前30字」；无出处写「查无」。
用法：python3 write_notes.py in.tsv <feedback根>/notes/<册>.jsonl --level L3 --model <模型> [--batch 名]
一格一行追加（后写覆盖先写，load_notes 取最后一条）。键：book+u（主）、cell（辅）。
待审单出单前跑 `python -m guji_manager.review.dian_attach`（卡上带 book、u 才能按 u 对上）。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys

URL = re.compile(r"(https?://\S+)\s*(.*)")


def row_to_note(r: dict, level: str, model: str, batch: str) -> dict:
    ev = []
    for part in (r.get("出处") or "").split(" | "):
        m = URL.match(part.strip())
        if m:
            ev.append({"url": m.group(1), "quote": m.group(2)[:60], "source_kind": "other_book"})
    status = (r.get("状态") or "").strip()
    why = (r.get("理由") or "").strip()
    if status in ("released", "pending", "unsure"):
        why = {"released": "已放行；", "pending": "未放行；", "unsure": "判不了；"}[status] + why
    item = {"level": level, "model": model, "char": (r.get("AI判") or "").strip(), "conf": (r.get("置信") or "").strip(),
            "why": why, "status": "found" if ev else "not_found", "evidence": ev}
    cands = [c for c in re.split(r"[/、,\s]+", r.get("候选") or "") if c]
    note = {"book": r["册"].strip(), "u": int(r["u"]), "cell": (r.get("格号") or "").strip() or None,
            "batch": batch, "trace": [item]}
    if cands:
        note["cands"] = cands
    return note


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv")
    ap.add_argument("out")
    ap.add_argument("--level", default="L3")
    ap.add_argument("--model", default="")
    ap.add_argument("--batch", default="")
    a = ap.parse_args(argv)
    n = 0
    with open(a.tsv, encoding="utf-8", newline="") as f, open(a.out, "a", encoding="utf-8") as o:
        for r in csv.DictReader(f, delimiter="\t"):
            if not r.get("u"):
                sys.exit(f"✗ 缺 u：{r.get('格号')}（先用 guji uid 补，裁定与笔记都按 u 挂）")
            o.write(json.dumps(row_to_note(r, a.level, a.model, a.batch), ensure_ascii=False) + "\n")
            n += 1
    print(f"{a.out}: 追加 {n} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
