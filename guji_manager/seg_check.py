"""`guji seg check`：切分核查一条命令（A22，2026-11-12，《切分三方向》第 2 步）。

并了三套东西：SJ 史記切分快筛（原 `tools/seg_check/`，SJ 11-12 同意并入、命令留别名）、cv `scripts/seg_screen.py`
（edge_ink、orphan、整页列网…）、待审原因码。**判据都在 cv `eval/seg_screen.py`**，跑法在 cv `eval/seg_screen_run.py`；
本模块只做汇总：按列给 类（结构／装饰／对位）与 处置，出列清单、需看图的整列缩略图和报告。

处置（SJ 第 7 条，按看图先后排）：
- 钉子未生效：中心库有钉子、本页产物没用上（产物早于钉子），要从 row_segment 重跑；
- 格号不符：钉子列 cell_shrink 出的格号集合 ≠ 钉子（钉子列只比格号、不跑墨账，SJ 第 5 条）；
- 版式不符：非钉子列格位表格数 ≠ 实出（格数同只编号不同判过、只计数，SJ 第 4 条）；
- 需钉子：结构类 flag（漏切块、夹注并格 JZW、格高离群＝并格／拆格、列首列尾漏墨 edge_ink、格高对整页 PITCH、
  夹注半格宽 HALF、同字对照并格 MERGED／切笔 CLIP、格线劈字 CUT＝cv cut_through，过了 U-Net 归属裁判（弱档 CUT_WEAK 只当提示「劈字弱·笔画相触」）；
  对位串错 ALIGN＝cv align_drift，一列里连续对不上参校字、劈或并后整列错一格（史記 R017，11-14）；同页报出 ≥3 列的
  （cv 标 page）记 ALIGN_PAGE，只当提示「对位串错·整页」（透印、版式、整页没对上，SJ 抽看）。
  不按 A6／A9 原因码排除：劈出来的那格整理本本来就没字，r59 切分线钉的 23 列报出里 17 列带 A6／A9；R016 参校本缺字的 10 列只报 1 列）；
- 原因码·看图：只有切分／对位类待审原因码（A1/A3/A4/A5/A6/A9）；
- 已钉·复核：钉子列上有结构类 flag；
- 对位（○）：列里有○、原因码来自整理本不录○（只列不报，SJ 第 6 条）；
- 格高·参校证实：只有格高／半格宽离群、但参校字落在字形匹配前 3 名且邻格无反证的格（cv `geo_ref_ok`，2026-11-13 史記 R011／R013），
  只列不算结构、不挡闸；写本册抽看用（SJ 11-14：R011 那批里混有真错）；
- 公用清格：只有装饰类 flag（FOR／Fend／Fpatch／Lh／Lv／端格只有框线／同字对照带框 FRAME、FRAME_HEAVY＝重档／邻格笔画溢入 BLEED，未量过）；
- 点名跳过、卷首页：书配置点名的页、卷首几页单列（SJ 第 3 条）；
- 书级提示：书级口径里只当提示的旗（`BOOK_HINT_FLAGS`／`seg_check.hint_flags`，史記写本的 BLOCK），只有这类旗的列。

书配置（工作区 `workspace.yaml`）：

```yaml
seg_check:
  head_pages: 3                       # 每册前几页当卷首页单列（缺省 0）
  skip: {"01": "39-52,54,121,127,138-139", "04": "124"}   # 点名跳过的页：年表、卷首题署、整页御题印…
  hint_flags: [BLOCK]                 # 这本书只当提示的旗（缺省按 BOOK_HINT_FLAGS：史記 BLOCK；[] 全按结构）
```

同字对照切坏检测（2026-11-12 并进来，`--no-defect` 关）：`review/seg_defect.book_flags`，殿本尺子
（open-guji-dataset char-segmentation/frame-end-crop）上切笔查全 0.69、带框 0.60；表 `筛查/seg_defect.tsv`。

召回尺子：`guji seg ruler` 从中心库人裁（manual-cells、column-slots、抬头、拖线、solo-notes）列出人修过的列和修的时间；
`guji seg check --recall <尺子.tsv>` 只拿「修在本页产物之后」的列（产物里错还在）量各检查的查全。
"""
from __future__ import annotations

