"""冷启动快审「高/低把握」两张页（全唐文 001–003 c35 第二层，2026-11-09 实例）。

输入：每册包里「库缺样本」那层的待审格（cell、参校本、库首位、cov、5b 前三、库例数、疑问）。
分档（依据 qtw-tools/冷启动加速/对照.md：5a=5b 且 cov .90–.95 对率 97.5%，5b 领先≥.03 对率 98.8%）：
  高把握＝（库首位＝5b 首位，或 5b 领先第二名≥LEAD_HI）且 cov≥COV_HI 且库里该字有例 → 带「本页其余都对」，整页一点确认；
  低把握＝其余（库与 5b 不一致且领先小、库 0 例、cov<.90）→ 一格一卡、没点不算对。
5b 领先量取自包里 rare_candidates 的 emb 候选（同一格 emb 分排序后首位减次位）。
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

LEAD_HI = 0.03
COV_HI = 0.90

HINT_HI = ("库首位与 5b 首位一致，或 5b 领先≥.03、cov≥.90（实测对率 97–99%）。卡左上角大字是机器判的字：认得对的不用点，"
           "页尾「本页其余都对」一点整页确认；不对的格点候选或填字，切坏点「切分有问题」。")
HINT_LO = ("库与 5b 不一致、库 0 例或 cov<.90 的格，逐格点选；没点的格不算对。卡左上角大字是机器判的字，对就点它，"
           "不对点候选或填字，切坏点「切分有问题」，实在认不出点「认不出」。")


def _read_rows(path: str) -> list[dict]:
    p = Path(path)
    if p.suffix == ".jsonl":
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return list(csv.DictReader(p.open(encoding="utf-8"), delimiter="\t"))


def lead_5b(pack_dir: str, cell: str, _cache: dict | None = None) -> float:
    """5b（rare_candidates 的 emb 候选）首位领先第二名多少；缺数据返回 0。pack_dir 用 {vol} 占位。"""
    vol, page = cell.split(":")[:2]
    f = Path(pack_dir.format(vol=vol)) / "rare_candidates" / f"p{int(page):04d}.json"
    cache = _cache if _cache is not None else {}
    if f not in cache:
        m = {}
        try:
            for col in json.loads(f.read_text(encoding="utf-8"))["rare_candidates"]["columns"]:
                for c in col["chars"]:
                    m[c["id"]] = c
        except (OSError, KeyError, ValueError):
            pass
        cache[f] = m
    c = cache[f].get(cell)
    b = sorted((x["score"] for x in (c or {}).get("candidates", []) if x.get("font") == "emb"), reverse=True)
    return (b[0] - b[1]) if len(b) > 1 else 0.0


def classify(rows: list[dict], pack_dir: str, crops_dir: str, skip_cells: set[str] = frozenset(),
             skip_chars: str = "", lead_hi: float = LEAD_HI, cov_hi: float = COV_HI):
    """返回 (hi_items, lo_items, stats)；items 可直接喂 `review-pages build char_card`。"""
    hi, lo, st, cache = [], [], {"skip_cell": 0, "skip_char": 0}, {}
    for r in rows:
        c = r["cell"]
        top5 = (list(r.get("5b前三") or "") or [r["库首位"]])[0]
        lib = r["库首位"]
        if c in skip_cells:
            st["skip_cell"] += 1; continue
        if top5 in skip_chars or lib in skip_chars:
            st["skip_char"] += 1; continue
        lead = lead_5b(pack_dir, c, cache)
        cov, ln = float(r.get("cov") or 0), int(r.get("库例数") or 0)
        high = (lib == top5 or lead >= lead_hi) and cov >= cov_hi and ln > 0
        cands: list[list[str]] = []
        for ch, why in [(top5, "5b首位"), (lib, "库首位"), (r.get("参校本"), "参校本")] + [(x, "5b次选") for x in list(r.get("5b前三") or "")[1:]]:
            if ch and ch not in (x[0] for x in cands):
                cands.append([ch, why])
        it = {"id": c, "pre": top5, "pre_conf": "high" if high else "mid", "kind": "高把握" if high else "低把握",
              "img": crops_dir.format(cell=c.replace(":", "_")), "ctx": "",
              "note": f"库首位 {lib}，cov {r.get('cov')}，库例数 {ln}，5b 领先 {lead:.3f}；参校本 {r.get('参校本')}；{r.get('疑问', '')}",
              "cands": cands}
        (hi if high else lo).append(it)
    lo.sort(key=lambda i: i["pre"])          # 低把握一格一卡，同判字挨着
    st.update(hi=len(hi), lo=len(lo))
    return hi, lo, st


def write_pages(out_dir: str, book: str, tag: str = "") -> dict:
    """按预设出两张页：高把握（per-card 3、带「本页其余都对」）、低把握（一格一卡、没点不算对）。"""
    from . import build as build_mod
    out = Path(out_dir)
    res = {}
    for key, per_card, rest_ok, hint, title in (
            ("hi", 3, True, HINT_HI, "高把握确认页"), ("lo", 1, False, HINT_LO, "低把握逐格页")):
        items = out / f"{key}.jsonl"
        if not items.exists():
            continue
        html = out / f"{key}.html"
        res[key] = build_mod.build("char_card", build_mod.read_items(str(items)), book, str(html),
                                   None, per_card, hint, set(), None, None, False, None, rest_ok=rest_ok)
        t = html.read_text(encoding="utf-8").replace("<title>一字一卡", f"<title>{title}{tag}", 1)
        html.write_text(t, encoding="utf-8")
    return res
