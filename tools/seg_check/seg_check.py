"""切分核查一条龙（SJ 史記切分线，2026-11-11）：输入一轮出包（产物根＋列图／字块缓存），输出切分类问题清单。

把原来分散的几步并成一条命令、一个报告：
  1. 几何快筛（seg_detect.py）：逐格 flags，FOR/Fend/Fpatch/Lh/Lv = 装饰类，JZW（夹注半格并格）= 结构类；
  2. 漏切块（orphan.py）：列里整块墨不在任何格框里；
  3. 钉子核对：中心库 manual-cells 钉子列，cell_shrink 出的格号集合必须与钉子一致（格号不符＝结构类）；
     版式对格号（给 --layout）：非钉子列按 layout_slots 格位表比实出格号（格数不同＝版式不符，要看；格数相同只是编号不同＝版式编号差，多为题署列空位、单侧小注 a/b 约定，框对就不修）；
  4. 待审原因（guji_manager.review.causes）：A1/A3/A4/A5/A6/A9 这些「切分或对位」原因码，
     所在列有○（evidence.symbol）的归「○对位」，其余归「原因码·看图」（多为整理本列与图不齐，要看图确认框对）；
  5. 汇总成列清单：每列一行，给出 类（结构／装饰／对位）与 处置（需钉子＝要看图定框、公用＝交 A22、
     对位＝不归切分、已钉＝钉子列只复核）。另出每个「需看图」列的缩略图，方便逐列看。

用法（cwd 任意；先 `guji products pack fetch` 取包、`guji cache warm` 暖列图与字块缓存）：

    python tools/seg_check/seg_check.py --products <产物根> --cache <缓存根> --vols 01,02 \\
        --pins $GUJI_DATA_HOME/main/<工作区id>/feedback/verdicts/char-segmentation/manual-cells/items.jsonl \\
        --skip 01:39-52,01:121,01:127,01:138-139 --out <报告目录>

--skip 点名不归本筛的页（职名页、年表页、卷首题署页等，按书配）；p1–3 一律当卷首页单列。
退出码：0 = 无「需钉子」「格号不符」；3 = 有，要看报告。
"""
from __future__ import annotations

import argparse
import collections
import csv
import glob
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEG_CAUSES = {"A1", "A3", "A4", "A5", "A6", "A9"}
COSM_FLAGS = ("FOR", "Fend", "Fpatch", "Lh", "Lv")


def parse_skip(s: str) -> set[tuple[str, int]]:
    out = set()
    for part in filter(None, (x.strip() for x in (s or "").split(","))):
        v, pg = part.split(":")
        a, _, b = pg.partition("-")
        for p in range(int(a), int(b or a) + 1):
            out.add((v.zfill(2), p))
    return out


def page_kind(v: str, p: int, skip) -> str:
    if (v, p) in skip:
        return "点名跳过"
    if p <= 3:
        return "卷首页"
    return ""


def run_geom(prod, cache, vols, out: Path):
    cells, orph = out / "逐格flags.tsv", out / "漏切块.tsv"
    vs = ",".join(vols)
    py = sys.executable
    subprocess.run([py, str(HERE / "seg_detect.py"), prod, cache, vs, str(cells)], check=True)
    subprocess.run([py, str(HERE / "orphan.py"), prod, cache, vs, str(orph)], check=True)
    return cells, orph


def shrink_slots(prod, v):
    """{(page, col): {slot 串}}，从 cell_shrink 取字格（char 类）。"""
    out = collections.defaultdict(set)
    for f in glob.glob(f"{prod}/{v}/cell_shrink/p*.json"):
        for col in json.load(open(f))["char_index"]["columns"]:
            for c in col["chars"]:
                if c.get("cell_type") != "char":
                    continue
                _v, p, cn, s = c["id"].split(":")
                out[(int(p), int(cn))].add(s)
    return out


def check_pins(prod, vols, pins_path):
    """钉子列：cell_shrink 格号集合 vs 钉子格号集合。返回 {(v,p,c): 问题串或 ''}。"""
    res = {}
    if not pins_path or not os.path.exists(pins_path):
        return res
    pins = collections.defaultdict(list)
    for line in open(pins_path):
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("status", "active") != "active":
            continue
        a = d["anchor"]
        v = str(a["book"]).zfill(2)
        if v in vols:
            pins[v].append(((int(a["page"]), int(a["col"])), d["expected"]["cells"]))
    for v, items in pins.items():
        got = shrink_slots(prod, v)
        for (p, c), cells in items:
            want = {f"{x['slot']}{x.get('sub') or ''}" for x in cells if x.get("kind", "char") != "blank"}
            have = got.get((p, c), set())
            miss, extra = sorted(want - have, key=_sk), sorted(have - want, key=_sk)
            msg = ""
            if miss or extra:
                msg = f"钉子有产物无 {','.join(miss) or '-'}；产物有钉子无 {','.join(extra) or '-'}"
            res[(v, p, c)] = msg
    return res