import collections
import csv
import json
import sys
from pathlib import Path

SEG_CAUSES = {"A1", "A3", "A4", "A5", "A6", "A9"}
COSM_FLAGS = ("FOR", "Fend", "Fpatch", "Lh", "Lv", "FRAME_ONLY", "FRAME", "FRAME_HEAVY", "BLEED")
#: 同字对照切坏检测（review/seg_defect）的 seg_kind → 列清单里的 flag
DEFECT_FLAG = {"merged": "MERGED", "clipped": "CLIP", "bleed": "BLEED", "frame_residue": "FRAME"}
RULER_SHARDS = {
    "manual-cells": "char-segmentation/manual-cells",
    "column-slots": "char-segmentation/column-slots",
    "head-raise": "char-segmentation/head-raise-columns",
    "touching-cuts": "char-segmentation/touching-cuts",
    "solo-notes": "char-segmentation/solo-notes",
}
LOOK = ("钉子未生效", "格号不符", "版式不符", "需钉子", "已钉·复核", "原因码·看图")
ORDER = {"钉子未生效": -1, "格号不符": 0, "版式不符": 0.5, "需钉子": 1, "原因码·看图": 1.7, "已钉·复核": 2, "对位（○）": 3,
         "公用清格": 4, "格高·参校证实": 4.5, "对位串错·整页": 4.6, "劈字弱·笔画相触": 4.7, "书级提示": 4.8, "已钉": 5}


# ── 书配置 ──────────────────────────────────────────────────────────────────

def parse_pages(s: str) -> set[int]:
    out: set[int] = set()
    for part in filter(None, (x.strip() for x in str(s or "").split(","))):
        a, _, b = part.partition("-")
        out |= set(range(int(a), int(b or a) + 1))
    return out


def parse_skip(s: str) -> dict[str, set[int]]:
    """`01:39-52,01:121,04:124` → {"01": {39…52, 121}, "04": {124}}。"""
    out: dict[str, set[int]] = collections.defaultdict(set)
    for part in filter(None, (x.strip() for x in (s or "").split(","))):
        v, _, pg = part.rpartition(":")
        if not v:
            raise ValueError(f"--skip 要写 册:页 或 册:起-止，给了 {part!r}")
        out[v] |= parse_pages(pg)
    return dict(out)


def book_config(ws: Path | None) -> dict:
    """工作区 `workspace.yaml` 的 `seg_check:`（没有就空）。"""
    if ws is None or not (Path(ws) / "workspace.yaml").exists():
        return {}
    import yaml
    d = yaml.safe_load((Path(ws) / "workspace.yaml").read_text(encoding="utf-8")) or {}
    return d.get("seg_check") or {}


#: 各书只当提示的 seg check 旗（书级口径，按 book-text 条目 id；工作区 workspace.yaml `seg_check.hint_flags` 写了就以它为准，
#: 写 [] 即全按结构算）。写本字距、笔画长短不匀，按刻本定的几何检查在写本上多是字形本来如此：
#: - 史記（文淵閣寫本）BLOCK 字块过高：SJ 11-14 r59 20/37/41/42 册新增约 170 列，抽 25 列看图全是长笔／笔画相触、0 真错；
#:   r59 之后人钉的 77 列里带 BLOCK 的 14 列都另有结构旗，只当提示不掉召回（A22 11-14）。殿本照旧算结构
#:   （ZM 11-13 vol06 147:3、vol07 133:7 靠它抓到、已钉）。
BOOK_HINT_FLAGS: dict[str, tuple[str, ...]] = {
    "988g3f0wsu": ("BLOCK",),
}


def book_hint_flags(ws: Path | None) -> tuple[str, ...]:
    """这本书只当提示的旗：workspace.yaml `seg_check.hint_flags` 优先，没写按 `BOOK_HINT_FLAGS`（认书用 workspace.yaml 的 id）。"""
    cfg = book_config(ws)
    if "hint_flags" in cfg:
        return tuple(str(f) for f in (cfg.get("hint_flags") or ()))
    if ws is None:
        return ()
    from .review import seg_defect as sd
    return BOOK_HINT_FLAGS.get(sd.book_id_of(ws), ())


