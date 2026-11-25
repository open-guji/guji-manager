"""`guji land`：出包后的收尾——新待审格对着中心库条目对账，没变不动、变了就地覆盖（GM4 11-24，sheldon 定）。

边界（sheldon 11-23 定）：cv pipeline 只出产物；之后所有对外交互（对账、推库、传图、发站、book-text）归 guji-manager。
`guji pipeline <管线> <册> --land`：先调 cv 跑管线，再做本命令的收尾（见 ``steps.route``）。

一册的收尾：
1. 取新待审格（cv 的 ``pending-cells`` 入口，从本机现成 products 算，不取包；也可 ``--pending-json`` 直接给）；
2. 对该册条目 ``pending_items.reconcile``（先指纹后格号，没变不动，变了 ver+1，没有的新开、开着而新单没有的 closed）；
3. 条目一格没变：不出新单、不升 rev、不推、不发站；
4. 有变：条目带上单格图→传 R2→存条目→导出整张单写回（**rev 不变**）→``guji db sync --only`` 只推条目文件和线上单两个文件
   （推不成留 ``_land/needs_sync.json``，下次先补推）→只发有变的册（串行、等空闲、被取消重发）→核线上格数。

缺省只出计划（dry-run），``--apply`` 才真写（``guji pipeline … --land`` 只计划，``--land-apply`` 才 apply）。
卡片字段并入次序（CV4 11-24）：pending_cells（带复审格、自检放上单的格）→卡片→复审→自检→待审原因→锚点原因→相似字字形图（见 ``prepare``）。
**真产物没验过**（云端无 torch/cv2），先在有环境的容器上跑只读计划，计数合理再 ``--apply``。
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
from .swap import current_main

HAND_SRC = ("human:", "script:")          # 人工加的格、手加格（swap-hand-cells）不被机器对账关掉
CHANGE_KEYS = ("开", "改", "挪格", "图变", "重开", "关")


def plan_book(store: P.ItemStore, cells: list[dict], *, src: str, fps: dict[str, str] | None = None, by: str = "",
              us: dict[str, int] | None = None) -> dict:
    """对账（只在内存里算，不写文件）：返回 reconcile 的计数明细与 ``changed``。"""
    work = P.ItemStore(store.path, store.text_id, store.chapter)
    work.items = copy.deepcopy(store.items)
    res = P.reconcile(work, cells, src=src, fps=fps or {}, by=by, keep_src=HAND_SRC, fp_reopen=False, us=us)
    res["changed"] = any(res[k] for k in CHANGE_KEYS)
    res["_store"] = work
    return res


def detail_rows(old: P.ItemStore, new: P.ItemStore) -> list[dict]:
    """对账前后逐条目比：动作、doc 里哪些键变了、新旧 fp。给 ``_land/land-detail.tsv``（QTW 11-24：要能看出是口径还是新裁定）。"""
    rows = []
    for iid, r in new.items.items():
        o = old.items.get(iid)
        if o is not None and o.get("ver") == r.get("ver"):
            continue
        od, nd = (o or {}).get("doc") or {}, r.get("doc") or {}
        keys = sorted(k for k in set(od) | set(nd) if od.get(k) != nd.get(k))
        rows.append({"cell": r["cell"], "action": ("开" if o is None else str(r.get("op") or "")), "id": iid,
                     "old_state": (o or {}).get("state", ""), "new_state": r.get("state", ""),
                     "old_fp": (o or {}).get("fp", ""), "new_fp": r.get("fp", ""),
                     "old_cell": (o or {}).get("cell", ""), "src": r.get("src", ""), "doc_keys": ",".join(keys)})
    return sorted(rows, key=lambda x: P.cell_sort_key(x["cell"]))


def write_detail(ws: Path, book: str, rows: list[dict]) -> Path:
    f = ws / "reports" / book / "_land" / "land-detail.tsv"
    f.parent.mkdir(parents=True, exist_ok=True)
    cols = ["cell", "action", "id", "old_state", "new_state", "old_fp", "new_fp", "old_cell", "src", "doc_keys"]
    f.write_text("\t".join(cols) + "\n" + "".join("\t".join(str(r[c]) for c in cols) + "\n" for r in rows), encoding="utf-8")
    return f


def human_deduct(store: P.ItemStore, cells: list[dict], human: set[str]) -> tuple[list[dict], list[str]]:
    """旧做法里 pending_route 把「已有人裁」的格从新单扣掉；对账后这件事归条目：条目里没有这一格（按格号）、而事件里已有人裁的，
    不新开待审条目（否则「已定的格」被当新判开出来，QTW 11-24 的 61:1:7 就是这类嫌疑）。复审格（recheck）不扣。
    ``human`` 是有人裁的格号集合（裸 id，不带册号）。返回 (留下的 cells, 被扣的格号)。"""
    have = {r["cell"] for r in store.items.values()}
    keep, drop = [], []
    for c in cells:
        cell = P.norm_cell(c.get("cell") or "")
        if cell in human and cell not in have and not c.get("recheck"):
            drop.append(cell)
        else:
            keep.append(c)
    return keep, drop


def alt_changed(old: P.ItemStore, new: P.ItemStore, cells: list[str]) -> list[str]:
    """doc 级改动里相似字（``alt``）有变的格：旧条目没有 alt、新有（出单时 audit alt 没跑，网站显示「机器没定出字」），或内容变了。"""
    out = []
    for cell in cells:
        o, n = old.find(cell), new.find(cell)
        if not (o and n):
            continue
        if ((o[0].get("doc") or {}).get("alt") or []) != ((n[0].get("doc") or {}).get("alt") or []):
            out.append(cell)
    return out


def human_cells(ws: Path, book: str) -> set[str]:
    """事件日志里这一册有人裁的格号（cv ``human_chars``：后到覆盖、过绑定表）；读不了就抛，不当「没有」。"""
    from ._cv import human_chars
    os.environ["GUJI_WORKSPACE"] = str(ws)
    return {P.norm_cell(k) for k in human_chars(book)}


def summarize(res: dict) -> str:
    parts = [f"{k}{len(res[k])}" for k in CHANGE_KEYS if res[k]]
    return "没变（%d 格不动）" % res["不变"] if not res["changed"] else "，".join(parts) + f"，不动 {res['不变']}"


def products_of(ws: Path) -> Path:
    """cv 的 ``products_root()`` 不收参数、按 ``GUJI_WORKSPACE`` 找（旧签名；新版也兼容无参）：先设环境变量再无参调用。"""
    from ._cv import products_root
    os.environ["GUJI_WORKSPACE"] = str(ws)
    return Path(products_root())


def cv_pending_cells(ws: Path, book: str, out_dir: Path, extra: list[str] | None = None) -> dict:
    """cv 的纯函数入口（cv #1835，经门面）：本机现成 products → 新待审格。只读，不碰中心库／R2／网站／book-text。
    返回 ``{cells, fps, sprites, digest, …}``；每格一张按内容寻址的单格图（雪碧图坐标会挪，不能用）。"""
    from ._cv import pending_cells
    out_dir.mkdir(parents=True, exist_ok=True)
    return pending_cells(products_of(ws), book, extra=extra or (), images=True, out_dir=out_dir)


def db_only(ws: Path, verb: str, paths: list[str], force: bool = False) -> int:
    """``guji db pull|sync -w <ws> --only <路径>…``（CV0，manager #901）：只拉／推这些路径，范围外不动、不碰字形库、不重建 glyph.db。
    要先整体 pull 过一次（状态文件）；推时范围内文件被别人改报 StaleBase，用 sync（合并）不用 push；事件撞号需整体 sync。"""
    cmd = [sys.executable, "-m", "open_guji_cv.cli_v2", "db", verb, "-w", str(ws)]
    for p in paths:
        cmd += ["--only", p]
    if verb != "pull":
        cmd += ["--no-glyph"]
    elif force:
        cmd += ["--force"]
    return subprocess.run(cmd, env={**os.environ, "GUJI_DB_NO_GLYPH": "1", "GUJI_WORKSPACE": str(ws)}).returncode


def _sprite_names(doc: dict) -> set[str]:
    names = set()
    img = doc.get("img")
    if isinstance(img, dict) and img.get("s"):
        names.add(img["s"])
    for x in doc.get("alt") or ():
        g = x.get("g")
        if isinstance(g, dict) and g.get("s"):
            names.add(g["s"])
    return names


def attach_sprites(work: P.ItemStore, sprites: list[dict], by: str = "") -> int:
    """条目 doc 里引用的单图（``img.s``、``alt[].g.s``）写进条目自己的 ``sprites``（导出时并进单头 ``sprites[]``，网站发布时传到 COS）。返回改了几条。"""
    by_name = {e["name"]: e for e in sprites}
    n = 0
    for r in list(work.items.values()):
        if r["state"] not in ("open", "resolved"):
            continue
        want = [by_name[x] for x in sorted(_sprite_names(r.get("doc") or {})) if x in by_name]
        have = {e["name"] for e in r.get("sprites") or []}
        if want and {e["name"] for e in want} != have:
            work.put(r, op="machine:sprites", by=by, why="land", sprites=want)
            n += 1
    return n


def upload_sprites(sprites: list[dict], files_dir: Path) -> dict:
    """按 sha256 传进 R2 main 桶（已有的跳过）；任何一张没传成就抛错，不让单子在图缺着的情况下上线。"""
    from .datastore.r2 import upload_files
    ent = {e["sha256"]: Path(files_dir) / e["name"] for e in sprites if (Path(files_dir) / e["name"]).exists()}
    if not ent:
        return {}
    stats = upload_files(ent, bucket="main", ext="webp")
    bad = {k: v for k, v in stats.items() if k not in ("uploaded", "exists")}
    if bad:
        raise RuntimeError(f"单格图没传完：{bad}")
    return stats


def apply_changes(ws: Path, book: str, *, data: Path, text_id: str, chapter: str, work: P.ItemStore, sprites: list[dict],
                  files_dir: Path | None, sync: bool = True) -> dict:
    """有变的册落地：条目带上单图 → 传 R2 → 存条目 → 导出整张单写回（**rev 不变**）→ 只推这两个文件（``db sync --only``）。"""
    sheet_p = P.sheet_path(data, text_id, chapter)
    if not sheet_p.exists():
        raise SystemExit(f"✗ {book} 没有线上单 {sheet_p}（先 db pull --only 或整体 pull 一次）：land 只在原 rev 上就地改条目，不出新单")
    head = json.loads(sheet_p.read_text(encoding="utf-8"))
    out: dict = {"sprites_attached": attach_sprites(work, sprites, os.environ.get("GUJI_ACTOR", ""))}
    if files_dir and sprites:
        out["uploaded"] = upload_sprites(sprites, files_dir)
    out["written"] = work.save()
    sheet = P.export_sheet(work, head)
    sheet_p.write_text(json.dumps(sheet, ensure_ascii=False), encoding="utf-8")
    out["cells"] = len(sheet["cells"])
    if sync:
        rels = [str(P.items_path(data, text_id, chapter).relative_to(data)), str(sheet_p.relative_to(data))]
        marker = ws / "reports" / book / "_land" / "needs_sync.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"rels": rels}), encoding="utf-8")      # 推成才删；没推成下次先补推（对账本身已落本机，重算会是「没变」）
        out["synced"] = db_only(ws, "sync", rels) == 0
        if not out["synced"]:
            # 现行单（pending.json）是条目派生的文件：收单线等刚推过它，两边都改会 SyncConflict。以库为准重派生——
            # 先拿库里的单（--force），条目文件按追加合并推上去，再用合并后的条目重新导出单、推回。
            print(f"⚠ {book} 现行单与库里冲突，以库为准重派生（条目按追加合并）", file=sys.stderr)
            if db_only(ws, "pull", [rels[1]], force=True) == 0 and db_only(ws, "sync", [rels[0]]) == 0:
                merged = P.ItemStore.open(data, text_id, chapter)
                head2 = json.loads(sheet_p.read_text(encoding="utf-8"))
                sheet = P.export_sheet(merged, head2)
                sheet_p.write_text(json.dumps(sheet, ensure_ascii=False), encoding="utf-8")
                out["cells"] = len(sheet["cells"])
                out["synced"] = db_only(ws, "sync", rels) == 0
                out["rederived"] = True
        if out["synced"]:
            marker.unlink(missing_ok=True)
        else:
            raise SystemExit(f"✗ {book} db sync --only 没成：条目与单已写本机，修好后重跑同一条命令（对账是幂等的）")
    return out


def landed_path(ws: Path, book: str) -> Path:
    return ws / "reports" / book / "_land" / "landed.json"


def last_digest(ws: Path, book: str) -> str | None:
    f = landed_path(ws, book)
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("digest")
    except (OSError, ValueError):
        return None


STRUCTURAL = ("开", "挪格", "图变", "重开", "关")        # 条目增减、挪格、图变：一定要动
from . import land_enrich as _E
APPLY_READY = not _E.PENDING_STEPS   # 卡片字段还有没并进 doc 的步（见 land_enrich.PENDING_STEPS）前，doc 级的「改」不可信，不开 --apply


def rev_votes_on(text_id: str, rev: str, fetch=None) -> int:
    """中心库网站收件箱里，仍按「单版 rev＋格号」记的、投在这个 rev 上的票数（不含按条目记的）。
    挪格而 rev 不升时，这些票的格号会落到新格号上的别的字（CV4 11-24）。读失败就抛，不当作 0。"""
    from .feedback import web_inbox as WI
    rows = (fetch or (lambda: WI.fetch("cellreview", text_id)[0]))()
    files = WI.rev_files(rows, text_id)
    return len(files.get(f"{rev}.jsonl", []))


def move_guard(plan: dict, text_id: str, rev: str | None, fetch=None) -> dict | None:
    """一册有格号挪动且该章仍有按当前 rev 记的票 → 拒绝 apply（要先把票落成人裁再对账，或升 rev）。返回拒绝说明，没事返回 None。"""
    if not plan["挪格"]:
        return None
    if not rev:
        return {"why": "有格号挪动，但线上单没有 rev，核不了按 rev 记的票", "moved": plan["挪格"][:10]}
    n = rev_votes_on(text_id, rev, fetch)
    if n:
        return {"why": f"有格号挪动 {len(plan['挪格'])} 格，且线上单 {rev} 上还有 {n} 条按「单版＋格号」记的票：不升 rev 就地改会让这些票落到别的字上。"
                       f"先 guji collect 把票落成人裁，或这册改走升 rev 的老换单路径", "moved": plan["挪格"][:10], "rev_votes": n}
    return None


def land(ws: Path, book: str, *, text_id: str, chapter: str, res: dict | None, apply: bool, by: str,
         digest: str | None = None, pull: bool = False, files_dir: Path | None = None, sync: bool = True,
         human: set[str] | None = None) -> dict:
    """一册收尾。``res`` 是 cv ``pending_cells`` 的返回（或 ``{"cells": [...], "fps": {...}}``）。
    ``digest`` 与上次落定相同 → 整册跳过（不用对账）。"""
    from .datastore.workcopy import data_dir
    data = data_dir(ws)
    items_rel = str(P.items_path(data, text_id, chapter).relative_to(data))
    if digest and digest == last_digest(ws, book):
        return {"book": book, "changed": False, "skipped": "digest", "summary": "digest 同上次，整册跳过", "items_path": items_rel}
    marker = ws / "reports" / book / "_land" / "needs_sync.json"
    if apply and sync and marker.exists():                       # 上次本机写好了但没推成：先补推
        rels = json.loads(marker.read_text(encoding="utf-8"))["rels"]
        if db_only(ws, "sync", rels):
            raise SystemExit(f"✗ {book} 上次没推成的条目文件这次还是推不上（--only {rels}）")
        marker.unlink(missing_ok=True)
    sheet_rel = str(P.sheet_path(data, text_id, chapter).relative_to(data))
    if pull and db_only(ws, "pull", [items_rel, sheet_rel, "feedback/events/"] if human is not None else [items_rel, sheet_rel]):
        print(f"⚠ {book} 条目文件／线上单没拉成（--only {items_rel} {sheet_rel}）：按本机现有的对账", file=sys.stderr)
    store = P.ItemStore.open(data, text_id, chapter)
    deducted: list[str] = []
    if human is not None and res and res.get("cells"):
        kept, deducted = human_deduct(store, res["cells"], human)
        res = {**res, "cells": kept}
    from .u_stamp import u_map
    us = u_map(book, [c.get("cell") or c.get("a") or "" for c in res["cells"]])   # 册有字格身份账才有（T2），没账空
    plan = plan_book(store, keep_old_alt(store, res["cells"]), src=f"land:{book}", fps=res.get("fps") or {}, by=by, us=us)
    structural = [k for k in STRUCTURAL if plan[k]]
    alt_chg = alt_changed(store, plan["_store"], plan["改"])      # 相似字（alt）空→有、或变了：要写，别当「只是 doc 噪声」
    if alt_chg:
        structural.append("alt")
    detail = write_detail(ws, book, detail_rows(store, plan["_store"]))
    out = {"book": book, "changed": bool(structural), "alt_changed": alt_chg,
           "summary": summarize(plan) + (f"，alt 更新 {len(alt_chg)} 格" if alt_chg else ""), "items_path": items_rel, "detail": str(detail), "deducted": deducted,
           "doc_only": [] if structural else plan["改"],
           # 挪格：条目没升 rev 时，按「rev＋格号」记的旧票会落到新格号上的别的字（CV4 答复）——要升 rev，或确认该章按单版票为 0
           "needs_rev_bump_check": bool(plan["挪格"])}
    if out["changed"] and plan["挪格"]:                 # 计划模式也先报：挪格＋按旧 rev 记的票，apply 会拒绝这册
        head = P.sheet_path(data, text_id, chapter)
        rev = json.loads(head.read_text(encoding="utf-8")).get("rev") if head.exists() else None
        try:
            blocked = move_guard(plan, text_id, rev)
        except Exception as e:  # noqa: BLE001 —— 读不到收件箱就按有风险处理，不当 0
            blocked = {"why": f"有格号挪动，但读不了网站收件箱核按 rev 记的票（{type(e).__name__}）", "moved": plan["挪格"][:10]}
        if blocked:
            out["blocked"] = blocked
    if apply:
        if not APPLY_READY:
            raise SystemExit("✗ --apply 暂不开放：卡片字段还有没并进条目 doc 的步（见 land_enrich.PENDING_STEPS）")
        if out.get("blocked"):
            out["written"] = 0
            return out                           # 拒绝：不写条目、不落定；cmd_land 汇总列出
        if out["changed"]:
            out.update(apply_changes(ws, book, data=data, text_id=text_id, chapter=chapter, work=plan["_store"],
                                     sprites=list((res or {}).get("sprites") or []), files_dir=files_dir, sync=sync))
        f = landed_path(ws, book)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"digest": digest, "pack": current_main(ws, book), "at": P.now()}), encoding="utf-8")
    return out


def verify_live(text_id: str, n: int, want_cells: int | None, minutes: float = 6.0) -> bool:
    """线上单的格数＝本地导出的格数（rev 没升，只能这样核）；CDN 缓存最多等几分钟。"""
    import time
    import urllib.request
    from .swap import LIVE
    end = time.time() + minutes * 60
    while True:
        try:
            with urllib.request.urlopen(LIVE.format(text_id=text_id, n=n) + f"?x={int(time.time())}", timeout=30) as r:
                if want_cells is None or len(json.load(r).get("cells") or []) == want_cells:
                    return True
        except Exception:  # noqa: BLE001
            pass
        if time.time() > end:
            return False
        time.sleep(20)


ALT_TIMEOUT = 900        # 每册 audit alt 最多等这么久，出不来快速告警，别拖整趟


def ensure_alt_cards(ws: Path, book: str, cells: list[str], recheck: str | None = None) -> None:
    """卡片文件（``reports/<册>/<册>.cards.alt.json``，``guji audit alt`` 的输出）缺待审格就先补出：
    不补的话 land 出来的条目没有相似字，网站显示「机器没定出字」（QTW 11-24：全唐文 36 格）。出不来只告警，不拦（报缺几格）。"""
    have = set(_E.load_cards(ws, book))
    want = {f"{book}:{c}" if not c.startswith(f"{book}:") else c for c in cells}
    have_ids = {h if h.startswith(f"{book}:") else f"{book}:{h}" for h in have}
    if not (want - have_ids):
        return
    # 总入口是 cv 的 cli_v2（manager 命令经入口点并进来；`guji-manager` 自己没有 audit）
    cmd = [sys.executable, "-m", "open_guji_cv.cli_v2", "audit", "alt", book, "-w", str(ws)]
    if recheck:
        cmd += ["--extra", str(recheck)]
    print(f"⚠ {book} 卡片缺 {len(want - have_ids)} 格相似字，先跑 guji audit alt（最多 {ALT_TIMEOUT // 60} 分钟）", file=sys.stderr)
    try:
        r = subprocess.run(cmd, env={**os.environ, "GUJI_WORKSPACE": str(ws)}, timeout=ALT_TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f"⚠ {book} audit alt 超时（{ALT_TIMEOUT} 秒），不再等：缺相似字的格上线会没有候选字", file=sys.stderr)
        return
    have_ids = {h if h.startswith(f"{book}:") else f"{book}:{h}" for h in _E.load_cards(ws, book)}
    lack = want - have_ids
    if r.returncode or lack:
        print(f"⚠ {book} audit alt 退出 {r.returncode}，仍有 {len(lack)} 格没有相似字卡片（环境缺 torch／权重？）：这些格上线会没有候选字", file=sys.stderr)


def keep_old_alt(store: P.ItemStore, cells: list[dict]) -> list[dict]:
    """新判里这格没算出 alt（卡片对不上、audit alt 没出）：宁可保留条目里原有的 alt，也不要冲掉（QTW 11-25：019/027 册 22 格候选字没了）。"""
    out = []
    for c in cells:
        if not c.get("alt"):
            live = store.find(c.get("cell") or "")
            old = (live[0].get("doc") or {}).get("alt") if live else None
            if old:
                c = {**c, "alt": old}
        out.append(c)
    return out


def hand_without_alt(ws: Path, book: str, text_id: str, chapter: str) -> list[str]:
    """条目里来源是人工／脚本（手加格）、还开着、doc 里没有候选字（alt）的格号：要补 alt。"""
    from .datastore.workcopy import data_dir
    try:
        store = P.ItemStore.open(data_dir(ws), text_id, chapter)
    except (OSError, SystemExit):
        return []
    # 不再只认来源前缀：老单导入的手加格来源是 import:<rev>（QTW 11-25：6 个手加格没补上）；凡开着、没有候选字的条目都并进 extra
    return sorted(r["cell"] for r in store.items.values() if r["state"] == "open" and not (r.get("doc") or {}).get("alt"))


def prepare(ws: Path, book: str, a) -> tuple[dict, Path]:
    """取新待审格并按 CV4 的次序并成完整条目 doc：pending_cells（带复审格、自检要放上单的格）→ 卡片字段 → 复审 → 自检
    → 待审原因 → 锚点原因 → 相似字字形图（按内容寻址）。返回 (res, 单图所在目录)。"""
    from .swap import chapter_of
    out_dir = ws / "reports" / book / "_land"
    products = products_of(ws)
    rc = _E.read_recheck(Path(a.recheck), book) if a.recheck else {}
    rows, kinds = _E.read_seg_flags(Path(a.seg_flags), products, book) if a.seg_flags else ([], [])
    hand = hand_without_alt(ws, book, a.text_id, chapter_of(book))          # 手加格没有候选字：补 alt（只补这一个键）
    res = cv_pending_cells(ws, book, out_dir, extra=list(rc) + hand)
    added = _E.seg_added_cells(rows, kinds, {c["cell"] for c in res["cells"]})
    if added:
        res = cv_pending_cells(ws, book, out_dir, extra=list(rc) + hand + added)
    if a.no_enrich:
        return res, out_dir
    if not getattr(a, "no_audit_alt", False):
        extra_f = None
        if a.recheck or hand:
            extra_f = out_dir / "alt-extra.tsv"
            lines = Path(a.recheck).read_text(encoding="utf-8").splitlines() if a.recheck else []
            extra_f.write_text("\n".join(lines + hand) + "\n", encoding="utf-8")
        ensure_alt_cards(ws, book, [c["cell"] for c in res["cells"]], str(extra_f) if extra_f else None)
    cells = _E.merge_cards(res["cells"], _E.load_cards(ws, book))
    if rc:
        cells = _E.merge_recheck(cells, rc)
    if rows:
        cells, _ = _E.apply_seg(cells, rows, kinds, set(added))
    cells = _E.add_causes(cells, products, book)
    if a.export_char and a.text_vdir:
        cells, _ = _E.anchor_reasons(cells, Path(a.export_char), Path(a.text_vdir), chapter_of(book))
    cells, alt_sprites = _E.alt_glyph_images(cells, out_dir)
    # digest 纳入并好的 doc（卡片、相似字、成因…）：只看 cv 的格号＋图指纹，audit alt 补跑后会被误判「同上次」整册跳过
    import hashlib
    digest = hashlib.sha1((str(res.get("digest")) + json.dumps(cells, ensure_ascii=False, sort_keys=True)).encode()).hexdigest()
    return {**res, "cells": cells, "digest": digest, "sprites": list(res.get("sprites") or []) + alt_sprites}, out_dir


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("land", help="出包后收尾：新待审格对账中心库条目（没变不动，变了就地覆盖）")
    p.add_argument("books", nargs="*", help="册名；经 guji pipeline … --land 来时由 cv 的册参数带入")
    p.add_argument("-w", "--workspace", required=True)
    p.add_argument("--text-id", required=True, help="book-text 条目 id（全唐文 995ejelvk0、史記 988g3f0wsu、殿本 96mid1ogzk）")
    p.add_argument("--pending-json", help="直接给新待审格 json（{cells:[…]} 或数组）；只对一册用。缺省调 cv pending-cells")
    p.add_argument("--recheck", help="复审格清单 tsv（格号<TAB>说明<TAB>旧人裁 id<TAB>旧字<TAB>时间），并进条目 doc")
    p.add_argument("--no-pull", action="store_true", help="不先 db pull --only 拉这一册的条目文件")
    p.add_argument("--seg-flags", help="同字对照自检旗表 tsv（seg_defect --gate 出的，旁边要有 .meta.json）")
    p.add_argument("--export-char", help="本次导出的 <章>.char.json（算锚点类待审原因 A01–A03 用）")
    p.add_argument("--text-vdir", help="book-text 版本目录（<章>.punct.json／entity.json；算锚点类待审原因用）")
    p.add_argument("--no-publish", action="store_true", help="--apply 后不发站（缺省只发有变的册，一次一批）")
    p.add_argument("--no-human-deduct", action="store_true", help="不按事件日志里的人裁扣掉「条目里没有、但已有人裁」的新判格")
    p.add_argument("--text", action="store_true", help="对账后算 book-text 计划：包放行字与 book-text dev 逐格比（只读，出 reports/<册>/_land/text-plan.tsv）")
    p.add_argument("--text-apply", action="store_true", help="计划里有字要改的册写回 book-text（独立 worktree、local_check、推 dev；1.x 开 PR）；隐含 --text")
    p.add_argument("--book-text", help="book-text 仓目录（--text 用）")
    p.add_argument("--keep-files", action="store_true", help="每册收完不清 _packs／导出／单格图（缺省清，盘紧的执行机用）")
    p.add_argument("--no-audit-alt", action="store_true", help="卡片缺格时不自动先跑 guji audit alt")
    p.add_argument("--no-enrich", action="store_true", help="不并卡片字段（只比结构：增减、挪格、图变）")
    p.add_argument("--apply", action="store_true", help="真写条目文件（缺省只出计划）")
    p.add_argument("--run", nargs=argparse.REMAINDER, default=None,
                   help="先跑 cv：其后的参数原样交 `guji-cv pipeline …`，跑完再收尾")


def clean_book(ws: Path, book: str) -> float:
    """这册收完就清（执行机盘紧，QTW 11-25 只剩 1.5G）：``_packs/*/<册>``（再取就有）、本册导出目录、本册单格图缓存。
    不碰 reports 其余、book-text、数据目录；返回释放的 GB。"""
    import shutil
    from .swap import _du
    freed = 0.0
    for p in [*(ws / "_packs").glob(f"*/{book}"), ws / "reports" / book / "_land" / "export"]:
        if p.exists():
            freed += _du(p)
            shutil.rmtree(p, ignore_errors=True)
    for f in (ws / "reports" / book / "_land").glob("*.webp"):      # 单格图已传 R2、条目已落库
        freed += f.stat().st_size / 2 ** 30
        f.unlink(missing_ok=True)
    return freed


