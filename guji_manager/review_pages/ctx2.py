"""文意两路判定（ctx2）：整格形近组靠「两个干净读者只看前后文」自行判，两路一致且都 high 才写人裁。

用在「文意能定、图上难判」的字组：日曰、己已巳、面而、還環、末未、大太、問間、論諭 等
（Sheldon 11-08 定：日曰/己已巳按文意判，不按他点的）。形状层拿不准的（冡冢、子于等）不在此列。

流程（两端都在会话里做，管线不调 Anthropic API）：
  1. `review-pages ctx2-export --packs <目录> --groups 日曰,己已巳 --out o/`
       <目录>/<册>/seed_admit/pNNNN.json（`guji products pack fetch` 取下后保留 seed_admit）；
       只取整格（a/b 半格归切分）、待审（admit=false）；--include-admitted 连放行格一起复核。
       写 o/cells.json（每格 n,id,g,l,r：前后各 5 字，不含整理本、放行字、图）与 o/prompt_A.txt、o/prompt_B.txt
       （候选顺序正反）。
  2. 两个干净会话（不同上下文）分别读 prompt_A、prompt_B，各回 JSON：[{"n":1,"ch":"日","conf":"high"},…]，存成 A.json、B.json。
  3. `review-pages ctx2-import --cells o/cells.json --a A.json --b B.json --out o/`
       两路字相同且都 high → 写 o/判定.tsv 的「文意定字」与 o/import草案.jsonl（可交 enrich_events 写人裁事件，
       source 写「文意两路 <轮>」）；不一致或低把握 → 「待审」，并入给人的大批页作「文意拿不准」。
注意：读者看不到图，邻字也可能是讹字；把握低就写 low。人裁事件写入前先给总览看清单。
"""
from __future__ import annotations

import csv
import glob
import json
import re
from pathlib import Path

# 组名 → 候选字（顺序无意义；prompt 里正反各排一次）
GROUPS = {
    "日曰": ("日", "曰"), "己已巳": ("己", "已", "巳"), "面而": ("面", "而"), "還環": ("還", "環"),
    "未末": ("未", "末"), "大太": ("大", "太"), "問間": ("問", "間"), "論諭": ("論", "諭"),
}
DEFAULT_GROUPS = ("日曰", "己已巳")
CTX_N = 5
GROUP_PROMPT = {"日曰": "ry", "己已巳": "jys"}

PROMPT = ("你是古籍整理员。下面每行有一个缺字格「□」及其前后各至多{n}个字（前后文字可能有个别讹误，"
          "前或后为空是因为到了列边界）。只凭上下文文意，在候选字里选一个，并给把握 high/low。"
          "不要猜别的字，选不出就写 low。只输出 JSON 数组：[{{\"n\":1,\"ch\":\"…\",\"conf\":\"high\"}},…]，"
          "共{m}项，不要别的文字。\n\n{lines}")


def _group_of(ch: str, groups) -> str | None:
    for g in groups:
        if ch in GROUPS[g]:
            return g
    return None


def collect(packs: str, groups=DEFAULT_GROUPS, include_admitted: bool = False) -> list[dict]:
    """从 <packs>/<册>/seed_admit/p*.json 取整格形近组格，附前后文。"""
    out = []
    for f in sorted(glob.glob(f"{packs}/*/seed_admit/p*.json")):
        for col in json.loads(Path(f).read_text(encoding="utf-8"))["seed_admit"]["columns"]:
            L = col["chars"]
            for k, ch in enumerate(L):
                if ch["id"][-1] in "ab":
                    continue
                if ch.get("admit") and not include_admitted:
                    continue
                g = _group_of(ch["char"], groups)
                if g is None:
                    continue
                out.append({"id": ch["id"], "g": g, "cur": ch["char"], "admit": bool(ch.get("admit")),
                            "l": "".join(x["char"] for x in L[max(0, k - CTX_N):k]),
                            "r": "".join(x["char"] for x in L[k + 1:k + 1 + CTX_N])})
    for n, c in enumerate(out, 1):
        c["n"] = n
    return out


def prompts(cells: list[dict], rev: bool) -> str:
    lines = []
    for c in cells:
        cand = list(GROUPS[c["g"]])
        if rev:
            cand.reverse()
        lines.append(f"{c['n']}. 〔{c['l']}〕□〔{c['r']}〕 候选：{'、'.join(cand)}")
    return PROMPT.format(n=CTX_N, m=len(cells), lines="\n".join(lines))


def _load(path):
    t = Path(path).read_text(encoding="utf-8")
    return json.loads(re.search(r"\[.*\]", t, re.S).group(0))


def decide(cells: list[dict], a: list[dict], b: list[dict]) -> list[dict]:
    """两路都选定且 high、字相同 → 定字；否则「待审」。"""
    ra = {x["n"]: x for x in a}
    rb = {x["n"]: x for x in b}
    rows = []
    for c in cells:
        x, y = ra.get(c["n"], {}), rb.get(c["n"], {})
        ok = (x.get("ch") == y.get("ch") and x.get("conf") == y.get("conf") == "high"
              and x.get("ch") in GROUPS[c["g"]])
        rows.append(dict(c, a=f"{x.get('ch')}/{x.get('conf')}", b=f"{y.get('ch')}/{y.get('conf')}",
                         char=x["ch"] if ok else "待审"))
    return rows


def write(rows: list[dict], out: str, rnd: str = "") -> dict:
    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)
    with open(o / "判定.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["格号", "组", "前5字", "后5字", "甲", "乙", "文意定字（两路一致双high才写，否则待审）", "当前字"])
        for r in rows:
            w.writerow([r["id"], r["g"], r["l"], r["r"], r["a"], r["b"], r["char"], r["cur"]])
    ok = [r for r in rows if r["char"] != "待审"]
    with open(o / "import草案.jsonl", "w", encoding="utf-8") as f:
        for r in ok:
            gid = GROUP_PROMPT.get(r["g"], r["g"])
            f.write(json.dumps({"group": gid, "ver": f"{gid}-l2-1", "l": r["l"], "r": r["r"],
                                "members": list(GROUPS[r["g"]]), "prompt": f"config/groups/{gid}/prompt.md",
                                "cells": [r["id"]], "char": r["char"], "conf": "high",
                                "why": f"两路盲读（±{CTX_N}字）一致 high{('（' + rnd + '）') if rnd else ''}"},
                               ensure_ascii=False) + "\n")
    return {"cells": len(rows), "decided": len(ok), "pending": len(rows) - len(ok)}