def _skip_for(book: str, skip: dict[str, set[int]]) -> set[int]:
    """册号写法宽松：`01`、`1`、`vol01` 都认。"""
    keys = {book, book.lstrip("vol"), book.lstrip("vol").lstrip("0") or "0"}
    out: set[int] = set()
    for k, v in skip.items():
        kk = str(k)
        if kk in keys or kk.lstrip("0") in keys or kk.zfill(2) in keys:
            out |= v
    return out


# ── 待审原因码 ───────────────────────────────────────────────────────────────

def seg_causes(products_dir: Path, book: str) -> dict[tuple[int, int], list[tuple[str, str, bool]]]:
    """{(页, 列): [(格号, 原因码, 本列有○)]}，只要切分／对位类原因码。产物没有 seed_admit 就空。"""
    from .review.causes import book_causes
    root = Path(products_dir) / book
    if not (root / "seed_admit").exists():
        return {}
    hits = {k: r for k, r in book_causes(products_dir, book).items() if r["cause"] in SEG_CAUSES}
    if not hits:
        return {}
    circ = set()   # 列里有○（evidence.symbol）的列：整理本不录○，整列对位会错开，A 码多由此来
    for f in sorted((root / "seed_admit").glob("p*.json")):
        for col in json.loads(f.read_text(encoding="utf-8"))["seed_admit"]["columns"]:
            for c in col["chars"]:
                ev = c.get("evidence") or {}
                if ev.get("symbol") == "○" or c.get("char") == "○":
                    _v, p, cn, _s = c["id"].split(":")
                    circ.add((int(p), int(cn)))
    out: dict = collections.defaultdict(list)
    for k, r in hits.items():
        p, c, s = k.split(":")
        out[(int(p), int(c))].append((s, r["cause"], (int(p), int(c)) in circ))
    return dict(out)


# ── 按列汇总 ────────────────────────────────────────────────────────────────