def check_layout(prod, vols, layout_path, pinned):
    """版式对格号：layout_slots 每列格位（大字 N、小注 Na/Nb、半格 Na）对 cell_shrink 实出格号。
    钉子列不比（钉子说了算）。返回 {(v,p,c): 问题串}。"""
    res = {}
    if not layout_path or not os.path.exists(layout_path):
        return res
    want = collections.defaultdict(dict)
    for line in open(layout_path):
        d = json.loads(line)
        v = str(d["vol"]).zfill(2)
        if v not in vols:
            continue
        notes, half = set(d.get("notes") or []), set(d.get("half") or [])
        ids = set()
        for n in d["slots"]:
            if n in half:
                ids.add(f"{n}a")
            elif n in notes:
                ids |= {f"{n}a", f"{n}b"}
            else:
                ids.add(str(n))
        want[v][(int(d["page"]), int(d["col"]))] = ids
    for v in vols:
        got = shrink_slots(prod, v)
        for (p, c), ids in want[v].items():
            if (v, p, c) in pinned:
                continue
            have = got.get((p, c))
            if have is None:
                continue
            miss, extra = sorted(ids - have, key=_sk), sorted(have - ids, key=_sk)
            if miss or extra:
                res[(v, p, c)] = ("同数" if len(miss) == len(extra) else "异数") + f"：版式有产物无 {','.join(miss) or '-'}；产物有版式无 {','.join(extra) or '-'}"
    return res


def _sk(s):
    n = "".join(ch for ch in s if ch.isdigit())
    return (int(n or 0), s)


def seg_causes(prod, vols):
    """{(v,p,c): [(slot, code, 是否○相关)]}"""
    sys.path.insert(0, str(HERE.parent.parent))
    from guji_manager.review.causes import book_causes

    out = collections.defaultdict(list)
    for v in vols:
        res = book_causes(prod, v)
        hits = {k: r for k, r in res.items() if r["cause"] in SEG_CAUSES}
        if not hits:
            continue
        circ = set()   # 列里有○（evidence.symbol）的列：整理本不录○，整列对位会错开，A 码多由此来
        for f in glob.glob(f"{prod}/{v}/seed_admit/p*.json"):
            for col in json.load(open(f))["seed_admit"]["columns"]:
                for c in col["chars"]:
                    ev = c.get("evidence") or {}
                    if ev.get("symbol") == "○" or c.get("char") == "○":
                        _v, p, cn, _s = c["id"].split(":")
                        circ.add((int(p), int(cn)))
        for k, r in hits.items():
            p, c, s = k.split(":")
            out[(v, int(p), int(c))].append((s, r["cause"], (int(p), int(c)) in circ))
    return out


def aggregate(cells_tsv, orph_tsv, pins, causes, skip, layout=None):
    col = collections.defaultdict(collections.Counter)
    ex = collections.defaultdict(list)
    for r in csv.DictReader(open(cells_tsv), delimiter="\t"):
        v, p, c, s = r["格号"].split(":")
        for f in filter(None, r["flags"].split(",")):
            col[(v, int(p), int(c))][f] += 1
            ex[(v, int(p), int(c))].append(f"{s}{f}{'' if r['放行'] == 'True' else '*'}")
    for r in csv.DictReader(open(orph_tsv), delimiter="\t"):
        v, p, c = r["列"].split(":")
        col[(v, int(p), int(c))]["ORPH_" + r["位置"]] += 1
        ex[(v, int(p), int(c))].insert(0, f"漏切{r['位置']}{r['bbox']}")
    for k, lst in causes.items():
        for s, code, circle in lst:
            col[k]["○对位" if circle else code] += 1
            ex[k].append(f"{s}{code}{'○' if circle else ''}")
    for k, msg in pins.items():
        if msg:
            col[k]["PIN"] += 1
            ex[k].insert(0, "格号不符:" + msg)
        else:
            col[k]  # 钉子列也列出来，标已钉
    for k, msg in (layout or {}).items():
        col[k]["LAYOUT" if msg.startswith("异数") else "LAYOUT_ID"] += 1
        ex[k].insert(0, msg)
    rows = []
    for k in set(col) | set(pins):
        cn = col[k]
        struct = (cn["ORPH_mid"] * 5 + cn["JZW"] * 3 + cn["ORPH_head"] + cn["ORPH_tail"]
                  + cn["PIN"] * 10 + sum(cn[a] for a in SEG_CAUSES) * 2)
        cosm = sum(cn[f] for f in COSM_FLAGS)
        pg = page_kind(k[0], k[1], skip)
        if cn["PIN"]:
            cls, act = "结构", "格号不符"
        elif cn["LAYOUT"] and not pg:
            cls, act = "结构", "版式不符"
        elif cn["LAYOUT_ID"] and not pg and not struct:
            cls, act = "结构", "版式编号差"
        elif pg:
            cls, act = ("结构" if struct else "装饰" if cosm else "对位"), pg
        elif struct and k in pins:
            cls, act = "结构", "已钉·复核"
        elif struct - sum(cn[a] for a in SEG_CAUSES) * 2 > 0:
            cls, act = "结构", "需钉子"
        elif struct:
            cls, act = "对位", "原因码·看图"
        elif cn["○对位"]:
            cls, act = "对位", "对位（○）"
        elif cosm:
            cls, act = "装饰", "公用清格"
        elif k in pins:
            cls, act = "", "已钉"
        else:
            continue
        rows.append(dict(列=f"{k[0]}:{k[1]}:{k[2]}", 类=cls, 处置=act, 结构分=struct, 装饰分=cosm,
                         各项=json.dumps(dict(cn), ensure_ascii=False), 例格=" ".join(ex[k][:14])))
    order = {"格号不符": 0, "版式不符": 0.5, "需钉子": 1, "版式编号差": 1.5, "原因码·看图": 1.7, "已钉·复核": 2, "对位（○）": 3, "公用清格": 4, "已钉": 5}
    rows.sort(key=lambda r: (order.get(r["处置"], 9), -r["结构分"], -r["装饰分"]))
    return rows


