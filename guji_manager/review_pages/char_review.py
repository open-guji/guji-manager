"""冷启动快审页（char_grid）的生成与落库：原 ai-team 冷启动快审流程/模板 的
char_review_sheet.py（只留 --grid 全对点错模式）、pull_char_review.py、ingest_char_review.py。

  sheet   <工作区> <册> <out.html> [--grid 30] [--per-char 14] [--unadmitted]
          借来的字形库首位字 ＝ 整理本字的格，按字归并，每字取像素匹配度最高的格，出 char_grid 页。
          只读产物（glyph_match/align_ref/seed_admit）和 cache/<册>/char_patch，不写库。
  pull    rows.json out.json    把后台 review 集合导出的文档合成 ingest 吃的 JSON
  ingest  result.json [--batch NAME] [--dry-run]
          ok 格写 confirm(v=confirm, shape=字) 事件（actor=user、source=char_review）并跑 glyphdb_admit；
          需要 GUJI_WORKSPACE；只写本机 feedback/events 和 glyph.db，不推中心库。
"""
from __future__ import annotations

import argparse
import base64
import collections
import glob
import io
import json
import os
import re
import sys
from pathlib import Path


def load(prod: Path):
    gm, ar, sa = {}, {}, {}
    for f in glob.glob(str(prod / "glyph_match/p*.json")):
        for c in json.load(open(f, encoding="utf-8"))["glyph_match"]["columns"]:
            for r in c["chars"]:
                gm[r["id"]] = r
    for f in glob.glob(str(prod / "align_ref/p*.json")):
        d = json.load(open(f, encoding="utf-8"))["align_ref"]
        for c in d["chars"]:
            if c["align_op"] in ("equal", "replace"):
                ar[c["id"]] = c["align_char"]
        for c in d.get("coord", []):
            if c.get("ref_char"):
                ar.setdefault(c["id"], c["ref_char"])
    for f in glob.glob(str(prod / "seed_admit/p*.json")):
        for c in json.load(open(f, encoding="utf-8"))["seed_admit"]["columns"]:
            for x in c["chars"]:
                sa[x["id"]] = x
    return gm, ar, sa


def patch_name(cid: str) -> str:
    _b, page, col, slot = cid.split(":")
    m = re.fullmatch(r"(-?\d+)([ab]?)", slot)
    return f"p{int(page):04d}c{int(col):02d}s{m.group(1)}{m.group(2)}.png"


def thumb(path: Path, h: int = 72) -> str:
    from PIL import Image          # 可选依赖
    im = Image.open(path).convert("L")
    w = max(8, round(im.width * h / im.height))
    im = im.resize((min(w, 90), h), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=55)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _key(i: str):
    return tuple(int(x) for x in re.findall(r"\d+", i))


def cmd_sheet(a) -> None:
    from .build import build
    gm, ar, sa = load(Path(a.ws) / "products" / a.book)
    groups: dict[str, list[str]] = collections.defaultdict(list)
    for i, r in gm.items():
        top = (r.get("candidates") or [[None]])[0][0]
        if a.unadmitted:
            if ar.get(i) and not sa.get(i, {}).get("admit"):
                groups[ar[i]].append(i)
        elif top and ar.get(i) == top:
            groups[top].append(i)
    patches = Path(a.ws) / "cache" / a.book / "char_patch"
    items = []
    for ch, ids in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        best = sorted(ids, key=lambda i: -float(gm[i].get("cov") or 0))[:a.per_char]
        for i in sorted(best, key=_key):
            p = patches / patch_name(i)
            if p.exists():
                items.append({"id": i, "pre": ch, "cov": round(float(gm[i].get("cov") or 0), 3),
                              "img": thumb(p), "n": len(ids)})
    st = build("char_grid", items, a.book, a.out, per_page=a.grid)
    print(f"{len(items)} 格（{len(groups)} 字）→ {a.out}（{st['bytes'] / 1e6:.1f} MB，{st['pages']} 页，模板 v{st['tpl_version']}）")


def cmd_pull(a) -> None:
    rows = json.load(open(a.rows, encoding="utf-8"))
    rows = rows.get("docs", rows.get("items", rows)) if isinstance(rows, dict) else rows
    rows = [r.get("data", r) for r in rows]
    book = rows[0]["book"]
    ok, bad, pages = [], [], set()
    for r in sorted(rows, key=lambda r: r["page"]):
        pages.add(r["page"]); ok += r["ok"]; bad += r["bad"]
    json.dump({"book": book, "pages_seen": len(pages), "ok": ok, "bad": bad},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"册{book}: {len(pages)} 页, ok {len(ok)}, bad {len(bad)}")


def cmd_ingest(a) -> None:
    res = json.load(open(a.result, encoding="utf-8"))
    if not os.environ.get("GUJI_WORKSPACE"):
        sys.exit("先设 GUJI_WORKSPACE")
    from guji_manager.feedback.consumers import route_and_consume
    from open_guji_cv.feedback.events import EventLog, EventTarget, make_event
    book = res["book"]
    bad = set(res.get("bad", []))
    log = EventLog()
    base = log.latest_seq(a.batch) + 1
    evs = []
    for k, (cid, ch) in enumerate(x for x in res["ok"] if x[0] not in bad):
        _b, page, col, slot = cid.split(":")
        m = re.fullmatch(r"(-?\d+)([ab]?)", slot)
        evs.append(make_event(a.batch, base + k, "confirm",
                              EventTarget(step="seed_admit", unit="cell", key=cid, book=book,
                                          page=int(page), col=int(col), slot=int(m.group(1))),
                              {"v": "confirm", "shape": ch, "source": "char_review"}))
    print(f"确认 {len(evs)} 格，剔除 {len(bad & {x[0] for x in res['ok']})} 格，不对 {len(bad)} 格")
    if a.dry_run:
        print("dry-run：不写事件、不落库")
        return
    log.append(evs)
    print(json.dumps(route_and_consume(log, batch=a.batch), ensure_ascii=False)[:1500])


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="guji-manager review-pages char", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sheet"); p.add_argument("ws"); p.add_argument("book"); p.add_argument("out")
    p.add_argument("--grid", type=int, default=30); p.add_argument("--per-char", type=int, default=14)
    p.add_argument("--unadmitted", action="store_true", help="只出还没放行、但整理本有对应字的格（第二轮）")
    p = sub.add_parser("pull"); p.add_argument("rows"); p.add_argument("out")
    p = sub.add_parser("ingest"); p.add_argument("result"); p.add_argument("--batch", default="char-review-grid")
    p.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    {"sheet": cmd_sheet, "pull": cmd_pull, "ingest": cmd_ingest}[a.cmd](a)