def aggregate(book: str, rows: dict[str, list], pinned: set[tuple[int, int]], causes: dict, skip: set[int],
              head_pages: int = 0, hint_flags: tuple[str, ...] = ()) -> list[dict]:
    """cv 筛查的各张表＋原因码 → 按列一行（列、类、处置、结构分、装饰分、各项、例格）。
    `hint_flags`：这本书只当提示的旗（书级口径，`book_hint_flags`），计数改记 `<旗>_HINT`、不算结构分。"""
    col: dict = collections.defaultdict(collections.Counter)
    ex: dict = collections.defaultdict(list)

    def mine(r):
        return r[0] == book and str(r[2]).lstrip("-").isdigit()

    for r in rows.get("cell_flags", []):
        if not mine(r):
            continue
        k = (int(r[1]), int(r[2]))
        slot = str(r[4]).split()[0] if r[4] else ""
        for f in filter(None, str(r[3]).split(",")):
            col[k][f] += 1
            ex[k].append(f"{slot}{f}")
    for r in rows.get("orphan", []):
        if mine(r):
            k = (int(r[1]), int(r[2]))
            where = str(r[4]).split()[0]
            col[k]["ORPH_" + where] += 1
            ex[k].insert(0, f"漏切{where}{str(r[4]).split('bbox', 1)[-1].strip()}")
    for r in rows.get("edge_ink", []):
        if mine(r):
            k = (int(r[1]), int(r[2]))
            col[k]["EDGE"] += 1
            ex[k].insert(0, f"端外墨 {r[4]}")
    for r in rows.get("cell_size", []):
        if mine(r):
            k = (int(r[1]), int(r[2]))
            for kind in str(r[3]).split(","):
                col[k]["TALL" if kind == "tall" else "SHORT"] += 1
            ex[k].insert(0, f"格高离群 {r[4]}")
    for r in rows.get("block_tall", []):
        if mine(r):
            k = (int(r[1]), int(r[2]))
            col[k]["BLOCK"] += 1
            ex[k].insert(0, f"字块过高×{r[3]} {r[4]}")
    for r in rows.get("page_pitch", []):
        if mine(r):
            k = (int(r[1]), int(r[2]))
            col[k]["PITCH"] += 1
            ex[k].insert(0, f"格高对整页 列×{r[3]} {r[4]}")
    for r in rows.get("half_width", []):
        if mine(r):
            k = (int(r[1]), int(r[2]))
            col[k]["HALF"] += 1
            ex[k].insert(0, f"夹注半格宽 {r[4]}")
    for r in rows.get("cut_through", []):
        if mine(r):
            k = (int(r[1]), int(r[2]))
            weak = str(r[3]) == "弱"            # cv CUT_WEAK_MOVE：挪不到 1/3 格高，多是上下字笔画相触（SJ 11-14），只当提示
            col[k]["CUT_WEAK" if weak else "CUT"] += 1
            ex[k].insert(len(ex[k]) if weak else 0, f"劈字{r[3]!s} {str(r[4]).split('，')[0]}")
    for r in rows.get("seg_defect", []):
        if mine(r):
            k = (int(r[1]), int(r[2]))
            fl = DEFECT_FLAG.get(str(r[3]), str(r[3]))
            if fl == "FRAME" and "重" in str(r[4]):
                fl = "FRAME_HEAVY"
            col[k][fl] += 1
            ex[k].insert(0 if fl in ("MERGED", "CLIP") else len(ex[k]), f"{str(r[4]).split()[0]}{fl}")
    for r in rows.get("align_drift", []):       # cv eval/seg_screen.align_drift：对位串错·疑整列错位（R017）
        if mine(r):
            k = (int(r[1]), int(r[2]))
            whole_page = "page" in str(r[3]).split(",")     # 一页报出 ≥3 列：透印、版式、整页没对上，降成提示（SJ 11-14 抽看）
            col[k]["ALIGN_PAGE" if whole_page else "ALIGN"] += 1
            ex[k].insert(len(ex[k]) if whole_page else 0, f"对位串错({r[3]}) {r[4]}")
    for r in rows.get("geo_ref_ok", []):        # cv eval/seg_screen：格高／半格宽离群、但参校字证实，降成提示（不算结构）
        if mine(r):
            k = (int(r[1]), int(r[2]))
            col[k]["GEO_OK"] += 1
            ex[k].append(f"{r[4]}证实")
    for r in rows.get("edge_frame_only", []):
        if mine(r):
            k = (int(r[1]), int(r[2]))
            col[k]["FRAME_ONLY"] += 1
            ex[k].append(f"{r[3]}框条")
    for (p, c), lst in causes.items():
        for s, code, circle in lst:
            col[(p, c)]["○对位" if circle else code] += 1
            ex[(p, c)].append(f"{s}{code}{'○' if circle else ''}")
    for r in rows.get("pin_slots", []):
        if mine(r):
            k = (int(r[1]), int(r[2]))
            col[k]["PIN"] += 1
            ex[k].insert(0, "格号不符:" + str(r[4]))
    for r in rows.get("pin_stale", []):
        if mine(r):
            k = (int(r[1]), int(r[2]))
            col[k]["PIN_STALE"] += 1
            ex[k].insert(0, "钉子未生效（产物早于钉子，从 row_segment 重跑）")
    for r in rows.get("layout_slots", []):
        if mine(r):
            k = (int(r[1]), int(r[2]))
            col[k]["LAYOUT"] += 1
            ex[k].insert(0, str(r[4]))
    out = []
    for k in set(col) | set(pinned):
        cn = col[k]
        for f in hint_flags:
            if cn.get(f):
                cn[f + "_HINT"] = cn.pop(f)
        hinted = [f for f in hint_flags if cn.get(f + "_HINT")]
        cause_n = sum(cn[a] for a in SEG_CAUSES)
        struct = (cn["ORPH_mid"] * 5 + cn["JZW"] * 3 + cn["TALL"] * 3 + cn["BLOCK"] * 3 + cn["SHORT"] * 2 + cn["ORPH_head"]
                  + cn["MERGED"] * 3 + cn["CLIP"] * 2 + cn["PITCH"] * 2 + cn["HALF"] * 2 + cn["CUT"] * 2
                  + cn["ORPH_tail"] + cn["EDGE"]
                  + cn["PIN"] * 10 + cause_n * 2
                  + cn["ALIGN"] * 3)
        cosm = sum(cn[f] for f in COSM_FLAGS)
        pg = "点名跳过" if k[0] in skip else "卷首页" if k[0] <= head_pages else ""
        if cn["PIN_STALE"]:
            cls, act = "结构", "钉子未生效"
        elif cn["PIN"]:
            cls, act = "结构", "格号不符"
        elif cn["LAYOUT"] and not pg:
            cls, act = "结构", "版式不符"
        elif pg:
            cls, act = ("结构" if struct else "装饰" if cosm else "提示" if cn["GEO_OK"] or cn["ALIGN_PAGE"] or cn["CUT_WEAK"] or hinted else "对位"), pg
        elif struct and k in pinned:
            cls, act = "结构", "已钉·复核"
        elif struct - cause_n * 2 > 0:
            cls, act = "结构", "需钉子"
        elif struct:
            cls, act = "对位", "原因码·看图"
        elif cn["○对位"]:
            cls, act = "对位", "对位（○）"
        elif cosm:
            cls, act = "装饰", "公用清格"
        elif cn["GEO_OK"]:
            cls, act = "提示", "格高·参校证实"
        elif cn["ALIGN_PAGE"]:
            cls, act = "提示", "对位串错·整页"
        elif cn["CUT_WEAK"]:
            cls, act = "提示", "劈字弱·笔画相触"
        elif hinted:
            cls, act = "提示", "书级提示"
        elif k in pinned:
            cls, act = "", "已钉"
        else:
            continue
        out.append({"列": f"{book}:{k[0]}:{k[1]}", "类": cls, "处置": act, "结构分": struct, "装饰分": cosm,
                    "各项": json.dumps(dict(cn), ensure_ascii=False), "例格": " ".join(ex[k][:14])})
    out.sort(key=lambda r: (ORDER.get(r["处置"], 9), -r["结构分"], -r["装饰分"]))
    return out