def text_step(ws: Path, a, books: list[str], results: list[dict]) -> None:
    """book-text 一步：导出 → 计划（只读）→（--text-apply）有改的册落文本。人裁最高、新覆盖旧的规则同 swap。"""
    from . import land_text as T
    from .datastore.workcopy import data_dir
    from .swap import chapter_of
    if not a.book_text:
        raise SystemExit("✗ --text 要 --book-text <book-text 仓>")
    by = {r["book"]: r for r in results}
    for b in books:
        ch = chapter_of(b)
        store = P.ItemStore.open(data_dir(ws), a.text_id, ch)
        exp = T.refresh_export(ws, b, chapter=ch)
        plan = T.text_plan(ws, b, text_id=a.text_id, book_text=Path(a.book_text), pending=T.open_pending(store), export=exp)
        r = by.get(b) or {}
        r["text"] = {k: v for k, v in plan.items() if k != "changes"}
        print(f"{b}\ttext\t{plan.get('status')}\t改 {plan.get('n', '-')} 格 {plan.get('counts', '')}\t{plan.get('table', plan.get('why', ''))}")
        if plan.get("conflicts"):
            print(f"  ⚠ {b} 新包与人裁冲突（保人裁，交书线确认）{len(plan['conflicts'])} 格：{plan['conflicts'][:5]}", file=sys.stderr)
        if a.text_apply and plan.get("n"):
            res = T.text_apply(ws, b, text_id=a.text_id, book_text=Path(a.book_text), pending=T.open_pending(store), export=exp,
                               note=f"{b} land：包放行字写回文本（{plan['counts']}）")
            r["text"]["apply"] = res
            print(f"  {b} book-text 落文本：{res.get('status')} {res.get('why', '')} {res.get('commit', '')}")


