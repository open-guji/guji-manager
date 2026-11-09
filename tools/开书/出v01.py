#!/usr/bin/env python3
"""一册出 v0.1：判停 → 收口单 → 导出＋出待审单 → book-text 加章 → 校验，一条命令串起来。

全唐文 004（2026-11-08）手工走 S4 收口＋S14 入库时，要串 6～7 个脚本、手改 book-text 三个文件；
本脚本把能机器做的都做了，只在两处停下：
  1. 判停：待审格里有「算法再处理」类（切分对位、切分缺陷、列宽出带……）就停，列出格号、按页归并，
     不往下导出——这正是 S4「还有算法再处理就不出 v0.1」。
  2. 推东西（中心库、R2、book-text 远端、网站）一律不做，末尾打印要跑的命令。

用法（cv 的 venv；PYTHONPATH 带 guji-manager；沙箱产物根）：
  GUJI_PRODUCTS_DIR=<沙箱> python tools/开书/出v01.py -w <工作区> --book 004 --label <main 包标签> \
      --book-text <book-text 检出> --title 卷三至卷六 [--gate-only] [--force]

产出 <工作区>/reports/<册>/_v01/：cells.tsv、summary.json、交接单.md（剩余格默认全「留人审」，
Sheldon 11-05 定收口单只有 放行／留人审／算法再处理 三去向，机器没把握的格预选留人审）。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

# 这些原因是切分／版面的毛病，算法能修（改册配置、格位表、换 cv），出 v0.1 前要再跑一轮
ALGO = {"seg_defect", "seg_col_unaligned", "seg_page_unaligned", "col_width_out_of_band", "machine_changed"}


def cv_root() -> Path:
    import open_guji_cv
    return Path(open_guji_cv.__file__).resolve().parents[1]


def lib_count_fn(ws: Path, text_id: str):
    """本书刻例数：优先中心库导出的 glyph_store/exemplars.jsonl（不含借库），没有再读 glyph.db。"""
    home = Path(os.environ.get("GUJI_DATA_HOME", Path.home() / ".guji-data"))
    ex = home / os.environ.get("GUJI_DATA_BRANCH", "main") / text_id / "output/glyph_store/exemplars.jsonl"
    if ex.exists():
        n = Counter(json.loads(l)["char"] for l in ex.open(encoding="utf-8") if l.strip())
        return (lambda ch: n.get(ch, 0)), ex
    db = ws / "output/glyph.db"
    return None, (db if db.exists() else None)


def gate(products: Path, book: str, ws: Path, text_id: str, out: Path) -> dict:
    from guji_manager.review import reasons as RS
    from guji_manager.review.pending_reason import specs
    fn, src = lib_count_fn(ws, text_id)
    if fn is not None:
        RS.lib_counts = lambda _p: fn
    sp = specs()
    cells = RS.book_cells(products, book)
    doc = {"cells": [{"cell": f"{book}:{k}", "why": c.doubts} for k, c in cells.items()]}
    res = RS.reasons_for_pending(doc, products, book, glyph_db=src)
    rows = []
    for cell, (r, d) in sorted(res.items(), key=lambda kv: [int(x) if x.isdigit() else 0 for x in kv[0].split(":")]):
        s = sp.get(r) or sp.get(r.value) or {}
        g = (lambda k: s.get(k) if isinstance(s, dict) else getattr(s, k, None))
        c = cells.get(cell.split(":", 1)[1]) or cells.get(cell)
        rows.append({"cell": cell, "reason": r.value, "category": str(g("category") or ""),
                     "owner": str(g("owner") or ""), "detail": d or "",
                     "char": (c.char or "") if c else "", "ref": (c.ref or "") if c else "",
                     "fate": "算法再处理" if r.value in ALGO else "留人审"})
    out.mkdir(parents=True, exist_ok=True)
    with (out / "cells.tsv").open("w", encoding="utf-8") as f:
        f.write("cell\tpending_reason\tcategory\towner\tdetail\tchar\tref\t去向\n")
        for x in rows:
            f.write("\t".join([x["cell"], x["reason"], x["category"], x["owner"], x["detail"], x["char"], x["ref"], x["fate"]]) + "\n")
    algo = [x for x in rows if x["fate"] == "算法再处理"]
    by_page = defaultdict(list)
    for x in algo:
        by_page[int(x["cell"].split(":")[1])].append(x)
    summ = {"book": book, "n": len(rows), "by_reason": dict(Counter(x["reason"] for x in rows).most_common()),
            "algo": len(algo), "algo_pages": {p: [f'{x["cell"]} {x["reason"]} {x["char"]}' for x in v] for p, v in sorted(by_page.items())},
            "lib_counts_from": str(src) if src else None}
    (out / "summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"rows": rows, "summary": summ}


def handoff(out: Path, book: str, label: str, rows: list, man: dict) -> None:
    by = Counter(x["reason"] for x in rows)
    L = [f"# 第 {book} 册 v0.1 交接单（{date.today()}，出v01.py 生成）", "",
         f"- 底：产物包 `{label}`（cv {man.get('cv_version') or '?'}），须已标 main。",
         f"- 待审 {len(rows)} 格；收口去向：全部**留人审**（放行 0、算法再处理 0），交精校。",
         "- 逐格：同目录 `cells.tsv`。", "", "| pending_reason | 格数 |", "|---|---|"]
    L += [f"| {k} | {n} |" for k, n in by.most_common()]
    left = [x for x in rows if x["fate"].startswith("留人审（")]
    if left:
        L += ["", "## 切分残留（人定不再重跑，留人审）", "", "| 格 | 原因 | 机器字 |", "|---|---|---|"]
        L += [f'| {x["cell"]} | {x["reason"]} {x["detail"]} | {x["char"]} |' for x in left]
    hp = [x for x in rows if x["reason"] == "hard_pair"]
    if hp:
        L += ["", "## 极难字（hard_pair，要看文意）", "", "| 格 | 机器字 |", "|---|---|"]
        L += [f'| {x["cell"]} | {x["char"]} |' for x in hp]
    (out / "交接单.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def bt_dir(bt: Path, text_id: str) -> Path:
    return bt / "Book" / text_id[-3] / text_id[-2] / text_id[-1] / text_id


def bt_add_chapter(bt: Path, text_id: str, chapter: str, export: Path, title: str, note: str) -> None:
    """book-text 条目加一章（已有同章则换文本、版本不动由调用方定）：拷文件、改 index／manifest 章数、记 CHANGES。"""
    d = bt_dir(bt, text_id)
    dd = d / "default"
    for kind in ("char", "cord", "norm"):
        src = export / f"{chapter}.{kind}.json"
        if not src.exists():
            sys.exit(f"✗ 导出里没有 {src.name}")
        shutil.copyfile(src, dd / src.name)
    cord = json.loads((export / f"{chapter}.cord.json").read_text(encoding="utf-8"))
    pages = sorted({int(p.get("page", 0)) for p in cord.get("pages", []) if isinstance(p, dict) and p.get("page")})
    char = json.loads((export / f"{chapter}.char.json").read_text(encoding="utf-8"))
    tv = char.get("version") or "0.1.0"
    idx_p = dd / "index.json"
    idx = json.loads(idx_p.read_text(encoding="utf-8"))
    ent = {"n": int(chapter), "file": chapter, "title": title, "char_file": f"{chapter}.char.json",
           "cord_file": f"{chapter}.cord.json", "norm_file": f"{chapter}.norm.json",
           "pages": f"{pages[0]}-{pages[-1]}" if pages else "", "text_version": tv, "proofing": True}
    chs = [c for c in idx["chapters"] if c.get("file") != chapter] + [ent]
    idx["chapters"] = sorted(chs, key=lambda c: int(c["n"]))
    idx["total_chapters"] = len(idx["chapters"])
    idx_p.write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    man_p = d / "manifest.json"
    man = json.loads(man_p.read_text(encoding="utf-8"))
    for v in man.get("versions", []):
        if v.get("key") == "default":
            v["chapters_total"] = len(idx["chapters"])    # E14-2：写已入库章数，不写全书册数
    man_p.write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ch_p = dd / "CHANGES.md"
    with ch_p.open("a", encoding="utf-8") as f:
        f.write(f"| {date.today()} | {chapter} | 文本 | —→{tv} | {note} | — |\n")
    print(f"book-text：{d} 加章 {chapter}（{ent['pages']}，text_version {tv}），总章数 {len(idx['chapters'])}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-w", "--workspace", required=True)
    ap.add_argument("--book", required=True)
    ap.add_argument("--label", required=True, help="main 包标签（guji products pack list <册>）")
    ap.add_argument("--book-text")
    ap.add_argument("--title", help="章题，如「卷三至卷六」")
    ap.add_argument("--gate-only", action="store_true", help="只判停、出收口清单")
    ap.add_argument("--force", action="store_true", help="有算法再处理也往下走（只在人定放行时用）")
    ap.add_argument("--promote", metavar="WHY", help="顺手把包标 main（写令牌），WHY 是 dev cv 包进 main 的理由")
    ap.add_argument("--no-fetch", action="store_true", help="沙箱里已有该包，不重取")
    a = ap.parse_args()
    ws, book = Path(a.workspace).resolve(), a.book
    if not os.environ.get("GUJI_PRODUCTS_DIR"):
        sys.exit("✗ 先设沙箱 GUJI_PRODUCTS_DIR（取包会整册覆盖 <产物根>/<册>）")
    products = Path(os.environ["GUJI_PRODUCTS_DIR"])
    import yaml
    text_id = str(yaml.safe_load((ws / "workspace.yaml").read_text(encoding="utf-8")).get("id"))
    py, cv = sys.executable, cv_root()
    env = {**os.environ, "GUJI_WORKSPACE": str(ws), "PYTHONIOENCODING": "utf-8"}
    if not a.no_fetch:
        if (products / book).exists():
            shutil.rmtree(products / book)
        subprocess.run([py, "-m", "open_guji_cv.cli_v2", "products", "pack", "fetch", book, "--label", a.label,
                        "--to", str(products), "-w", str(ws)], check=True, env=env)
    out = ws / "reports" / book / "_v01"
    g = gate(products, book, ws, text_id, out)
    s = g["summary"]
    print(f"待审 {s['n']} 格：{s['by_reason']}")
    if s["algo"]:
        print(f"✗ 算法再处理 {s['algo']} 格（{len(s['algo_pages'])} 页），不出 v0.1：")
        for p, v in s["algo_pages"].items():
            print(f"  p{p}: " + "；".join(v))
        print(f"  清单 {out}/cells.tsv；按页画框看图（tools/开书/全唐文/draw_page.py），改册配置／格位表后重跑")
        if not a.force:
            return 2
        for x in g["rows"]:              # 人看过、定为修不了也不值得再跑的（如空页墨点）：转留人审，交接单单列
            if x["fate"] == "算法再处理":
                x["fate"] = "留人审（切分残留，--force）"
    if a.gate_only:
        return 0
    if not (a.book_text and a.title):
        sys.exit("✗ 往下走要 --book-text 和 --title")
    import re
    m = re.match(r"cv(.+?)(?:pg([0-9a-f]+))?-c", a.label)          # 包标签：cv<版本>[pg<commit>]-c<语料>-g-…
    man = {"cv_version": (m.group(1) if m else None)}
    if a.promote:                     # 标 main（开书授权内）；dev cv 出的包 main 要 --why
        subprocess.run([py, "-m", "open_guji_cv.cli_v2", "products", "pack", "promote", book, "-w", str(ws),
                        "--label", a.label, "--note", f"{book} v0.1：待审 {s['n']}，收口全留人审",
                        "--why", a.promote], check=True, env={**env, "GUJI_AUTO_ONLINE_LISTS": "0"})
    handoff(out, book, a.label, g["rows"], man)
    bt = Path(a.book_text).resolve()
    chapter = book
    online = bt_dir(bt, text_id) / "default" / f"{chapter}.char.json"
    tv = json.loads(online.read_text(encoding="utf-8")).get("version") if online.exists() else "0.1.0"
    # 字块图要原图：没有就取；prep 按 data_full/*/<册> 找图，图在 data_full/<册> 的书（全唐文）补一层链接（E14-5）
    if not (ws / "data_full" / book).is_dir():
        subprocess.run([py, "-m", "open_guji_cv.cli_v2", "source", "pull", book, "-w", str(ws)], env=env)
    if (ws / "data_full" / book).is_dir() and not list((ws / "data_full").glob(f"*/{book}")):
        (ws / "data_full" / "_vol").mkdir(exist_ok=True)
        (ws / "data_full" / "_vol" / book).symlink_to(Path("..") / book)
    rc = subprocess.run([py, str(cv / "scripts/zhengli/republish.py"), "from-pack", "--book", book, "-w", str(ws),
                         "--label", a.label, "--text-version", tv, "--no-alt", "--no-pull"], env=env, cwd=cv).returncode
    if rc:
        return rc
    export = ws / "reports" / book / "_publish" / f"export-{a.label}"
    note = (f"粗校 v0.1：产物包 {a.label}（cv {man.get('cv_version') or '?'}），待审 {s['n']} 格（收口全留人审），"
            f"proofing: true")
    bt_add_chapter(bt, text_id, chapter, export, a.title, note)
    subprocess.run([py, "scripts/local_check.py", "--dev"], cwd=bt)
    pub = sorted((ws / "reports" / book / "_publish").glob(f"{chapter}-r*"))
    rev = pub[-1].name if pub else "<rev>"
    print("\n接下来（推东西，人或总览线做）：")
    print(f"  1. 看差异单 {ws}/reports/{book}/_publish/{rev}/差异单.md")
    print(f"  2. book-text：git add Book/…/{text_id} && git commit && git pull --rebase origin dev && git push origin HEAD:dev")
    print(f"  3. guji source pull {book} -w {ws}（出字块图要原图；图在 data_full/{book} 时建 data_full/_vol/{book} 链接）")
    print(f"  4. python {cv}/scripts/zhengli/republish.py push --book {book} -w {ws} --rev {rev} --yes --no-publish-web")
    print(f"  5. guji db pull → guji db push --dry-run（看 0 成批 delete、glyph_exported false）→ guji db push")
    print(f"  6. 网站：pages-books.json 加 {book}（3 位册号）、触发 iiif（vols={book}）与 proofing-sync（only={text_id}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
