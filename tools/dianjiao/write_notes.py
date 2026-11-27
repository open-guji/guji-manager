# -*- coding: utf-8 -*-
"""把 AI 判定分析（浅层文意或联网深搜，放行与不确定都写）落成 notes 行，进中心库 ai_notes 表（GM3 11-27）。

输入 TSV（UTF-8，首行表头），列：
  册  u  格号  AI判  置信(high|mid|low)  状态  一句话  详情  检索  出处  [候选]
  - 状态：released（已放行）｜pending（没放行，有倾向）｜unsure（判不了）
  - 一句话：≤40 字，常显，如「倾向曰·高；三家註卷15同；现字日」；缺省取详情前 38 字
  - 详情：≤300 字，折叠：文意依据、对位结果、为何置信如此、人审看什么
  - 检索：检索记录，多条用「 ; 」分隔，每条「来源|结果|说明」，结果取 同字／异字／查无／取不到；
          浅层判没检索就留空（网站显示「无检索」）；**检索过的要写，包括没查到的**
  - 出处：URL 或本地文件，多条「 | 」分隔，每条「URL 原句前30字」
  兼容旧列「理由」＝详情。
用法：python3 write_notes.py in.tsv <feedback根>/notes/<册>.jsonl --level L2|L3 --model <模型> [--batch 名]
一格一行追加（后写覆盖先写）。键：book＋u。写完 `guji db push`，notes 进 ai_notes 表，出待审单时 dian_attach 带上。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys

URL = re.compile(r"(https?://\S+)\s*(.*)")


def _log(text: str) -> list[dict]:
    out = []
    for part in (text or "").split(" ; "):
        f = [x.strip() for x in part.split("|")]
        if f and f[0]:
            out.append({"src": f[0], "r": f[1] if len(f) > 1 else "", "t": f[2] if len(f) > 2 else ""})
    return out


def row_to_note(r: dict, level: str, model: str, batch: str) -> dict:
    ev = []
    for part in (r.get("出处") or "").split(" | "):
        m = URL.match(part.strip())
        if m:
            ev.append({"url": m.group(1), "quote": m.group(2)[:60], "source_kind": "other_book"})
    status = (r.get("状态") or "").strip()
    detail = (r.get("详情") or r.get("理由") or "").strip()
    item = {"level": level, "model": model, "char": (r.get("AI判") or "").strip(), "conf": (r.get("置信") or "").strip(),
            "why": detail[:300], "s": (r.get("一句话") or "").strip()[:40],
            "status": status or ("found" if ev else "not_found"), "evidence": ev, "log": _log(r.get("检索") or "")}
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
