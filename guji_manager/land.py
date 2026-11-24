"""`guji land`：出包后的收尾——新待审格对着中心库条目对账，没变不动、变了就地覆盖（GM4 11-24，sheldon 定）。

边界（sheldon 11-23 定）：cv pipeline 只出产物；之后所有对外交互（对账、推库、传图、发站、book-text）归 guji-manager。
`guji pipeline <管线> <册> --land`：先调 cv 跑管线，再做本命令的收尾（见 ``steps.route``）。

一册的收尾：
1. 取新待审格（cv 的 ``pending-cells`` 入口，从本机现成 products 算，不取包；也可 ``--pending-json`` 直接给）；
2. 对该册条目 ``pending_items.reconcile``（先指纹后格号，没变不动，变了 ver+1，没有的新开、开着而新单没有的 closed）；
3. 条目一格没变：不出新单、不升 rev、不推、不发站；
4. 有变：只写这一册的 items 文件，推库只推它（要 ``guji db sync --only``，CV0 做；没到之前只写本地并打印该推的路径），只发有变的册。

缺省只出计划（dry-run），``--apply`` 才写条目文件。
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

from .review import pending_items as P

CHANGE_KEYS = ("开", "改", "挪格", "图变", "重开", "关")


def plan_book(store: P.ItemStore, cells: list[dict], *, src: str, fps: dict[str, str] | None = None, by: str = "") -> dict:
    """对账（只在内存里算，不写文件）：返回 reconcile 的计数明细与 ``changed``。"""
    work = P.ItemStore(store.path, store.text_id, store.chapter)
    work.items = copy.deepcopy(store.items)
    res = P.reconcile(work, cells, src=src, fps=fps or {}, by=by)
    res["changed"] = any(res[k] for k in CHANGE_KEYS)
    res["_store"] = work
    return res


def summarize(res: dict) -> str:
    parts = [f"{k}{len(res[k])}" for k in CHANGE_KEYS if res[k]]
    return "没变（%d 格不动）" % res["不变"] if not res["changed"] else "，".join(parts) + f"，不动 {res['不变']}"


def cv_pending_cells(ws: Path, book: str, out_dir: Path) -> dict:
    """cv 的纯函数入口（cv #1835，经门面）：本机现成 products → 新待审格。只读，不碰中心库／R2／网站／book-text。
    返回 ``{cells, fps, sprites, digest, …}``；每格一张按内容寻址的单格图（雪碧图坐标会挪，不能用）。"""
    from ._cv import pending_cells, products_root
    out_dir.mkdir(parents=True, exist_ok=True)
    return pending_cells(products_root(), book, images=True, out_dir=out_dir)


def landed_path(ws: Path, book: str) -> Path:
    return ws / "reports" / book / "_land" / "landed.json"


def last_digest(ws: Path, book: str) -> str | None:
    f = landed_path(ws, book)
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("digest")
    except (OSError, ValueError):
        return None


STRUCTURAL = ("开", "挪格", "图变", "重开", "关")        # 条目增减、挪格、图变：一定要动
APPLY_READY = False   # 卡片字段（alt、原因、proof_fields）还没并进 doc 前，doc 级的「改」不可信，不开 --apply


def land(ws: Path, book: str, *, text_id: str, chapter: str, res: dict | None, apply: bool, by: str,
         digest: str | None = None) -> dict:
    """一册收尾。``res`` 是 cv ``pending_cells`` 的返回（或 ``{"cells": [...], "fps": {...}}``）。
    ``digest`` 与上次落定相同 → 整册跳过（不用对账）。"""
    from .datastore.workcopy import data_dir
    data = data_dir(ws)
    items_rel = str(P.items_path(data, text_id, chapter).relative_to(data))
    if digest and digest == last_digest(ws, book):
        return {"book": book, "changed": False, "skipped": "digest", "summary": "digest 同上次，整册跳过", "items_path": items_rel}
    store = P.ItemStore.open(data, text_id, chapter)
    plan = plan_book(store, res["cells"], src=f"land:{book}", fps=res.get("fps") or {}, by=by)
    structural = [k for k in STRUCTURAL if plan[k]]
    out = {"book": book, "changed": bool(structural), "summary": summarize(plan), "items_path": items_rel,
           "doc_only": [] if structural else plan["改"],
           # 挪格：条目没升 rev 时，按「rev＋格号」记的旧票会落到新格号上的别的字（CV4 答复）——要升 rev，或确认该章按单版票为 0
           "needs_rev_bump_check": bool(plan["挪格"])}
    if apply:
        if not APPLY_READY:
            raise SystemExit("✗ --apply 暂不开放：卡片字段（alt、待审原因、proof_fields）还没并进条目 doc，直接写会把没变的格全判成「改」。"
                             "现在只出计划；并入后开放")
        out["written"] = plan["_store"].save()
    return out


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("land", help="出包后收尾：新待审格对账中心库条目（没变不动，变了就地覆盖）")
    p.add_argument("books", nargs="*", help="册名；经 guji pipeline … --land 来时由 cv 的册参数带入")
    p.add_argument("-w", "--workspace", required=True)
    p.add_argument("--text-id", required=True, help="book-text 条目 id（全唐文 995ejelvk0、史記 988g3f0wsu、殿本 96mid1ogzk）")
    p.add_argument("--pending-json", help="直接给新待审格 json（{cells:[…]} 或数组）；只对一册用。缺省调 cv pending-cells")
    p.add_argument("--apply", action="store_true", help="真写条目文件（缺省只出计划）")
    p.add_argument("--run", nargs=argparse.REMAINDER, default=None,
                   help="先跑 cv：其后的参数原样交 `guji-cv pipeline …`，跑完再收尾")


def cmd_land(a) -> int:
    from .swap import chapter_of, parse_books
    ws = Path(a.workspace).resolve()
    if a.run:
        from .pipeline import run as cv_run
        if cv_run(["pipeline", *a.run]).returncode:
            print("✗ cv 管线没跑成，不收尾", file=sys.stderr)
            return 1
    books = parse_books(",".join(a.books)) if a.books else []
    if not books:
        raise SystemExit("land 要给册名")
    if a.pending_json and len(books) != 1:
        raise SystemExit("--pending-json 只能配一册")
    by = os.environ.get("GUJI_ACTOR", "")
    results = []
    for b in books:
        if a.pending_json:
            doc = json.loads(Path(a.pending_json).read_text(encoding="utf-8"))
            res = doc if isinstance(doc, dict) else {"cells": doc}
        else:
            res = cv_pending_cells(ws, b, ws / "reports" / b / "_land")
        r = land(ws, b, text_id=a.text_id, chapter=chapter_of(b), res=res, apply=a.apply, by=by, digest=res.get("digest"))
        results.append(r)
        print(f"{b}\t{'有变' if r['changed'] else '没变'}\t{r['summary']}" + (f"\t已写 {r.get('written', 0)} 行" if a.apply else ""))
    changed = [r["book"] for r in results if r["changed"]]
    print(json.dumps({"changed": changed, "unchanged": [r["book"] for r in results if not r["changed"]]}, ensure_ascii=False))
    if a.apply and changed:
        print("下一步（等 guji db sync --only 落地）：只推 " + " ".join(r["items_path"] for r in results if r["changed"])
              + "；只发这几册。", file=sys.stderr)
    return 0


COMMANDS = {"land": (add_parser, cmd_land)}