def montage(rows: list[dict], out: Path, limit: int = 60) -> int:
    """需看图的列：列图上画 cell_shrink 字框（红＝字、绿＝空），12 列一张。"""
    from PIL import Image, ImageDraw

    from ._cv import (
        ImageCache,
        ProductStore,
        RunContext,
        column_key,
        load_book,
        page_key,
    )
    from ._cv import steps as _s  # noqa: F401
    store, cache = ProductStore(), ImageCache()
    ctxs: dict = {}
    tiles = []
    for r in rows[:limit]:
        book, p, c = r["列"].rsplit(":", 2)
        p, c = int(p), int(c)
        if book not in ctxs:
            ctxs[book] = RunContext(load_book(book), store, cache, log=lambda _: None)
        try:
            img = ctxs[book].materialize("column_image", column_key(p, c))
        except Exception:  # noqa: BLE001
            continue
        ci = store.read(book, "cell_shrink", page_key(p), "char_index")
        chars = [] if ci is None else [x for cc in ci.columns if cc.col == c for x in cc.chars if x.bbox_col]
        im = Image.open(img).convert("RGB")
        d = ImageDraw.Draw(im)
        for x in chars:
            a, b, e, f = x.bbox_col
            d.rectangle([a, b, e, f], outline=(255, 0, 0) if x.cell_type == "char" else (0, 160, 0), width=2)
            d.text((a + 2, b + 2), x.id.split(":")[3], fill=(0, 0, 255))
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


# ── 召回尺子 ────────────────────────────────────────────────────────────────

