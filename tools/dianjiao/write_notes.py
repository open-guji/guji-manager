# -*- coding: utf-8 -*-
"""把 AI 判定分析（浅层文意或联网深搜，放行与不确定都写）落成 notes 行，进中心库 ai_notes 表（GM3 11-27）。

输入 TSV（UTF-8，首行表头），列：
  册  u  格号  AI判  置信(high|mid|low)  状态  一句话  详情  检索  出处  [候选]
  - 状态：released（已放行；**放行事件已进库才能写**，并须带 --release-batch 事件批名）｜pending（没放行，有倾向）｜unsure（判不了）
  - 一句话：≤40 字，常显，如「倾向曰·高；三家註卷15同；现字日」；缺省取详情前 38 字
  - 详情：≤300 字，折叠：文意依据、对位结果、为何置信如此、人审看什么
  - 检索：检索记录，多条用「 ; 」分隔，每条「来源|结果|说明」，结果取 同字／异字／查无／取不到；
          浅层判没检索就留空（网站显示「无检索」）；**检索过的要写，包括没查到的**
  - 出处：URL 或本地文件，多条「 | 」分隔，每条「URL 原句前30字」
  兼容旧列「理由」＝详情。
  **一句话／详情／检索都是给用户看的：纯中文白话，不写 L2／L3、high／mid／low 等代号和英文**（写法见 wiki 第七节）；
  漏进来的会被自动换成白话，换不掉的（如 pending、found）直接报错。
用法：python3 write_notes.py in.tsv <feedback根>/notes/<册>.jsonl --level L2|L3 --model <模型> [--batch 名]
一格一行追加（后写覆盖先写）。键：book＋u。写完 `guji db push`，notes 进 ai_notes 表，出待审单时 dian_attach 带上。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from guji_manager.review.dian_trace import jargon_hits, plain_zh  # noqa: E402

URL = re.compile(r"(https?://\S+)\s*(.*)")


def _log(text: str) -> list[dict]:
    out = []
    for part in (text or "").split(" ; "):
        f = [x.strip() for x in part.split("|")]
        if f and f[0]:
            out.append({"src": f[0], "r": f[1] if len(f) > 1 else "", "t": f[2] if len(f) > 2 else ""})
    return out


def row_to_note(r: dict, level: str, model: str, batch: str, release_batch: str = "") -> dict:
    ev = []
    for part in (r.get("出处") or "").split(" | "):
        m = URL.match(part.strip())
        if m:
            ev.append({"url": m.group(1), "quote": m.group(2)[:60], "source_kind": "other_book"})
    status = (r.get("状态") or "").strip()
    if status == "released" and not release_batch:
        sys.exit(f"✗ u={r.get('u')} 状态写了 released（已放行），但没给 --release-batch：放行事件先写进库，再带上事件批名写摘要；"
                 "没写事件就写 pending，否则网站摘要说已放行、待审单却还开着（SJ 11-27：gm3-deep-1126 批 42 格）")
    detail = plain_zh((r.get("详情") or r.get("理由") or "").strip())      # 给用户看的字样：内部代号／英文兜底换白话（模板第七节）
    item = {"level": level, "model": model, "char": (r.get("AI判") or "").strip(), "conf": (r.get("置信") or "").strip(),
            "why": detail[:300], "s": plain_zh((r.get("一句话") or "").strip())[:40],
            "status": status or ("found" if ev else "not_found"), "evidence": ev, "log": [{k: plain_zh(v) for k, v in e.items()} for e in _log(r.get("检索") or "")]}
    said = re.search(r"已放行|已经放行|放行了", " ".join([item["s"], item["why"]]))
    if said and status != "released":
        sys.exit(f"✗ u={r.get('u')} 摘要文字写了「{said.group(0)}」，状态却是 {status or '空'}：摘要里不写已放行，除非放行事件已进库（状态 released＋--release-batch）")
    bad = jargon_hits(" ".join([item["s"], item["why"], *(v for e in item["log"] for v in e.values())]))
    if bad:
        sys.exit(f"✗ u={r.get('u')} 摘要里还有内部代号或英文状态词 {bad}：给用户看的话要纯中文白话，见 wiki「AI分析两层做法与待审格摘要」第七节")
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
    ap.add_argument("--level", default="L2", help="L2＝浅层文意（未联网）；L3＝联网深搜。缺省 L2：没联网就别标 L3（GM3 11-27，QTW 031 的 9 条标错）")
    ap.add_argument("--model", default="")
    ap.add_argument("--batch", default="")
    ap.add_argument("--release-batch", default="", help="放行事件的批名；状态含 released 的行必须给（事件已写进库才写 released）")
    a = ap.parse_args(argv)
    n = 0
    with open(a.tsv, encoding="utf-8", newline="") as f, open(a.out, "a", encoding="utf-8") as o:
        for r in csv.DictReader(f, delimiter="\t"):
            if not r.get("u"):
                sys.exit(f"✗ 缺 u：{r.get('格号')}（先用 guji uid 补，裁定与笔记都按 u 挂）")
            o.write(json.dumps(row_to_note(r, a.level, a.model, a.batch, a.release_batch), ensure_ascii=False) + "\n")
            n += 1
    print(f"{a.out}: 追加 {n} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