def cmd_land(a) -> int:
    from .swap import chapter_of, parse_books
    ws = Path(a.workspace).resolve()
    os.environ["GUJI_WORKSPACE"] = str(ws)             # cv 的 products_root／缓存按它找，不让用户另外 export（QTW 11-24）
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
        files_dir = None
        if a.pending_json:
            doc = json.loads(Path(a.pending_json).read_text(encoding="utf-8"))
            res = doc if isinstance(doc, dict) else {"cells": doc}
        else:
            res, files_dir = prepare(ws, b, a)
        r = land(ws, b, text_id=a.text_id, chapter=chapter_of(b), res=res, apply=a.apply, by=by, digest=res.get("digest"),
                 pull=not a.no_pull and not a.pending_json, files_dir=files_dir if not a.pending_json else None,
                 human=None if (a.pending_json or a.no_human_deduct) else human_cells(ws, b))
        results.append(r)
        if not a.keep_files and (a.apply or not r["changed"]) and not r.get("blocked") and not (a.text or a.text_apply):
            freed = clean_book(ws, b)         # 写文本那步还要用导出，开了 --text 的整趟结束后再清
            if freed > 0.01:
                print(f"  {b} 清理释放 {freed:.2f} GB", file=sys.stderr)
        print(f"{b}\t{'有变' if r['changed'] else '没变'}\t{r['summary']}\t明细 {r.get('detail', '')}" + (f"\t按人裁扣掉 {len(r['deducted'])} 格 {r['deducted'][:5]}" if r.get("deducted") else "") + (f"\t已写 {r.get('written', 0)} 行" if a.apply else ""))
    if (a.text or a.text_apply) and not a.pending_json:
        text_step(ws, a, books, results)
        if not a.keep_files and a.apply:
            for b in books:
                clean_book(ws, b)
    blocked = {r["book"]: r["blocked"] for r in results if r.get("blocked")}
    for b, v in blocked.items():
        print(f"✗ {b} 拒绝 apply：{v['why']}（挪格 {v['moved']}）", file=sys.stderr)
    changed = [r["book"] for r in results if r["changed"] and r["book"] not in blocked]
    print(json.dumps({"changed": changed, "unchanged": [r["book"] for r in results if not r["changed"]], "blocked": blocked}, ensure_ascii=False))
    if a.apply and changed and not a.no_publish:
        from .swap import publish_batch, vol_no
        concl = publish_batch(changed, a.text_id)              # 串行、等空闲、被取消重发；只发有变的册，一次一批
        print(f"发站 {','.join(changed)}：{concl}", file=sys.stderr)
        purge_only = False
        if concl != "success":
            # 发站 run 红不一定没发成：腾讯云 CDN purge 日配额用完时 run 失败，但数据已上传、带 ?x= 读得到新格。
            # 以线上数据为准：新的就算发成（只提示缓存），读不到才算失败。
            if concl in ("failure", "timeout") and all(
                    verify_live(a.text_id, vol_no(r["book"]), r.get("cells"), minutes=1.0) for r in results if r["book"] in changed):
                purge_only = True
                print(f"⚠ 发站 run 是 {concl}，但线上数据已是新的（多半只是 CDN purge 配额）：不判失败；普通读者要等缓存过期或配额重置",
                      file=sys.stderr)
            else:
                print("⚠ 发站没成功且线上没读到新数据：条目已在中心库，修好后手动触发 proofing-sync（only=…）或重跑；不记已发", file=sys.stderr)
                return 3
        if not purge_only:
            bad = [r["book"] for r in results if r["book"] in changed and not verify_live(a.text_id, vol_no(r["book"]), r.get("cells"))]
            if bad:
                print(f"⚠ 线上格数与本地不符：{' '.join(bad)}（CDN 缓存？几分钟后再核）", file=sys.stderr)
                return 3
    return 4 if blocked else 0


COMMANDS = {"land": (add_parser, cmd_land)}