def ruler_rows(books: list[str] | None = None) -> list[dict]:
    """中心库里人修过的列：{book, page, col, source, status, ts（第一次写的时间）}。退役（stale）的照列。"""
    from ._cv import verdict_store
    vs = verdict_store()
    out = []
    for src, shard in RULER_SHARDS.items():
        p = Path(vs.items_path(shard))
        if not p.exists():
            continue
        seen = set()
        for ln in p.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            a = d.get("anchor") or {}
            if a.get("page") is None or a.get("col") is None or d.get("status") in ("rejected", "withdrawn"):
                continue                # 退役（stale）的也算：人当时确实修过这一列
            b = str(a.get("book"))
            if books and b not in books:
                continue
            k = (b, int(a["page"]), int(a["col"]), src)
            if k in seen:
                continue
            seen.add(k)
            hist = d.get("history") or []
            out.append({"book": b, "page": k[1], "col": k[2], "source": src, "status": d.get("status", "active"),
                        "ts": (hist[0].get("ts") if hist else "") or d.get("created_at", "")})
    out.sort(key=lambda r: (r["book"], r["page"], r["col"], r["source"]))
    return out


def _iso_to_epoch(ts: str) -> float | None:
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def page_run_ts(products_dir: Path, book: str) -> dict[int, float]:
    """row_segment 各页产物的生成时间（manifest 的 ts）。"""
    p = Path(products_dir) / book / "row_segment" / "_manifest.jsonl"
    out: dict[int, float] = {}
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                d = json.loads(ln)
                if d.get("ts") and str(d.get("key", "")).startswith("p"):
                    out[int(d["key"][1:])] = float(d["ts"])
    return out


def recall(ruler: list[dict], rows: dict[str, list], products_dir: Path, books: list[str],
           pages: set[int] | None, skip: dict[str, set[int]]) -> dict:
    """只量产物里错还在的人修列，看各检查、合起来各抓到几列。

    产物里错还在不在：manual-cells 看本页产物有没有用上钉子（`pin_stale` 表里的列＝没用上）；其余人裁看修的时间
    是否晚于本页 row_segment 产物的时间（manifest ts）。`pin_stale` 本身不算检查（它是拿钉子对的）。"""
    flagged: dict[str, set] = collections.defaultdict(set)
    for name, rs in rows.items():
        if name in ("pin_slots", "pin_stale", "geo_ref_ok"):     # geo_ref_ok 是按参校字豁免掉的，不算报出
            continue
        for r in rs:
            if str(r[2]).lstrip("-").isdigit():
                flagged[name].add((r[0], int(r[1]), int(r[2])))
            elif name in ("colnet_page", "layout_col_shift", "frame_margin"):
                flagged[name].add((r[0], int(r[1]), None))
    stale_pins = {(r[0], int(r[1]), int(r[2])) for r in rows.get("pin_stale", [])}
    run_ts = {b: page_run_ts(products_dir, b) for b in books}
    target, fixed = set(), set()
    for r in ruler:
        b, p, c = r["book"], int(r["page"]), int(r["col"])
        if b not in books or (pages and p not in pages) or p in _skip_for(b, skip):
            continue
        if r.get("source") == "manual-cells":
            (target if (b, p, c) in stale_pins else fixed).add((b, p, c))
            continue
        t, fix = run_ts.get(b, {}).get(p), _iso_to_epoch(r["ts"])
        if t is None or fix is None:
            continue
        (target if fix > t else fixed).add((b, p, c))
    fixed -= target
    target = sorted(target)

    def hit(k, name):
        return k in flagged[name] or (k[0], k[1], None) in flagged[name]
    per = {name: sum(hit(k, name) for k in target) for name in flagged}
    anyhit = {k for k in target if any(hit(k, n) for n in flagged)}
    return {"n": len(target), "already_fixed": len(fixed), "any": len(anyhit), "per_check": per,
            "missed": [f"{b}:{p}:{c}" for b, p, c in target if (b, p, c) not in anyhit]}


