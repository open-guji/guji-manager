"""land 收尾的 book-text 一步（GM4 11-25，用户同意）：包放行的字写回 book-text。

对账待审单（land.py）只管条目；这里补上「包里放行（含 provenance=human 的人裁放行）的字，文本里还是 □／不同」：
  1. 导出：``guji export format <册>``（本机现成产物，只读）→ ``reports/<册>/_land/export/<章>.char/cord.json``；
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


def refresh_export(ws: Path, book: str, *, chapter: str) -> Path:
    """本机产物 → 导出目录（每次现导，保证是当前 ★main 包）。出不来抛 SystemExit（别拿旧导出写文本）。"""
    out = export_dir(ws, book)
    out.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "open_guji_cv.cli_v2", "export", "format", book, "-w", str(ws), "--out", str(out), "--chapter", chapter]
    r = subprocess.run(cmd, env={**os.environ, "GUJI_WORKSPACE": str(ws)}, timeout=EXPORT_TIMEOUT)
    if r.returncode or not (out / f"{chapter}.char.json").exists():
        raise SystemExit(f"✗ {book} 导出失败（export format 退出 {r.returncode}）：不写 book-text")
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