def montage(prod, cache, rows, out: Path, limit=60):
    from PIL import Image, ImageDraw

    tiles = []
    for r in rows[:limit]:
        v, p, c = r["列"].split(":")
        p, c = int(p), int(c)
        img = f"{cache}/{v}/column_image/p{p:04d}c{c:02d}.png"
        if not os.path.exists(img):
            continue
        cs = json.load(open(f"{prod}/{v}/cell_shrink/p{p:04d}.json"))["char_index"]
        cells = [x for col in cs["columns"] for x in col["chars"]
                 if x["id"].split(":")[2] == str(c) and x.get("bbox_col")]
        im = Image.open(img).convert("RGB")
        d = ImageDraw.Draw(im)
        for x in cells:
            a, b, e, f = x["bbox_col"]
            d.rectangle([a, b, e, f], outline=(255, 0, 0) if x.get("cell_type") == "char" else (0, 160, 0), width=2)
            d.text((a + 2, b + 2), x["id"].split(":")[3], fill=(0, 0, 255))
        d.text((2, 2), r["列"], fill=(0, 128, 0))
        im.thumbnail((180, 2000))
        tiles.append(im)
    for i in range(0, len(tiles), 12):
        ch = tiles[i:i + 12]
        sh = Image.new("RGB", (186 * len(ch), max(t.height for t in ch)), "white")
        for j, t in enumerate(ch):
            sh.paste(t, (j * 186, 0))
        sh.save(out / f"需看图_{i // 12 + 1}.png")
    return len(tiles)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--products", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--vols", required=True)
    ap.add_argument("--pins", default="")
    ap.add_argument("--skip", default="")
    ap.add_argument("--layout", default="", help="版式格位表 layout_slots.jsonl（书语料 corpus/<参校>/），给了就比版式对格号")
    ap.add_argument("--out", required=True)
    ap.add_argument("--reuse-geom", action="store_true", help="out 里已有逐格flags/漏切块就不重算")
    a = ap.parse_args(argv)
    vols = [v.zfill(2) for v in a.vols.split(",")]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    skip = parse_skip(a.skip)
    if a.reuse_geom and (out / "逐格flags.tsv").exists():
        cells, orph = out / "逐格flags.tsv", out / "漏切块.tsv"
    else:
        cells, orph = run_geom(a.products, a.cache, vols, out)
    pins = check_pins(a.products, vols, a.pins)
    causes = seg_causes(a.products, vols)
    layout = check_layout(a.products, vols, a.layout, set(pins))
    rows = aggregate(cells, orph, pins, causes, skip, layout)
    with open(out / "列清单.tsv", "w") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["列"], delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    look = [r for r in rows if r["处置"] in ("格号不符", "版式不符", "需钉子", "已钉·复核", "原因码·看图", "版式编号差")]
    n_img = montage(a.products, a.cache, look, out)
    cnt = collections.Counter(r["处置"] for r in rows)
    flags = collections.Counter()
    for r in csv.DictReader(open(cells), delimiter="\t"):
        for fl in filter(None, r["flags"].split(",")):
            flags[fl] += 1
    lines = [f"# 切分核查 {','.join(vols)}", "",
             f"- 产物根 `{a.products}`，钉子 `{a.pins or '无'}`",
             "- 处置计数（按列）：" + "，".join(f"{k} {v}" for k, v in cnt.most_common()),
             "- 逐格 flags：" + "，".join(f"{k} {v}" for k, v in flags.most_common()),
             f"- 需看图列缩略图 {n_img} 列：`需看图_*.png`", "",
             "## 格号不符／版式不符／需钉子／已钉复核", ""]
    lines += [f"- {r['列']} {r['处置']}：{r['例格']}" for r in look] or ["- 无"]
    lines += ["", "## ○对位（不归切分，交对位／参校）", ""]
    lines += [f"- {r['列']}：{r['例格']}" for r in rows if r["处置"] == "对位（○）"] or ["- 无"]
    bad = sum(1 for r in look if r["处置"] in ("格号不符", "版式不符", "需钉子"))
    lines += ["", f"结论：{'有 %d 列要看图（格号不符、版式不符或需钉子）' % bad if bad else '0 格号不符、0 版式不符、0 需钉子'}"]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:6]))
    print(lines[-1])
    return 3 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