def defect_rows(books: list[str], pages: set[int] | None, skip: dict[str, set[int]], ws: Path | None) -> list[tuple]:
    """同字对照切坏检测（`review.seg_defect.book_flags`，有尺子：殿本列端 677 块，切笔查全 0.69／查准 0.84，
    带框 0.60／0.79）→ 筛查表行 (book, page, col, seg_kind, "格号 特征 程度")。书级阈值取 `SELFCHECK_BOOKS`
    （按工作区的 book-text id），没登记的书用殿本口径（查带框）。缺 seed_admit 等产物的册跳过并提示。"""
    from ._cv import ImageCache, ProductStore, cache_root, products_root
    from .review import seg_defect as sd
    store, cache = ProductStore(Path(products_root())), ImageCache(Path(cache_root()))
    bid = sd.book_id_of(ws) if ws else ""
    opts = sd.book_opts(bid) if bid else None
    if opts is None:
        opts = {"frame": True}
        print(f"⚠️ 同字对照切坏检测：认不出书（工作区 {ws or '未给'}，id {bid or '-'}）不在 SELFCHECK_BOOKS 里，按殿本口径跑"
              "（clip_edge_ink 0、查带框）；写本书这样会把长笔伸出格报成 CLIP，跑前给 -w <书仓>", file=sys.stderr)
    out = []
    for b in books:
        pgs = [p for p in sd._pages_of(store, b) if (not pages or p in pages) and p not in _skip_for(b, skip)]
        try:
            rs, _meta = sd.book_flags(b, store, cache, opts, pages=pgs)
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ {b}：同字对照切坏检测没跑成（{type(e).__name__}: {e}），列清单里不含并格／切笔／带框", file=sys.stderr)
            continue
        for r in rs:
            parts = str(r["格号"]).split(":")
            if len(parts) < 4:
                continue
            out.append((b, int(parts[-3]), int(parts[-2]), r["seg_kind"],
                        f"{parts[-1]} {r['特征']} {r.get('程度') or ''}".strip()))
    return out


def job_text(report: str) -> str:
    """把 report.md 改排成任务单输出：逐列清单在前、○对位只留列数、计数与结论压最后。
    任务库只存每条命令输出的尾巴（runner `run_commands` 留末 6000 字），尾巴被截时丢的是清单头，不是计数。"""
    head, body, tail, n_dui, sec = [], [], [], 0, None
    for ln in report.splitlines():
        if ln.startswith("## "):
            sec = ln
            continue
        if not ln.strip() or ln.startswith("# "):
            continue
        if ln.startswith("结论："):
            tail.append(ln)
        elif sec is None:
            head.append(ln)
        elif sec.startswith("## ○"):
            n_dui += ln.startswith("- ") and ln != "- 无"
        else:
            body.append(ln)
    return "\n".join(body + [f"- ○对位（不归切分）{n_dui} 列，明细见 report.md"] + head + tail)


# ── 一条命令 ────────────────────────────────────────────────────────────────

