#!/usr/bin/env python3
"""「落定」清单校验（只读）：v0.1 之后把确定的待审格写成人裁／AI 裁定事件之前，先过这一关。

史记 11-27 的做法（SJ-settle-1127-*）是书线手写脚本：tsv → 事件。校验这一步各书都一样，抽到这里；
写事件那一步要 cv（make_event、盖 u），仍由各书线脚本或后续 `guji` 子命令接，本脚本不写任何东西。

TSV 首行表头，必有列：
  vol    册号（vol29）
  u      字格永久编号（正整数；撞号时按（册，u）认，所以册必填）
  char   落定的字（单个汉字，或 ○ □ 〇 这类阙字符号）
  basis  依据（一句话：看图／上下文／参校字…，不许空）
可选列：
  cur    book-text 现字；  cands  候选字（空格或逗号分隔）——给了才查刻形字对
      python3 settle_check.py list.tsv --batch SJ-settle-1127-vol29 [--carve-book 全唐文 | --carve-pairs a.tsv:b.tsv]

查什么（错＝退出码 1；警告不影响）：
  错  缺列／空必填；u 不是正整数；char 不是单字；同（册,u）两行字不同；批名含空白或斜杠；
      落定字与 cur/cands 里的字构成「按刻形记」的字对（carve_pairs，留人看图，不放行）
  警  同（册,u）重复且字相同（只会写一条）；char＝cur（没变，无需落定）
**不查**：u 是否在库里、该格是否真在待审里——那要连中心库，由写事件那一步（`guji pending-settle` 对账）负责。
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from carve_pairs import blocked, load  # noqa: E402

REQUIRED = ("vol", "u", "char", "basis")
SYMBOLS = set("○〇□■◇")
BATCH_RE = re.compile(r"^[\w\-.~一-鿿]+$")


def is_char(s: str) -> bool:
    if len(s) != 1:
        return False
    o = ord(s)
    return s in SYMBOLS or 0x3400 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF or 0x20000 <= o <= 0x3FFFF


def check(rows: list[dict], pairs: dict[str, set[str]] | None = None, batch: str | None = None) -> tuple[list[str], list[str]]:
    """→ (错误, 警告)；行号从表头下一行算 2。"""
    errs: list[str] = []
    warns: list[str] = []
    if batch is not None and not BATCH_RE.match(batch):
        errs.append(f"批名 {batch!r} 不合规（只许字母数字汉字和 - _ . ~，不含空白斜杠）")
    seen: dict[tuple[str, int], tuple[str, int]] = {}
    for i, r in enumerate(rows, start=2):
        v = {k: (r.get(k) or "").strip() for k in (*REQUIRED, "cur", "cands")}
        miss = [k for k in REQUIRED if not v[k]]
        if miss:
            errs.append(f"第{i}行：必填列为空：{'、'.join(miss)}")
            continue
        if not v["u"].isdigit() or int(v["u"]) <= 0:
            errs.append(f"第{i}行：u={v['u']!r} 不是正整数")
            continue
        if not is_char(v["char"]):
            errs.append(f"第{i}行：char={v['char']!r} 不是单个汉字或阙字符号")
            continue
        key = (v["vol"], int(v["u"]))
        if key in seen:
            j, ch = seen[key][1], seen[key][0]
            (errs if ch != v["char"] else warns).append(
                f"第{i}行：（{key[0]},u={key[1]}）与第{j}行重复，" + (f"字不同（{ch}／{v['char']}）" if ch != v["char"] else "字相同，只会写一条"))
        else:
            seen[key] = (v["char"], i)
        if v["cur"] and v["cur"] == v["char"]:
            warns.append(f"第{i}行：（{key[0]},u={key[1]}）落定字与现字相同（{v['char']}），无需落定")
        if pairs:
            cands = [c for c in re.split(r"[\s,，、]+", v["cands"]) if c]
            if blocked(v["char"], cands, pairs, v["cur"]):
                errs.append(f"第{i}行：（{key[0]},u={key[1]}）落定字 {v['char']} 与候选/现字构成按刻形记的字对，留人看图，不放行")
    return errs, warns


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="落定清单校验（只读）")
    ap.add_argument("tsv")
    ap.add_argument("--batch", default=None, help="事件批名，如 SJ-settle-1127-vol29（校验格式）")
    ap.add_argument("--carve-book", default=None, help="用 carve_pairs/<书>.tsv 的刻形字对表")
    ap.add_argument("--carve-pairs", default=None, help="刻形字对表路径，冒号分隔多张")
    a = ap.parse_args(argv)
    with open(a.tsv, encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f, delimiter="\t")
        cols = rd.fieldnames or []
        rows = list(rd)
    lack = [k for k in REQUIRED if k not in cols]
    if lack:
        print(f"✗ 缺表头列：{'、'.join(lack)}（必有 {'、'.join(REQUIRED)}）")
        return 1
    pairs = load(path=a.carve_pairs.split(":")[0] if a.carve_pairs and ":" not in a.carve_pairs else None,
                 book=a.carve_book) if (a.carve_book or a.carve_pairs) else None
    if a.carve_pairs and ":" in a.carve_pairs:
        pairs = {}
        for p in a.carve_pairs.split(":"):
            for k, s in load(path=p).items():
                pairs.setdefault(k, set()).update(s)
    errs, warns = check(rows, pairs, a.batch)
    for w in warns:
        print("警 " + w)
    for e in errs:
        print("错 " + e)
    print(f"{'✗' if errs else '✓'} {len(rows)} 行，错 {len(errs)}，警 {len(warns)}"
          + ("" if pairs is not None else "（未给刻形字对表，没查刻形对）"))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
