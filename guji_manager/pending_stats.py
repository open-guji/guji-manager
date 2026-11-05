#!/usr/bin/env python3
"""全部待审格分类统计（A31，2026-10-28，sheldon「把统计待审并分类规范化、脚本化、直接查库」）。

只查中心库，不下产物包、不拉原图，全套 99 册约 5 秒：
  - 线上待审单：`files` 表 `feedback/lists/proofing/<文本号>/<册号>.pending.json`（每格自带成因码 cause，republish 发布时写入）
  - 全册格数：`progress.volume.cells_total`（算人审率）
  - 码位表：`files` 表 `config/codepoints.yaml`（判「码位已定」）
分类规则见 `guji_manager/taxonomy.py`，跟进方与口径见 ai-team `domain/CV/质检/待审分类规范.md`。

  guji-manager pending-stats --out /tmp/ps                 # 全套，写 report.md／cells.tsv／summary.json
  guji-manager pending-stats --vols 20-50 --out /tmp/ps
  guji-manager pending-stats --out /tmp/ps --prev old/summary.json   # 括号里写与上一份的增减
  guji-manager pending-stats --from-dir lists/ --out /tmp/ps        # 离线：目录里放 <册号>.pending.json

非正文页（册配置 `page_kinds` 的 roster 职名页、table 表格页、cover 书衣，及老写法 `row_segment.roster_pages`、
`border_detect_gate.table_pages`）的待审格单列「非正文」，不进待审数和人审率（cv 只优化正文，指标正文与非正文分开报；11-04 SJ 史記职名页）。
全册格数分母仍是 `progress.volume.cells_total`（含非正文页，库里没有分页格数），所以正文人审率略偏低。

统计的是「线上单」，不是 ★main 包：单子落后于 main 包时数字也落后（报告里列了每册单子的版本和时间，落后的先重出单）。
连库：GUJI_DATA_PG_DSN，或 NEON_DATABASE_URL（自动起 443 桥）。
过渡期直接 import open_guji_cv 的 datastore.connect、groups.registry（用户 10-27 允许），装了 cv 才能跑；离线 `--from-dir` 且待审单自带 `grp` 时不需要。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from . import diagnose
from .taxonomy import BIG, FIX, SUBS, _c, _ref, _tok, cause_of, cell_pos, classify, conc_tag

DEFAULT_WS, DEFAULT_TEXT = "siku-zongmu", "96mid1ogzk"


def parse_vols(spec: str | None) -> set[int] | None:
    if not spec:
        return None
    out: set[int] = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return out


#: 非正文页型 → 老写法 (Step, 参数)
NONBODY_KINDS = {"roster": ("row_segment", "roster_pages"), "table": ("border_detect_gate", "table_pages"),
                 "cover": ("border_detect_gate", "cover_pages")}


def _expand_pages(spec) -> set[str]:
    out: set[str] = set()
    for x in spec if isinstance(spec, (list, tuple)) else [spec]:
        if isinstance(x, bool) or x is None:
            continue
        for part in str(x).split(","):
            part = part.strip()
            if not part:
                continue
            a, _, b = part.partition("-")
            out |= {str(i) for i in range(int(a), int(b or a) + 1)}
    return out


def nonbody_of_yaml(raw: str) -> dict[str, str]:
    """册 yaml 原文 → {页号: 页型}（只收非正文页型 roster／table／cover；新写法 page_kinds 与老写法都认）。"""
    import yaml
    d = yaml.safe_load(raw) or {}
    pk, params = d.get("page_kinds") or {}, d.get("params") or {}
    out: dict[str, str] = {}
    for kind, (step, key) in NONBODY_KINDS.items():
        for spec in (pk.get(kind), (params.get(step) or {}).get(key)):
            if spec:
                out.update({pg: kind for pg in _expand_pages(spec)})
    return out


def load_nonbody(ws: str) -> dict[str, dict[str, str]]:
    """中心库 `books` 表的册 yaml 原文 → {册号(三位): {页号: 页型}}。"""
    from ._cv import connect
    with connect() as con:
        cur = con.cursor()
        cur.execute("select src_path, raw from books where ws=%s", (ws,))
        rows = cur.fetchall()
    out = {}
    for path, raw in rows:
        m = re.findall(r"\d+", Path(path).stem)
        if m and raw:
            nb = nonbody_of_yaml(raw)
            if nb:
                out[f"{int(m[-1]):03d}"] = nb
    return out


L3_MISSING = "文意 L3 未运行：本书缺 config/groups/book_prompt.json（seed_admit 会静默跳过所有文意组，待审偏高）"


def has_book_prompt(ws: str) -> bool:
    """中心库里本书有没有提示词变量文件；没有则 seed_admit 的文意 L3 一格都不问（`_l3_online` 遇 KeyError 跳过）。"""
    from ._cv import connect
    with connect() as con:
        cur = con.cursor()
        cur.execute("select 1 from files where ws=%s and src_path='config/groups/book_prompt.json' limit 1", (ws,))
        return cur.fetchone() is not None


def load_db(ws: str, text: str, vols: set[int] | None):
    """→ (lists {册号: doc}, cells_total {册号: n}, codepoints {另一码位: 本书码位})。"""
    from ._cv import connect
    with connect() as con:
        cur = con.cursor()
        cur.execute("select src_path, doc from files where ws=%s and src_path like %s", (ws, f"feedback/lists/proofing/{text}/%.pending.json"))
        lists = {}
        for p, d in cur.fetchall():
            n = Path(p).name[:3]
            if vols is None or int(n) in vols:
                lists[n] = d if isinstance(d, dict) else json.loads(d)
        cur.execute("select vol, cells_total from progress.volume where book_id=%s", (text,))
        total = {v: int(t) for v, t in cur.fetchall() if t}
        cur.execute("select raw from files where ws=%s and src_path='config/codepoints.yaml'", (ws,))
        row = cur.fetchone()
    cp: dict = {}
    if row:
        import yaml
        cp = (yaml.safe_load(row[0]) or {}).get("codepoints") or {}
    return lists, total, cp


def load_dir(path: Path, vols: set[int] | None):
    lists = {}
    for f in sorted(path.glob("*.pending.json")):
        n = f.name[:3]
        if vols is None or int(n) in vols:
            lists[n] = json.loads(f.read_text(encoding="utf-8"))
    return lists, {}, {}


@lru_cache(maxsize=None)
def _group_of(ch: str) -> str | None:
    from ._cv import groups_of
    gs = groups_of(ch)
    return gs[0].id if gs else None


def analyse(lists: dict, codepoints: dict, extra_cp: dict | None = None, lib_n=None,
            nonbody: dict | None = None) -> list[dict]:
    """→ 每格一行 {vol, cell, big, sub, key, owner, fix, conc, cause, kind}；kind＝body 或非正文页型（见 `load_nonbody`）。"""
    cp = {**codepoints, **(extra_cp or {})}
    decided = lambda a, b: cp.get(a) == b or cp.get(b) == a   # noqa: E731
    rows = []
    for vol, doc in sorted(lists.items()):
        cells = [c for c in doc.get("cells") or [] if c.get("review") != "human"]
        occ_page, page_n, col_n = Counter(), Counter(), Counter()
        for c in cells:
            pos = cell_pos(c["cell"])
            if pos:
                page_n[pos[0]] += 1
                col_n[pos[1]] += 1
                if cause_of(c) == "D":
                    occ_page[pos[0]] += 1
        m = re.findall(r"\d+", str(vol))
        nb = (nonbody or {}).get(f"{int(m[0]):03d}" if m else vol) or {}
        for c in cells:
            pos = cell_pos(c["cell"]) or ("?", "?")
            v = classify(c, occ_page_n=occ_page[pos[0]], decided=decided, group_of=_group_of, lib_n=lib_n)
            rows.append({"vol": vol, "cell": c["cell"], "big": v.big, "sub": v.sub, "key": v.key, "owner": v.owner,
                         "fix": v.fix, "conc": conc_tag(page_n[pos[0]], col_n[pos[1]]), "cause": cause_of(c) or "",
                         "pending_reason": c.get("pending_reason") or "unknown",
                         "src": str(c.get("src") or ""),
                         "kind": nb.get(str(pos[0]).lstrip("0") or "0", "body"),
                         "ref": _ref(c) or "", "top": next((_c(x) for x in c.get("lib_top") or []), "") or "",
                         "tok": ",".join(sorted(_tok(c))),
                         "slim": not any(k in c for k in ("ref", "ctx", "lib", "lib_top"))})   # 瘦单只有成因码（cls 11-04 起不出单，不能再拿它判）
    return rows


def summarize(rows: list[dict], lists: dict, total: dict) -> dict:
    """待审数、人审率只算正文格（kind=body）；非正文格数记在 n_nonbody。"""
    nonbody = Counter(r["vol"] for r in rows if r.get("kind", "body") != "body")
    rows = [r for r in rows if r.get("kind", "body") == "body"]
    by_sub, by_vol, keys, conc = Counter(), defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    by_reason = Counter(r["pending_reason"] for r in rows)
    by_src = Counter(r["src"] for r in rows if r.get("src"))   # 单上来源标记，如 seg_selfcheck（出单同字对照自检）
    for r in rows:
        by_sub[r["sub"]] += 1
        by_vol[r["vol"]][r["big"]] += 1
        by_vol[r["vol"]]["n"] += 1
        keys[r["sub"]][r["key"] or "—"] += 1
        conc[r["big"]][r["conc"]] += 1
    vols = {}
    for v, doc in lists.items():
        t = total.get(v) or total.get(str(int(v)))
        vols[v] = {"n": by_vol[v]["n"], "cells": t, "rate": (by_vol[v]["n"] / t) if t else None,
                   "by_big": {b: by_vol[v][b] for b in BIG if by_vol[v][b]},
                   "rev": doc.get("rev"), "cv": doc.get("cv_version"), "at": doc.get("routed_as_of"),
                   "slim": sum(1 for r in rows if r["vol"] == v and r["slim"]), "n_nonbody": nonbody[v]}
    return {"n": len(rows), "n_nonbody": sum(nonbody.values()), "by_reason": dict(by_reason), "by_src": dict(by_src), "by_sub": dict(by_sub), "keys": {k: dict(v) for k, v in keys.items()},
            "conc": {k: dict(v) for k, v in conc.items()}, "vols": vols}


def _d(now: int, prev) -> str:
    if prev is None:
        return ""
    d = now - prev
    return f"（{'+' if d > 0 else ''}{d}）" if d else "（0）"


def reason_specs() -> dict:
    """{pending_reason: (码, 名, 去向)}；真源 cv `review/pending_reason.py`，没装 cv 就只列英文名。"""
    try:
        from ._cv import pending_reason_specs as specs
    except (ImportError, AttributeError):
        return {}
    return {r.value: (sp.code, sp.label, sp.route.value) for r, sp in specs().items()}


def render_reasons(s: dict, prev: dict | None) -> list[str]:
    """按待审原因 pending_reason（sheldon 11-03 定，旧单没有的记 unknown）。"""
    n = s["n"] or 1
    pr = (prev or {}).get("by_reason", {})
    sp = reason_specs()
    out = ["## 零、按待审原因（pending_reason）", "",
           "原因码表真源 `open_guji_cv/review/pending_reasons.yaml`；单上没有这个字段的格记 `unknown`。", "",
           "| 原因 | 码 | 名 | 去向 | 格数 | 占比 |", "|---|---|---|---|---|---|"]
    route_n = Counter()
    for r, k in sorted(s.get("by_reason", {}).items(), key=lambda kv: -kv[1]):
        code, label, route = sp.get(r, ("", "", ""))
        route_n[route or "?"] += k
        out.append(f"| `{r}` | {code} | {label} | {route} | {k}{_d(k, pr.get(r, 0) if prev else None)} | {k / n:.1%} |")
    if sp:
        out += ["", "按去向：" + "；".join(f"{r} {k}（{k / n:.0%}）" for r, k in route_n.most_common())]
    return out + [""]


#: 单上 `src` 的中文名（review/reasons.py）
SRC_NAMES = {"seg_selfcheck": "同字对照自检（seg_selfcheck）"}


def render(s: dict, prev: dict | None, top: int, diag: list[str] | None = None) -> str:
    n = s["n"]
    ps = (prev or {}).get("by_sub", {})
    tot_cells = sum(v["cells"] or 0 for v in s["vols"].values())
    out = ["# 待审格分类统计", "",
           *([f"> **注意：{L3_MISSING}**", ""] if s.get("l3_missing") else []),
           f"口径：线上待审单（中心库 `files` 表），{len(s['vols'])} 册，待审 **{n}** 格"
           + (f"，占全册 {tot_cells} 格的 {n / tot_cells:.2%}" if tot_cells else "")
           + (f"；另有非正文页（职名、表格）待审 {s['n_nonbody']} 格，单列、不计入" if s.get("n_nonbody") else "")
           + "。分类规则 `open_guji_cv/review/taxonomy.py`；跟进方见 ai-team `domain/CV/质检/待审分类规范.md`。"
           + ("括号里是比上一份的增减。" if prev else ""), "",
           *render_reasons(s, prev),
           *([f"单上来源标记（已含在上面的原因里，单独数）：" + "；".join(f"{SRC_NAMES.get(k, k)} {v}{_d(v, ((prev or {}).get('by_src') or {}).get(k, 0) if prev else None)}"
                                                       for k, v in sorted(s["by_src"].items())), ""] if s.get("by_src") else []),
           *(diag or []),
           "## 一、大类／小类总账（旧分类，过渡期保留）", "",
           "| 小类 | 名 | 格数 | 占比 | 跟进方 | 处理方式 | 集中度（整页／整列／零散） |", "|---|---|---|---|---|---|---|"]
    by_big = Counter()
    for sub, k in s["by_sub"].items():
        by_big[SUBS[sub][0]] += k
    pb = Counter()
    for sub, k in ps.items():
        pb[SUBS[sub][0]] += k
    for big, (bname, _) in BIG.items():
        if not by_big[big]:
            continue
        cc = s["conc"].get(big, {})
        out.append(f"| **{big}** | **{bname}** | **{by_big[big]}**{_d(by_big[big], pb[big] if prev else None)} | {by_big[big] / n:.1%} | | | "
                   f"{cc.get('整页', 0)}／{cc.get('整列', 0)}／{cc.get('零散', 0)} |")
        for sub in sorted(k for k, v in SUBS.items() if v[0] == big and s["by_sub"].get(k)):
            _, name, owner, fix, _ = SUBS[sub]
            k = s["by_sub"][sub]
            out.append(f"| {sub} | {name} | {k}{_d(k, ps.get(sub, 0) if prev else None)} | {k / n:.1%} | {owner} | {FIX[fix]} | |")
    fixc = Counter()
    for sub, k in s["by_sub"].items():
        fixc[SUBS[sub][3]] += k
    out += ["", "按处理方式：" + "；".join(f"{FIX[f]} {fixc[f]}（{fixc[f] / n:.0%}）" for f in FIX if fixc[f]), "",
            "## 二、各小类的键（前 %d）" % top, "",
            "Z＝字组 id；M＝字对；L1＝缺字；L2／L3＝原因。", ""]
    for sub in sorted(s["keys"]):
        if sub[0] not in "ZMLR" or not s["by_sub"].get(sub):
            continue
        ks = sorted(s["keys"][sub].items(), key=lambda kv: -kv[1])
        out.append(f"- **{sub} {SUBS[sub][1]}**（{s['by_sub'][sub]} 格，{len(ks)} 个键）：" + "、".join(f"{k} {v}" for k, v in ks[:top]))
    out += ["", "## 三、分册", "",
            "| 册 | 待审 | 全册格 | 人审率 | " + " | ".join(BIG[b][0] for b in BIG if by_big[b]) + " | 单子 | cv | 出单时间 | 瘦单格 |",
            "|---|---|---|---|" + "---|" * (sum(1 for b in BIG if by_big[b]) + 4)]
    pv = (prev or {}).get("vols", {})
    for v, d in sorted(s["vols"].items()):
        out.append(f"| {v} | {d['n']}{_d(d['n'], pv.get(v, {}).get('n') if prev else None)} | {d['cells'] or '—'} | "
                   f"{'%.2f%%' % (d['rate'] * 100) if d['rate'] is not None else '—'} | "
                   + " | ".join(str(d["by_big"].get(b, 0)) for b in BIG if by_big[b])
                   + f" | {d['rev']} | {d['cv']} | {(d['at'] or '')[:16]} | {d['slim']} |")
    cvs = Counter(d["cv"] for d in s["vols"].values())
    slim = sum(d["slim"] for d in s["vols"].values())
    out += ["", "## 四、数据说明", "",
            f"- 单子 cv 版本不齐：" + "、".join(f"{k}×{v}" for k, v in sorted(cvs.items(), key=lambda kv: str(kv[0]))) + "。比较各册时带着这个前提。",
            f"- 瘦单格（单子里只有成因码、没有 ref／ctx／库候选）{slim} 格：O 类落 O0、Z 类字组 id 记 `?`，是因为该册单子发布时没带细节；重出单后自动变细。",
            "- 统计的是线上单，落后于 ★main 包时数字也落后；重出单见 `粗校进度填数/sync_online_lists.py`。"]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ws", default=DEFAULT_WS)
    ap.add_argument("--text", default=DEFAULT_TEXT, help="文本号（线上单目录名）")
    ap.add_argument("--vols", help="册号范围，如 20-50,56；缺省全部")
    ap.add_argument("--from-dir", type=Path, help="离线：读目录里的 <册号>.pending.json，不连库")
    ap.add_argument("--extra-codepoints", type=Path, help="再叠一份 {另一码位: 本书码位} 的 yaml（还没推库的码位）")
    ap.add_argument("--prev", type=Path, help="上一份 summary.json，报告里写增减")
    ap.add_argument("--glyph-db", type=Path, help="字形库 db（<工作区>/output/glyph-gN.db）：给了就把「整理本字库样本≤2」的成因 I 单列成 L4 库样本过少")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--nonbody-dir", type=Path, help="离线：册 yaml 所在目录（判非正文页）；连库时缺省读中心库 books 表")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    vols = parse_vols(a.vols)
    lists, total, cp = load_dir(a.from_dir, vols) if a.from_dir else load_db(a.ws, a.text, vols)
    extra = {}
    if a.extra_codepoints:
        import yaml
        raw = yaml.safe_load(a.extra_codepoints.read_text(encoding="utf-8")) or {}
        extra = raw.get("codepoints", raw)
    lib_n = None
    if a.glyph_db:
        import sqlite3
        from collections import defaultdict
        cnt = defaultdict(int)
        for ch, k in sqlite3.connect(a.glyph_db).execute("select char,sum(n_confirmed) from glyphs group by char"):
            cnt[ch] += k or 0
        lib_n = lambda ch: cnt.get(ch, 0)   # noqa: E731
    nonbody = None
    if a.nonbody_dir:
        nonbody = {}
        for f in sorted(a.nonbody_dir.glob("*.yaml")):
            m = re.findall(r"\d+", f.stem)
            nb = nonbody_of_yaml(f.read_text(encoding="utf-8")) if m else {}
            if nb:
                nonbody[f"{int(m[-1]):03d}"] = nb
    elif not a.from_dir:
        nonbody = load_nonbody(a.ws)
    rows = analyse(lists, cp, extra, lib_n, nonbody)
    s = summarize(rows, lists, total)
    if not a.from_dir and not has_book_prompt(a.ws):
        s["l3_missing"] = True
        print(f"警告：{L3_MISSING}", file=sys.stderr)
    body_rows = [r for r in rows if r["kind"] == "body"]
    prev = json.loads(a.prev.read_text(encoding="utf-8")) if a.prev else None
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "report.md").write_text(render(s, prev, a.top, diagnose.render(body_rows, lib_n)), encoding="utf-8")
    s["signals"] = diagnose.signals(body_rows, lib_n)
    (a.out / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    cols = ["vol", "cell", "pending_reason", "big", "sub", "key", "owner", "fix", "conc", "cause", "kind", "ref", "top", "tok"]
    (a.out / "cells.tsv").write_text("\n".join(["\t".join(cols)] + ["\t".join(str(r[c]) for c in cols) for r in rows]) + "\n", encoding="utf-8")
    print(f"待审 {s['n']} 格（另非正文 {s['n_nonbody']} 格），{len(lists)} 册 → {a.out}/report.md、cells.tsv、summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