def run(books: list[str], out: Path, *, pages: set[int] | None = None, skip: dict[str, set[int]] | None = None,
        head_pages: int = 0, cell_checks: bool = True, causes: bool = True, montage_limit: int = 60,
        ruler_tsv: Path | None = None, defect: bool = True, ws: Path | None = None) -> tuple[str, int]:
    from ._cv import products_root
    try:
        from ._cv import screen_seg_book, write_seg_screen_report
    except (ImportError, AttributeError) as e:
        raise SystemExit(f"❌ 装的 cv 没有 eval/seg_screen_run（cv #1447，2026-11-12 起的 dev）：先升级 cv（{e}）")
    skip = skip or {}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows: dict[str, list] = {}
    counts: dict = {}
    pinned_all: dict[str, set] = {}
    prod = Path(products_root())
    for b in books:
        screen_seg_book(b, pages, False, rows, counts, cell_checks=cell_checks)
        from ._cv import resolved_manual_cells
        try:
            pinned_all[b] = {(int(p), int(c)) for p, c in resolved_manual_cells(b)}
        except Exception:  # noqa: BLE001
            pinned_all[b] = set()
    if defect:
        rows["seg_defect"] = defect_rows(books, pages, skip, ws)
    write_seg_screen_report(rows, counts, out / "筛查")
    allrows = []
    hint = book_hint_flags(ws)
    if hint:
        print(f"ℹ️ 本书只当提示的旗（书级口径）：{', '.join(hint)}", file=sys.stderr)
    for b in books:
        cz = seg_causes(prod, b) if causes else {}
        if pages:
            cz = {k: v for k, v in cz.items() if k[0] in pages}
        stale = {(int(r[1]), int(r[2])) for r in rows.get("pin_stale", []) if r[0] == b}
        pinned = {k for k in pinned_all[b] if (not pages or k[0] in pages) and k not in stale}
        allrows += aggregate(b, rows, pinned, cz, _skip_for(b, skip), head_pages, hint)
    allrows.sort(key=lambda r: (ORDER.get(r["处置"], 9), -r["结构分"], -r["装饰分"]))
    fields = ["列", "类", "处置", "结构分", "装饰分", "各项", "例格"]
    with open(out / "列清单.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(allrows)
    look = [r for r in allrows if r["处置"] in LOOK]
    n_img = montage(look, out, montage_limit) if look else 0
    cnt = collections.Counter(r["处置"] for r in allrows)
    flags = collections.Counter(f for r in rows.get("cell_flags", []) for f in str(r[3]).split(",") if f)
    flags.update(DEFECT_FLAG.get(str(r[3]), str(r[3])) + ("重" if "重" in str(r[4]) else "")
                 for r in rows.get("seg_defect", []))
    same = sum(c.get("layout_same_count", 0) for c in counts.values())
    lines = [f"# 切分核查 {','.join(books)}", "",
             f"- 产物根 `{prod}`；页 {'全部' if not pages else ','.join(map(str, sorted(pages)))}",
             "- 处置计数（按列）：" + ("，".join(f"{k} {v}" for k, v in cnt.most_common()) or "无"),
             "- 逐格 flags：" + ("，".join(f"{k} {v}" for k, v in flags.most_common()) or "无"),
             f"- 版式格数同、编号不同（判过）：{same} 列",
             f"- 需看图列缩略图 {n_img} 列：`需看图_*.png`；各项检查原表在 `筛查/`", ""]
    if ruler_tsv:
        rl = list(csv.DictReader(open(ruler_tsv, encoding="utf-8"), delimiter="\t"))
        for r in rl:
            r["page"], r["col"] = int(r["page"]), int(r["col"])
        rc = recall(rl, rows, prod, books, pages, skip)
        (out / "召回.json").write_text(json.dumps(rc, ensure_ascii=False, indent=1), encoding="utf-8")
        pct = f"{rc['any'] / rc['n']:.0%}" if rc["n"] else "—"
        lines += ["## 召回（人修过、修在产物之后的列）", "",
                  f"- 量了 {rc['n']} 列（另 {rc['already_fixed']} 列产物已带上人修，不量）；任一检查抓到 {rc['any']} 列（{pct}）",
                  "- 各检查：" + ("，".join(f"{k} {v}" for k, v in sorted(rc["per_check"].items(), key=lambda t: -t[1]) if v)
                                 or "无"),
                  f"- 漏掉的列：{' '.join(rc['missed'][:40]) or '无'}", ""]
    lines += ["## 钉子未生效／格号不符／版式不符／需钉子／已钉复核／原因码看图", ""]
    lines += [f"- {r['列']} {r['处置']}：{r['例格']}" for r in look] or ["- 无"]
    lines += ["", "## ○对位（不归切分，交对位／参校）", ""]
    lines += [f"- {r['列']}：{r['例格']}" for r in allrows if r["处置"] == "对位（○）"] or ["- 无"]
    bad = sum(1 for r in look if r["处置"] in ("钉子未生效", "格号不符", "版式不符", "需钉子"))
    lines += ["", f"结论：{'有 %d 列要处理（钉子未生效、格号不符、版式不符或需钉子）' % bad if bad else '0 钉子未生效、0 格号不符、0 版式不符、0 需钉子'}"]
    text = "\n".join(lines) + "\n"
    (out / "report.md").write_text(text, encoding="utf-8")
    return text, (3 if bad else 0)
