"""land 收尾的 book-text 一步（GM4 11-25，用户同意）：包放行的字写回 book-text。

对账待审单（land.py）只管条目；这里补上「包里放行（含 provenance=human 的人裁放行）的字，文本里还是 □／不同」：
  1. 导出：本包 ``output/guji_format_export --format char-cord``（参数同 cv ``republish.py from-pack``；本机现成产物，只读）→ ``reports/<册>/_land/export/<章>.char/cord.json``；
  2. 计划（只读）：与 book-text origin/dev 的 ``<章>.char.json`` 逐格走 ``swap/booktext.merge_chars``（同包同切分，对照表＝格号自对自），
     规则同 swap：人裁最高、新结果覆盖旧、待审格只录首选字、归一同字不算冲突；写 ``reports/<册>/_land/text-plan.tsv``；
  3. 落（``--text-apply``）：只有计划里有字要改的册才走 ``swap/booktext.do_book``（独立 worktree、bump、local_check、推 dev；
     1.x 册按 swap 现行规矩开 PR）。无变化的册不碰 book-text，不产生空提交。
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

from .review import pending_items as P

EXPORT_TIMEOUT = 900


def export_dir(ws: Path, book: str) -> Path:
    return ws / "reports" / book / "_land" / "export"


def export_meta(book: str, out_dir: Path) -> Path | None:
    """导出用的 meta（同 cv ``republish.py`` 的 ``meta_file``）：cv 仓有 ``meta_<册>.json`` 就用；殿本 volNN 按固定模板现生成；
    非殿本按册配置（book_id、volume 必有，书名／版本取 book_title／book_edition）现生成到 out_dir。都不成给 None。"""
    import re
    from ._cv import cv_repo
    try:
        f = cv_repo() / "doc/formats/samples/guji_format_v0.1" / f"meta_{book}.json"
    except Exception:  # noqa: BLE001 —— cv 不是检出安装：照下面现生成
        f = None
    if f is not None and f.exists():
        return f
    m = re.fullmatch(r"vol(\d+)", book)
    if m:
        n = int(m.group(1))
        meta = {"defaults": {"book": {"id": "96mid1ogzk", "edition": "siku-zongmu", "title": "欽定四庫全書總目（武英殿刻本）"},
                             "volume": {"index": n, "cv_book": book},
                             "snapshot": f"guji-workspace 96mid1ogzk-欽定四庫全書總目武英殿刻本 本地产物（{book}）"}}
    else:
        from ._cv import volume_of
        v = volume_of(book)
        if not (v.book_id and v.volume):
            return None
        d = _book_dict(book)
        bk = {"id": v.book_id, "title": d.get("book_title") or d.get("title") or book}
        if d.get("book_edition"):
            bk["edition"] = d["book_edition"]
        meta = {"defaults": {"book": bk, "volume": {"index": v.volume, "cv_book": book},
                             "snapshot": f"{v.book_id} 本地产物（{book}）"}}
    out_dir.mkdir(parents=True, exist_ok=True)
    g = out_dir / f"meta_{book}.json"
    g.write_text(json.dumps(meta, ensure_ascii=False) + "\n", encoding="utf-8")
    return g


def _book_dict(book: str) -> dict:
    """生效的册配置（册 yaml ∪ 基础配置），读不到给空。"""
    try:
        from ._cv import book_config_effective, book_yaml_path
        return book_config_effective(book_yaml_path(book), apply_override=False)
    except Exception:  # noqa: BLE001
        return {}


def dev_text_version(book_text: Path, text_id: str, chapter: str) -> str:
    """book-text origin/dev 上这一章的现行文本版本（index.json chapters[].text_version）；没有就停。"""
    from .swap import booktext as B
    src = Path(book_text).resolve()
    rel = B._bt_dir(src, text_id).relative_to(src).as_posix() + "/default"
    idx = _show_dev(src, f"{rel}/index.json") or {}
    for c in idx.get("chapters", []):
        if str(c.get("file")) == chapter or f"{c.get('n', 0):03d}" == chapter or str(c.get("file", "")).startswith(chapter + "."):
            if c.get("text_version"):
                return c["text_version"]
    if idx.get("text_version"):
        return idx["text_version"]
    raise SystemExit(f"✗ book-text dev {rel}/index.json 里 {chapter} 没有 text_version：不导出、不写 book-text")


def _products(ws: Path) -> Path:
    env = os.environ.get("GUJI_PRODUCTS_DIR")
    return Path(env).expanduser() if env else ws / "products"


def export_cmd(ws: Path, book: str, *, chapter: str, out: Path, text_version: str, meta: Path,
               prev_char: Path | None = None) -> list[str]:
    """导出命令，参数同 cv ``republish.py from-pack``：本包导出器、char-cord、cv 格位口径、现行文本版本、meta、四庫拆页表。

    不走 ``guji export format <册> …``：cv ≥0.9.7 的 ``guji export`` 把册号后面全当 REMAINDER，-w／--out／--chapter 吃不到；
    那条命令也缺省只出 pages 格式、不出 char.json（MJ 11-27）。"""
    cmd = [sys.executable, "-m", "guji_manager.output.guji_format_export", "--products", str(_products(ws)), "--book", book,
           "--chapter", chapter, "--out", str(out), "--format", "char-cord", "--keys", "cv", "--text-version", text_version,
           "--meta", str(meta)]
    try:
        from ._cv import cv_repo
        split = cv_repo() / "doc/formats/samples/guji_page_v0.2/split_table_siku.json"
    except Exception:  # noqa: BLE001
        split = None
    if split is not None and split.exists():
        cmd += ["--split-table", str(split)]
    if prev_char is not None:
        cmd += ["--prev-char", str(prev_char)]
    return cmd


def refresh_export(ws: Path, book: str, *, chapter: str, book_text: Path, text_id: str) -> Path:
    """本机产物 → 导出目录（每次现导，保证是当前 ★main 包）。出不来抛 SystemExit（别拿旧导出写文本）。

    文本版本与「保 u 连续」用的现行 char 都取 book-text origin/dev（后面计划、落文本也是对 dev）。"""
    from .swap import booktext as B
    out = export_dir(ws, book)
    if out.exists():                                   # 旧导出不留：导出失败时别让旧 char.json 混过检查
        import shutil
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    side = out.parent / "export-input"
    side.mkdir(parents=True, exist_ok=True)
    meta = export_meta(book, side)
    if meta is None:
        raise SystemExit(f"✗ {book} 没有导出用的 meta：cv 无 meta_{book}.json，册配置也缺 book_id／volume；不写 book-text")
    src = Path(book_text).resolve()
    B._git(src, "fetch", "-q", "origin", B.DEV_REFSPEC)
    tv = dev_text_version(src, text_id, chapter)
    rel = B._bt_dir(src, text_id).relative_to(src).as_posix() + "/default"
    prev = _show_dev(src, f"{rel}/{chapter}.char.json")
    prev_f = None
    if prev:
        prev_f = side / f"{chapter}.char.json"
        prev_f.write_text(json.dumps(prev, ensure_ascii=False), encoding="utf-8")
    cmd = export_cmd(ws, book, chapter=chapter, out=out, text_version=tv, meta=meta, prev_char=prev_f)
    print("→ " + " ".join(cmd), file=sys.stderr)
    r = subprocess.run(cmd, env={**os.environ, "GUJI_WORKSPACE": str(ws), "PYTHONIOENCODING": "utf-8"}, timeout=EXPORT_TIMEOUT)
    if r.returncode or not (out / f"{chapter}.char.json").exists():
        why = f"退出 {r.returncode}" if r.returncode else f"退出 0 但没出 {chapter}.char.json"
        raise SystemExit(f"✗ {book} 导出失败（{why}）：不写 book-text")
    return out


def _show_dev(src: Path, rel: str) -> dict | None:
    from .swap.booktext import _show
    return _show(src, "refs/remotes/origin/dev", rel)


def open_pending(store: P.ItemStore) -> dict[str, dict]:
    """条目 → ``fill_pending_blanks`` 要的 {格号: 带首选字信息的 doc}。"""
    return {r["cell"]: {**(r.get("doc") or {}), "cell": r["cell"], "src": r.get("src")} for r in store.items.values() if r["state"] == "open"}


def text_plan(ws: Path, book: str, *, text_id: str, book_text: Path, pending: dict[str, dict], export: Path, human: dict | None = None) -> dict:
    """只读计划：返回 {changes:[(格,现行字,包字,落字,类别)], counts, table}；不写 book-text。"""
    from .swap import booktext as B
    ch = B._chapter(book)
    src = Path(book_text).resolve()
    B._git(src, "fetch", "-q", "origin", B.DEV_REFSPEC)
    rel = B._bt_dir(src, text_id).relative_to(src).as_posix() + "/default"
    old = _show_dev(src, f"{rel}/{ch}.char.json")
    new = B._load(export / f"{ch}.char.json")
    if not old or not new:
        return {"status": "blocked", "why": f"book-text dev 或导出里没有 {ch}.char.json"}
    rows = [{"old": a, "new": a} for a, _ in B._chars(new)]
    new_c = copy.deepcopy(new)
    hum = human if human is not None else (B.load_human(book) or {})
    from .charnorm import codepoints_of, load_norm
    from .datastore.workcopy import data_dir
    try:
        extra = codepoints_of(data_dir(ws), book)          # 同 remap_in_repo：直接读数据目录的码位表，别退成字面比
    except SystemExit:
        extra = {}
    same = load_norm(book, extra).same
    edits = (_show_dev(src, f"{rel}/{ch}.char-edits.json") or {}).get("edits") or []
    prot_old, _pre = B.protected_cells(old, hum, edits, same)
    chars = B.merge_chars(old, new_c, rows, set(pending), prot_old, same)
    filled = B.fill_pending_blanks(new_c, pending, prot_old)
    if filled:
        chars["pending_first_choice"] = filled
    changes = []
    for kind, lst in chars.items():
        if kind == "dup_new":
            continue
        for a, cur, nw, out in lst:
            if out != cur:
                changes.append((a, cur, nw, out, kind))
    changes.sort(key=lambda x: [int(t) if t.isdigit() else t for t in B.re.split(r"(\d+)", x[0]) if t])
    f = ws / "reports" / book / "_land" / "text-plan.tsv"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("格\t现行字\t包字\t落字\t类别\n" + "".join("\t".join("" if v is None else str(v) for v in c) + "\n" for c in changes), encoding="utf-8")
    counts: dict[str, int] = {}
    for c in changes:
        counts[c[4]] = counts.get(c[4], 0) + 1
    return {"status": "planned", "changes": changes, "counts": counts, "table": str(f), "n": len(changes),
            "conflicts": [(a, nw, out) for a, _c, nw, out in chars.get("protected_conflict") or []]}


def text_apply(ws: Path, book: str, *, text_id: str, book_text: Path, pending: dict[str, dict], export: Path, note: str) -> dict:
    """落文本：独立 worktree 里走 swap 的 ``do_book``（人裁最高、bump、local_check、推 dev；1.x 册开 PR）。"""
    from .swap import booktext as B
    src = Path(book_text).resolve()
    sp = (B._bt_dir(Path("."), text_id).as_posix().lstrip("./"),)
    wt = B._worktree(src, Path(str(src) + "-swap").resolve(), sparse=sp)
    out_dir = ws / "reports" / "_swap" / "book-text" / book
    r = B.do_book(wt, ws, book, text_id, export, note=note, push=True, pending=pending, out_dir=out_dir)
    return {k: v for k, v in r.items() if k not in ("char_detail", "left", "review")}
