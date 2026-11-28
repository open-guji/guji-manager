#!/usr/bin/env python3
"""一册出 v0.1：判停 → 收口单 → 导出 → book-text 加章 → 校验，一条命令串起来。

全唐文 004（2026-11-08）手工走 S4 收口＋S14 入库时，要串 6～7 个脚本、手改 book-text 三个文件；
本脚本把能机器做的都做了（含第五步产物 `guji output export md`＋`guji pipeline collate`，原 Step9，close-check 第 12 项要），只在两处停下：
  1. 判停：待审格里有「算法再处理」类（切分对位、切分缺陷、列宽出带……）就停，列出格号、按页归并，
     不往下导出——这正是 S4「还有算法再处理就不出 v0.1」。
  2. 推东西（中心库、R2、book-text 远端、网站）一律不做，末尾打印要跑的命令。

用法（cv 的 venv；PYTHONPATH 带 guji-manager；沙箱产物根）：
  GUJI_PRODUCTS_DIR=<沙箱> python guji launch prepare（本模块） -w <工作区> --book 004 --label <main 包标签> \
      --book-text <book-text 检出> --title 卷三至卷六 [--gate-only] [--force]

产出 <工作区>/reports/<册>/_v01/：cells.tsv、summary.json、交接单.md（剩余格默认全「留人审」，
Sheldon 11-05 定收口单只有 放行／留人审／算法再处理 三去向，机器没把握的格预选留人审）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

# 这些原因是切分／版面的毛病，算法能修（改册配置、格位表、换 cv），出 v0.1 前要再跑一轮
ALGO = {"seg_defect", "seg_col_unaligned", "seg_page_unaligned", "col_width_out_of_band", "machine_changed"}


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


def chapter_for(book: str, ws: Path, given: str | None = None) -> str:
    """册号 → book-text 章号（三位）。先认 --chapter，再按 cv 册配置（``core.volume_id.chapter_of``，与 guji land 同法），
    再退到册号里的数字补三位（史記册号 01 → 001；SJ 11-19：原来直接用册号当章号，落成 01.char.json）。"""
    import re
    if given:
        if not re.fullmatch(r"\d+", given):
            sys.exit(f"✗ --chapter 要是数字：{given}")
        return f"{int(given):03d}"
    try:
        os.environ.setdefault("GUJI_WORKSPACE", str(ws))
        from open_guji_cv.core.volume_id import chapter_of
        ch = chapter_of(book)
        if ch:
            return f"{int(ch):03d}" if str(ch).isdigit() else str(ch)
    except Exception:  # noqa: BLE001  cv 太旧或册配置读不到，退到册号数字
        pass
    m = re.fullmatch(r"\D*(\d+)", book)
    if not m:
        sys.exit(f"✗ {book} 推不出章号：给 --chapter NNN")
    return f"{int(m[1]):03d}"


def bt_dir(bt: Path, text_id: str) -> Path:
    return bt / "Book" / text_id[-3] / text_id[-2] / text_id[-1] / text_id


def _cn_num(s: str) -> int | None:
    """「三十一」「百一」「二十」「7」→ 整数（1–999）；认不出返回 None"""
    if s.isdigit():
        return int(s)
    D = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    tot = cur = 0
    for ch in s:
        if ch == "百":
            tot, cur = tot + (cur or 1) * 100, 0
        elif ch == "十":
            tot, cur = tot + (cur or 1) * 10, 0
        elif ch in D:
            cur = D[ch]
        else:
            return None
    return tot + cur or None


def parse_juan(spec: str | None, title: str) -> list[int] | None:
    """册含的原书卷号 [起, 止]：优先 --juan「3-6」；没给就从章题「卷三至卷六」「总目三、卷一至卷二」里取；取不到（序、总目）返回 None 不写。
    index.json 的章条目 ``juan`` 是对校（book-text-util）按册取对照本卷的固定字段，不再让它解析章题。"""
    if spec:
        a, _, b = spec.partition("-")
        lo, hi = int(a), int(b or a)
    else:
        m = re.search(r"卷([\d〇零一二三四五六七八九十百]+)(?:\s*[至到—–-]\s*卷?([\d〇零一二三四五六七八九十百]+))?", title)
        if not m:
            return None
        lo, hi = _cn_num(m[1]), _cn_num(m[2] or m[1])
        if lo is None or hi is None:
            return None
    if not (1 <= lo <= hi):
        sys.exit(f"✗ 卷号 {lo}-{hi} 不合法")
    return [lo, hi]


def bt_add_chapter(bt: Path, text_id: str, chapter: str, export: Path, title: str, note: str, juan: list[int] | None = None) -> None:
    """book-text 条目加一章（已有同章则换文本、版本不动由调用方定）：拷文件（有 NNN.gaps.json 一并拷、写 gaps_file）、改 index／manifest 章数；版本记录打印出来，调用方写进提交信息（book-text 不再有 CHANGES.md）。"""
    d = bt_dir(bt, text_id)
    dd = d / "default"
    for kind in ("char", "cord", "norm"):
        src = export / f"{chapter}.{kind}.json"
        if not src.exists():
            sys.exit(f"✗ 导出里没有 {src.name}")
        shutil.copyfile(src, dd / src.name)
    gaps = export / f"{chapter}.gaps.json"          # 缺页旁挂（guji-gaps/0.1，导出时册 yaml 有落在本章的 gaps 才有）
    if gaps.exists():
        shutil.copyfile(gaps, dd / gaps.name)
    else:
        (dd / gaps.name).unlink(missing_ok=True)    # 重出时缺页已撤：删掉旧文件，条目也不写 gaps_file
    cord = json.loads((export / f"{chapter}.cord.json").read_text(encoding="utf-8"))
    pages = sorted({int(p.get("page", 0)) for p in cord.get("pages", []) if isinstance(p, dict) and p.get("page")})
    char = json.loads((export / f"{chapter}.char.json").read_text(encoding="utf-8"))
    tv = char.get("version") or "0.1.0"
    idx_p = dd / "index.json"
    idx = json.loads(idx_p.read_text(encoding="utf-8"))
    ent = {"n": int(chapter), "file": chapter, "title": title, "char_file": f"{chapter}.char.json",
           "cord_file": f"{chapter}.cord.json", "norm_file": f"{chapter}.norm.json",
           "pages": f"{pages[0]}-{pages[-1]}" if pages else "", "text_version": tv, "proofing": True}
    if gaps.exists():
        ent["gaps_file"] = gaps.name                 # 网站／阅读包按它读缺页（Web 11-23 要），与 cord_file 同级
    if juan:
        ent["juan"] = juan
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
    print(f"版本记录: {text_id}/{chapter} | 文本 | →{tv} | {note}")
    print(f"book-text：{d} 加章 {chapter}（{ent['pages']}，text_version {tv}），总章数 {len(idx['chapters'])}")


def step9(py: str, book: str, ws: Path, env: dict) -> None:
    """第五步产物（原 Step9；close-check 第 12 项，R5 要它）：从刚取的 main 包本地出 reports/<册>/<册>.md 与对勘 html。

    任务库包里不带这些产物（它跨页、不进 products/），出 0.1.0 前在取包这台机器上补（A31 11-16 定口径）。
    只读产物；对勘证人读书配置 `references:`。失败不拦导出，末尾 close-check 会报第 12 项。"""
    for cmd in (["export", "md", book], ["collate", book, "--console", ""]):
        rc = subprocess.run([py, "-m", "open_guji_cv.cli_v2", *cmd, "-w", str(ws)], env=env).returncode
        if rc:
            print(f"⚠ 第五步产物 `guji {' '.join(cmd)}` 退出码 {rc}：close-check 第 12 项会挂，修好后单跑这条补上")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-w", "--workspace", required=True)
    ap.add_argument("--book", required=True)
    ap.add_argument("--label", required=True, help="main 包标签（guji products pack list <册>）")
    ap.add_argument("--book-text")
    ap.add_argument("--title", help="章题，如「卷三至卷六」")
    ap.add_argument("--juan", help="本册含的原书卷号「3-6」，写进章条目 juan（对校按它取对照本的卷）；不给就从 --title 取")
    ap.add_argument("--gate-only", action="store_true", help="只判停、出收口清单")
    ap.add_argument("--force", action="store_true", help="有算法再处理也往下走（只在人定放行时用）")
    ap.add_argument("--promote", metavar="WHY", help="顺手把包标 main（写令牌），WHY 是 dev cv 包进 main 的理由")
    ap.add_argument("--chapter", help="book-text 章号（三位，如 001）；不给按册配置 volume 推，推不出时取册号数字补成三位")
    ap.add_argument("--no-fetch", action="store_true", help="沙箱里已有该包，不重取")
    a = ap.parse_args(argv)
    ws, book = Path(a.workspace).resolve(), a.book
    if not os.environ.get("GUJI_PRODUCTS_DIR"):
        sys.exit("✗ 先设沙箱 GUJI_PRODUCTS_DIR（取包会整册覆盖 <产物根>/<册>）")
    products = Path(os.environ["GUJI_PRODUCTS_DIR"])
    import yaml
    text_id = str(yaml.safe_load((ws / "workspace.yaml").read_text(encoding="utf-8")).get("id") or "")
    if not text_id or text_id == "None":
        sys.exit(f"✗ {ws}/workspace.yaml 没有 id（book-text 条目 id），出不了 v0.1")
    py = sys.executable
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
    step9(py, book, ws, env)
    import re
    m = re.match(r"cv(.+?)(?:pg([0-9a-f]+))?-c", a.label)          # 包标签：cv<版本>[pg<commit>]-c<语料>-g-…
    man = {"cv_version": (m.group(1) if m else None)}
    if a.promote:                     # 标 main（开书授权内）；dev cv 出的包 main 要 --why
        subprocess.run([py, "-m", "open_guji_cv.cli_v2", "products", "pack", "promote", book, "-w", str(ws),
                        "--label", a.label, "--note", f"{book} v0.1：待审 {s['n']}，收口全留人审",
                        "--why", a.promote], check=True, env={**env, "GUJI_AUTO_ONLINE_LISTS": "0"})
    handoff(out, book, a.label, g["rows"], man)
    bt = Path(a.book_text).resolve()
    chapter = chapter_for(book, ws, a.chapter)
    online = bt_dir(bt, text_id) / "default" / f"{chapter}.char.json"
    tv = json.loads(online.read_text(encoding="utf-8")).get("version") if online.exists() else "0.1.0"
    # 字块图要原图：没有就取；prep 按 data_full/*/<册> 找图，图在 data_full/<册> 的书（全唐文）补一层链接（E14-5）
    if not (ws / "data_full" / book).is_dir():
        subprocess.run([py, "-m", "open_guji_cv.cli_v2", "source", "pull", book, "-w", str(ws)], env=env)
    if (ws / "data_full" / book).is_dir() and not list((ws / "data_full").glob(f"*/{book}")):
        (ws / "data_full" / "_vol").mkdir(exist_ok=True)
        (ws / "data_full" / "_vol" / book).symlink_to(Path("..") / book)
    # 导出（原 cv republish.py from-pack，cv #1974 已删）：参数同 guji land 收尾的导出（land_text.export_cmd）。
    # 首发时 book-text dev 上还没有这一章，所以文本版本取本机检出、不带 --prev-char，不走 land_text.refresh_export。
    from guji_manager import land_text as LT
    export = LT.export_dir(ws, book)
    if export.exists():
        shutil.rmtree(export)
    export.mkdir(parents=True, exist_ok=True)
    meta = LT.export_meta(book, export.parent / "export-input")
    if meta is None:
        sys.exit(f"✗ {book} 没有导出用的 meta：cv 无 meta_{book}.json，册配置也缺 book_id／volume")
    rc = subprocess.run(LT.export_cmd(ws, book, chapter=chapter, out=export, text_version=tv, meta=meta),
                        env={**env, "GUJI_PRODUCTS_DIR": str(products)}).returncode
    if rc or not (export / f"{chapter}.char.json").exists():
        print(f"✗ 导出失败（退出 {rc}），不写 book-text")
        return rc or 1
    note = (f"粗校 v0.1：产物包 {a.label}（cv {man.get('cv_version') or '?'}），待审 {s['n']} 格（收口全留人审），"
            f"proofing: true")
    bt_add_chapter(bt, text_id, chapter, export, a.title, note, parse_juan(a.juan, a.title))
    subprocess.run([py, "scripts/local_check.py", "--dev"], cwd=bt)
    vdir = bt_dir(bt, text_id) / "default"
    print("\n接下来（推东西，人或总览线做）：")
    print(f"  0. 出口检查（R5）：guji close-check {book} --tier rough -w {ws}（第五步产物上面已出在 reports/{book}/）")
    print(f"  1. book-text：git add Book/…/{text_id} && git commit && git pull --rebase origin dev && git push origin HEAD:dev")
    print(f"  2. guji source pull {book} -w {ws}（出单格图要原图；图在 data_full/{book} 时建 data_full/_vol/{book} 链接）")
    print(f"  3. 出待审单（原 republish.py push，已退役）：先看计划 guji land {book} -w {ws} --text-id {text_id} "
          f"--export-char {export}/{chapter}.char.json --text-vdir {vdir}；计数合理再加 --apply"
          "（开条目、传单格图、推条目与线上单、发站；首发上线要先问用户，不想发站加 --no-publish）")
    print("  4. guji db pull → guji db push --dry-run（看 0 成批 delete、glyph_exported false）→ guji db push")
    print(f"  5. 网站：pages-books.json 加 {book}（3 位册号）、触发 iiif（vols={book}）与 proofing-sync（only={text_id}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
