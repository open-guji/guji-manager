"""`guji cellvotes`：网站精校页投票 → 人裁事件（M10 精校，2026-10-21）。逻辑在 `feedback/web_votes.py`。

    guji cellvotes draft vol04 --site-book 96mid1ogzk --rev 004-r3 --cord <book-text>/…/default/004.cord.json \
        --out <目录> -w <工作区>                   # 只读：出 drafts.jsonl（可写的）、held.tsv（挂起的）、report.md
                                                  # 另出 recheck.tsv：挂起里回网站再看的格（推翻旧裁、意见不一致、
                                                  # 说无字又给字、格位变了），交 republish.py prep --recheck
    guji cellvotes migrate vol04 --cells <old_new_cells/vol04.tsv[.gz]> --source-rev <新页表rev> --out <目录> -w <工作区>
                                                  # 换图源迁票（GUJI-748）：只读，按格级对照表把每格最新人裁（和给了 --rev 的票）
                                                  # 迁到新格，出 events.jsonl／votes.jsonl／pending.tsv（没迁的）／report.md
    guji cellvotes rebase vol05 --book-id 96mid1ogzk --source-rev 4 --out <目录> -w <工作区>
                                                  # 换图源（页号格号不变，只换像素）后的人裁事件换算：只读，锚里的框按页表 from_rev.H
                                                  # 换到新页、source_rev 改成新页表 rev，出 events.jsonl（id 加 ~r）／pending.tsv／report.md
    guji cellvotes write vol04 <目录> --batch H-web-vol04-2026-10-20 --reviewer Sheldon -w <工作区>
                                                  # 写进数据目录（锚按现行产物算）并消费；推库另跑 guji db sync

先 `guji db pull -w <工作区>`（票、人裁都从数据目录读），再把涉及的页跑到 seed_admit（锚要用现行产物）。
票的来源缺省是数据目录 `feedback/lists/web/<site-book>/<rev>.jsonl`（每日 proofing-sync 写进中心库的快照）；
刚投的票还没同步，用 `--from-kv` 直接管理读网站（令牌取 `--token-env`，缺省 CELLREVIEW_TOKEN，不打印），
或 `--from <文件>`（jsonl，或管理读接口原样存下的 JSON）。

`--cord` 是**出单那一版**的 book-text 格框（rev 对应的文本版本，如 004-r3 ↔ 004 0.2.2）。拿它和现行
cell_shrink 的框比，对不上的格挂起，不写——现行 cv 重切过的列，旧格号已经不是读者看到的那个字。
不给 `--cord` 就要显式 `--no-box-check`（自己担保产物没重切过）。

**`--pack <标签>`（GUJI-730 P1-1）**：出单时 `republish.py push --sync` 把那一版产物存成包 `rev-<rev>`。
draft 给 `--pack rev-004-r6`，就取回这个包当产物根（缓存在 `<产物根>/../_packs/<标签>/`），锚和格位都按出单版算，
不用重跑、格号也不会漂；`--cord` 可省。草稿 meta 记下产物根，write 自动用同一份。

**`--items`（待审条目化，sheldon 11-10）**：网站按条目记的票（`feedback/lists/web/<site-book>/items.jsonl`，或 `--from-kv` 管理读
`?items=1`）。每票按条目 id 换成条目**现在**的格号、`rev` 记成 `--rev`（现行单），其余同上——换单不丢票，不用「换单前先落完票」。
`--rev` 给现行单的 rev，`--pack` 给现行单的产物包。write 时这些条目标 `resolved`（记事件 id），整张单随之重导。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

SITE = "https://www.openguji.com"
DEFAULT_SOURCE = "网站精校意见"


def _print(s: str = "") -> None:
    sys.stdout.write(s + "\n")


def _fetch_kv(site_book: str, rev: str, token: str, site: str = SITE) -> list[dict]:
    """管理读 /api/cellreview，按 cursor 翻页取全。"""
    items, cursor = [], ""
    while True:
        q = {"rev": rev, "book": site_book, "limit": "256", **({"cursor": cursor} if cursor else {})}
        req = urllib.request.Request(f"{site}/api/cellreview?{urllib.parse.urlencode(q)}",   # 站点拒收 urllib 缺省 UA
                                     headers={"Authorization": f"Bearer {token}", "User-Agent": "open-guji-cv/cellvotes"})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
        if not d.get("success"):
            raise SystemExit(f"管理读失败：{d.get('error')}")
        items += d.get("items") or []
        cursor = d.get("cursor") or ""
        if not d.get("hasMore") or not cursor:
            return items


def _item_votes(args) -> tuple[list[dict], str]:
    """按条目记的票 → 按现行格号记的票（a＝条目现在的格号，rev＝--rev）。条目找不到的丢掉（计数）。"""
    from ._cv import feedback_root
    from ._cv import load_votes
    from .review import pending_items as P
    if args.from_kv:
        tok = os.environ.get(args.token_env)
        if not tok:
            raise SystemExit(f"--from-kv 要环境变量 {args.token_env}（网站管理令牌）")
        raw, where = _fetch_kv_items(args.site_book, tok), "网站管理读 /api/cellreview?items=1"
    else:
        p = Path(args.from_file) if args.from_file else feedback_root() / "lists" / "web" / args.site_book / "items.jsonl"
        if not p.exists():
            raise SystemExit(f"没有 {p}（先 guji db pull；票刚投、还没同步就用 --from-kv）")
        raw, where = load_votes(p), str(p)
    chap = args.rev.split("-r")[0]
    store = P.ItemStore.open(feedback_root().parent, args.site_book, chap)
    out, lost = [], 0
    for v in raw:
        if str(v.get("vol") or "").zfill(3) != chap.zfill(3):
            continue
        it = store.items.get(v.get("item") or "")
        if it is None:
            lost += 1
            continue
        out.append({**v, "a": it["cell"], "rev": args.rev, "item": it["id"]})
    return out, f"{where}：条目票 {len(out)} 条" + (f"（{lost} 条找不到条目，丢掉）" if lost else "")


def _fetch_kv_items(site_book: str, token: str, site: str = SITE) -> list[dict]:
    items, cursor = [], ""
    while True:
        q = {"items": "1", "book": site_book, "limit": "256", **({"cursor": cursor} if cursor else {})}
        req = urllib.request.Request(f"{site}/api/cellreview?{urllib.parse.urlencode(q)}",
                                     headers={"Authorization": f"Bearer {token}", "User-Agent": "open-guji-cv/cellvotes"})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
        if not d.get("success"):
            raise SystemExit(f"管理读失败：{d.get('error')}")
        items += d.get("items") or []
        cursor = d.get("cursor") or ""
        if not d.get("hasMore") or not cursor:
            return items


def _votes(args) -> tuple[list[dict], str]:
    from ._cv import feedback_root
    from ._cv import load_votes
    if getattr(args, "items", False):
        return _item_votes(args)
    if args.from_file:
        return load_votes(Path(args.from_file)), f"文件 {args.from_file}"
    if args.from_kv:
        tok = os.environ.get(args.token_env)
        if not tok:
            raise SystemExit(f"--from-kv 要环境变量 {args.token_env}（网站管理令牌）")
        items = _fetch_kv(args.site_book, args.rev, tok)
        if items:
            # 两种记法并存（旧网站按单版、新网站按条目）：只读了其中一种，另一种的票不会落——11-13 第五册 005-r13 的 25 票就这么漏的
            chap = args.rev.split("-r")[0].zfill(3)
            n_item = sum(1 for v in _fetch_kv_items(args.site_book, tok) if str(v.get("vol") or "").zfill(3) == chap)
            if n_item:
                _print(f"⚠ 这一册还有 {n_item} 条按条目记的票没读（本次按单版读了 {len(items)} 票）：另跑一遍 --items 落它们，别漏。")
        if not items:
            # 新网站按条目记票，旧口径读到 0 条：自动改读条目票（下游 meta／write 也按条目处理）
            args.items = True
            raw, where = _item_votes(args)
            _print(f"按格号读到 0 票，自动改读条目票：{where}")
            return raw, where
        return items, f"网站管理读 /api/cellreview（{len(items)} 条）"
    p = feedback_root() / "lists" / "web" / args.site_book / f"{args.rev}.jsonl"
    if not p.exists():
        raise SystemExit(f"数据目录没有 {p}（先 guji db pull；票刚投、还没同步就用 --from-kv）")
    return load_votes(p), f"数据目录 {p.relative_to(feedback_root().parent)}"


def _box_checker(book: str, cord_path: Path, tol: float):
    """返回 check(a)：按页懒读现行 cell_shrink，和出单版 cord 比。缺这一页的产物就挂起（不猜）。"""
    from ._cv import page_key
    from ._cv import check_cell, cord_boxes, shrink_boxes
    from ._cv import ProductStore
    cord = cord_boxes(json.loads(Path(cord_path).read_text(encoding="utf-8")))
    store = ProductStore()
    main = ProductStore(_MAIN_ROOT[0]) if _MAIN_ROOT[0] else None
    cache: dict[int, dict | None] = {}

    def check(a: str) -> str | None:
        pg = int(a.split(":")[0])
        width, old = cord.get(pg, (0, {}))
        if pg not in cache:
            raw = store.read_raw(book, "cell_shrink", page_key(pg))
            if raw is None and main is not None:       # 出单版包没带这页（那页没重跑过）：用主产物
                raw = main.read_raw(book, "cell_shrink", page_key(pg))
            cache[pg] = None if raw is None else shrink_boxes(raw.get("char_index") or {}, width)
        if cache[pg] is None:
            return f"现行产物缺第 {pg} 页（先 guji pipeline keben_body_v2 {book} --pages {pg} --to seed_admit）"
        return check_cell(a, old, cache[pg], tol)
    return check


#: 用了 --pack 时记下主产物根（``_box_checker`` 对包里缺的页退回它）
_MAIN_ROOT: list = [None]


def _use_pack(book: str, label: str) -> Path:
    """取回出单版产物包当产物根（已取过就复用），并设 GUJI_PRODUCTS_DIR，之后读产物、算锚都走它。"""
    from ._cv import products_root
    from ._cv import packs as PK
    pr = products_root()
    base = pr.parent.parent if pr.parent.name == "_packs" else pr.parent   # 已经指到某个包时，回到原产物根旁边
    root = base / "_packs" / label
    if pr.parent.name != "_packs":
        _MAIN_ROOT[0] = pr           # 出单版包只含重跑过的页；没重跑的页格位没变，核格位时退回这个主产物根
    if not (root / book).is_dir() or not any((root / book).iterdir()):
        info = PK.fetch_products(book, root, label=label, force=True)
        _print(f"已取出单版产物包 {info['name']} → {root}")
    os.environ["GUJI_PRODUCTS_DIR"] = str(root)
    return root


def _sheet(args) -> dict | None:
    """投票时网站上那张单（读 `prior`：投票人看到的旧人裁）。--sheet 给了就用；否则数据目录线上单 rev 对得上就用它。"""
    from ._cv import feedback_root
    if getattr(args, "sheet", None):
        p = Path(args.sheet)
    else:
        p = feedback_root() / "lists" / "proofing" / args.site_book / f"{args.rev.split('-r')[0].zfill(3)}.pending.json"
    if not p.exists():
        return None
    doc = json.loads(p.read_text(encoding="utf-8"))
    if doc.get("rev") != args.rev:
        return None
    return {**doc, "_path": str(p)}


def _route(t, out: Path, rev: str) -> dict:
    """票按去向分流（A34 11-08）：text＝改文本批（□→字，走 1.x revise）；structure＝切分类（切坏无字、错位、破损、
    带备注的看不出），写成按页按列的清单交切分线（A22/A31）；exclude＝无字（排除名单）；recheck＝推翻旧裁回网站复审。
    人裁事件照常全写进中心库（切分线自己去库里按批次找），这里只给出人读的去向清单 route.md 与 structure.tsv。"""
    text, structure, exclude, held = [], [], [], []
    for d in t.drafts:
        v, pl = d.payload.get("v"), d.payload
        note = "；".join(x.get("note") or "" for x in d.votes if x.get("note"))
        shown = next((x.get("shown") for x in d.votes if x.get("shown")), "")
        if d.held:
            held.append((d.a, d.held))
        elif v == "confirm":
            text.append((d.a, pl.get("shape", "")))
        elif v == "seg_defect":
            if pl.get("shape"):
                text.append((d.a, pl["shape"]))
            structure.append((d.a, "切坏" + ("（字对，已入文本批）" if pl.get("shape") else "（无字）"), shown, note))
        elif v == "damaged":
            structure.append((d.a, "破损/无整页坐标", shown, note))
        elif v == "not_a_char":
            exclude.append(d.a)
    for a, why in t.skipped:
        if "看不出" in why:                    # 与已有人裁一致等跳过项不进清单（那是重跑 draft 时的幂等）
            structure.append((a, "看不出/错位：" + why, "", ""))
    from .opinions.schema import cell_key
    structure.sort(key=lambda r: cell_key(r[0]))
    with open(out / "structure.tsv", "w", encoding="utf-8") as f:
        f.write("页\t列\t格\t类\t页面显示字\t备注\n")
        for a, kind, shown, note in structure:
            pg, col, slot = a.split(":")
            f.write(f"{pg}\t{col}\t{slot}\t{kind}\t{shown}\t{note}\n")
    L = [f"# {rev} 票的去向", "", f"- 改文本批：{len(text)} 格（□→字，走 1.x revise 一批一 PR）",
         f"- 切分类清单：{len(structure)} 格（structure.tsv，按页按列；事件已写中心库，切分线按批次自取）",
         f"- 无字（排除名单，需 --include-none）：{len(exclude)} 格", f"- 挂起：{len(held)} 格", ""]
    pages: dict[str, list] = {}
    for a, kind, shown, note in structure:
        pages.setdefault(a.split(":")[0], []).append(f"{a} {kind}")
    if pages:
        L.append("## 切分类按页")
        for pg in sorted(pages, key=int):
            L.append(f"- 第 {pg} 页（{len(pages[pg])} 格）：" + "；".join(pages[pg]))
    (out / "route.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return {"text": len(text), "structure": len(structure), "exclude": len(exclude), "held": len(held)}


def cmd_draft(args) -> None:
    from ._cv import feedback_root
    from ._cv import EventLog
    from ._cv import latest_human, latest_votes, recheck_rows, triage
    pack_root = _use_pack(args.book, args.pack) if args.pack else None
    if not args.cord and not args.no_box_check and not pack_root:
        raise SystemExit("要给 --cord（出单那一版 book-text 的 <册>.cord.json）或 --pack（出单版产物包），或显式 --no-box-check")
    raw, where = _votes(args)
    if not raw:
        raise SystemExit(f"读到 0 票（{where}）：核对 --rev／--site-book／--items，别拿空草稿往下走")
    votes, dropped = latest_votes(raw, args.site_book, args.rev)
    human = latest_human(EventLog(feedback_root()).iter_all())
    check = _box_checker(args.book, Path(args.cord), args.tol) if args.cord else None
    sheet = _sheet(args)
    sheet_prior = {c["cell"]: (c.get("prior") or {}).get("id") for c in (sheet or {}).get("cells", [])
                   if (c.get("prior") or {}).get("id")}
    from .charnorm import load_norm
    t = triage(votes, args.book, human, include_none=args.include_none, check=check, sheet_prior=sheet_prior,
               same=load_norm(args.book).same)
    # 待审原因（sheldon 11-03 定）：照投票时那张单上的 pending_reason 写进事件；单对不上或格不在单上就 unknown
    sheet_reason = {c["cell"]: c.get("pending_reason") or "unknown" for c in (sheet or {}).get("cells", [])}
    for d in t.drafts:
        if d.payload:
            d.payload["pending_reason"] = sheet_reason.get(d.a, "unknown")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    source = f"{args.source}（{args.rev}）"
    with open(out / "drafts.jsonl", "w", encoding="utf-8") as f:
        for d in t.ready:
            f.write(json.dumps(d.row(source), ensure_ascii=False) + "\n")
    with open(out / "held.tsv", "w", encoding="utf-8") as f:
        f.write("格位\t拟写\t理由\t票\n")
        for d in t.held:
            f.write(f"{d.a}\t{json.dumps(d.payload, ensure_ascii=False)}\t{d.held}\t"
                    f"{'；'.join(v['choice'] + (('=' + v['char']) if v.get('char') else '') for v in d.votes)}\n")
    rc = recheck_rows(t)
    with open(out / "recheck.tsv", "w", encoding="utf-8") as f:
        f.write("格位\t说明\t旧人裁\t旧人裁的字\t旧人裁时间\n")
        for r in rc:
            f.write("\t".join(r) + "\n")
    n_over = sum(1 for d in t.ready if d.payload.get("overrides"))
    meta = {"book": args.book, "site_book": args.site_book, "rev": args.rev, "votes_from": where,
            "recheck": len(rc), "overrides": n_over, "sheet": (sheet or {}).get("_path"),
            "cord": str(args.cord) if args.cord else None, "pack": args.pack, "items": bool(getattr(args, "items", False)),
            "products_root": str(pack_root) if pack_root else None, "n_raw": len(raw), "n_votes": len(votes),
            "dropped": dropped, "ready": len(t.ready), "held": len(t.held), "skipped": t.skipped}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# {args.book} 网页投票 → 事件草稿（{args.rev}）", "",
             f"- 票：{where}；原始 {len(raw)} 条，有效 {len(votes)} 条，丢弃 {dropped or 0}",
             f"- 格位核对：{('对 ' + str(args.cord)) if args.cord else ('产物即出单版包 ' + args.pack) if args.pack else '未核（--no-box-check）'}",
             f"- **可写 {len(t.ready)} 格**（drafts.jsonl，其中在复审单上有意推翻旧人裁 {n_over} 格），挂起 {len(t.held)} 格（held.tsv），"
             f"跳过 {len(t.skipped)} 格",
             f"- 挂起里回网站再看的 {len(rc)} 格（recheck.tsv，交 `republish.py prep --recheck`）", "",
             "| 格位 | 拟写 | 状态 |", "|---|---|---|"]
    for d in t.drafts:
        what = d.payload.get("shape") or d.payload.get("quality") or d.payload.get("reason") or ""
        lines.append(f"| {d.a} | {d.payload.get('v', '')} {what} | {d.held or '可写'} |")
    for a, why in t.skipped:
        lines.append(f"| {a} | — | 跳过：{why} |")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _print(f"{where}：有效 {len(votes)} 条 → 可写 {len(t.ready)}（推翻旧裁 {n_over}）、挂起 {len(t.held)}"
           f"（回网站再看 {len(rc)}）、跳过 {len(t.skipped)}")
    for d in t.held:
        _print(f"  挂起 {d.a}：{d.held}")
    r = _route(t, out, args.rev)
    _print(f"去向：改文本 {r['text']}、切分类 {r['structure']}、无字 {r['exclude']}、挂起 {r['held']}")
    _print(f"→ {out}/drafts.jsonl、held.tsv、report.md、route.md、structure.tsv")


def cmd_write(args) -> None:
    from ._cv import batches_root, feedback_root, verdicts_root
    from ._cv import EventLog
    from ._cv import GoldStore
    from ._cv import ProductStore
    from ._cv import BatchStore
    from ._cv import write_events
    out = Path(args.dir)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    if meta["book"] != args.book:
        raise SystemExit(f"草稿是 {meta['book']} 的，不是 {args.book}")
    if meta.get("products_root"):            # 草稿按出单版产物包算的，锚也要按它算
        os.environ["GUJI_PRODUCTS_DIR"] = meta["products_root"]
        _print(f"产物根：出单版包 {meta.get('pack')}（{meta['products_root']}）")
    rows = [json.loads(line) for line in (out / "drafts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        _print("没有可写的格")
        return
    # 幂等键：同一份草稿重跑 write 不重复写（控制台写入路径按 payload.request_id 判重）
    rid = "cellvotes-" + hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    res = write_events(EventLog(feedback_root()), BatchStore(batches_root()), GoldStore(verdicts_root()),
                       ProductStore(None), batch=args.batch, step="seed_admit", unit="cell", kind="confirm",
                       events=rows, request_id=rid, consume=not args.no_consume, reviewer=args.reviewer)
    _print(json.dumps(res, ensure_ascii=False, indent=1))
    if meta.get("items") and not res.get("duplicate"):
        _resolve_items(meta, rows, res, args.reviewer or "")
    if not res.get("duplicate"):
        _print("已写进数据目录；推库：guji db sync -w <工作区>（写中心库前先报告、等点头）")


def _resolve_items(meta: dict, rows: list[dict], res: dict, by: str) -> None:
    """落了票的条目标 resolved（待审条目化），并重导整张单。"""
    from ._cv import feedback_root
    from .review import pending_items as P
    data = feedback_root().parent
    store = P.ItemStore.open(data, meta["site_book"], meta["rev"].split("-r")[0])
    ids = dict(zip([r.get("a") for r in rows], res.get("ids") or [None] * len(rows)))
    n = 0
    for r in rows:
        hit = [x for x in store.find(r.get("a") or "") if x["state"] in ("open", "withdrawn")]
        if hit:
            store.resolve(hit[0]["id"], by=by or "cellvotes", event=ids.get(r.get("a")) or "", why=f"落票 {meta['rev']}")
            n += 1
    if n:
        store.save()
        from .cli_pending import export
        _print(f"条目标已裁 {n} 条；整张单 → {export(store, data)}")


def cmd_migrate(args) -> None:
    """换图源迁票提案（逻辑在 `feedback/cell_migrate.py`）。只读：不写事件、不写库。"""
    from ._cv import feedback_root
    from ._cv import cell_migrate as M
    from ._cv import EventLog
    from ._cv import latest_votes
    miss = [k for k in ("cells", "source_rev", "out") if not getattr(args, k)]
    if miss:
        raise SystemExit("migrate 要 " + "、".join("--" + k.replace("_", "-") for k in miss))
    rows = M.load_table(args.cells)
    if args.events:
        from ._cv import Event
        events = [Event.model_validate_json(line) for f in args.events
                  for line in Path(f).read_text(encoding="utf-8").splitlines() if line.strip()]
        where = "、".join(args.events)
    else:
        events = [e for e in EventLog(feedback_root()).iter_all(raw=True)   # 迁移读旧页号的事件：不过页表 rev 判据
                  if e.target.key.startswith(args.book + ":")]
        where = f"数据目录 {feedback_root()}"
    bindings = json.loads(Path(args.bind).read_text(encoding="utf-8")) if args.bind else None
    res = M.migrate_events(events, rows, args.book, args.source_rev, min_iou=args.min_iou, bindings=bindings)
    if args.site_book and args.rev:
        raw, vwhere = _votes(args)
        votes, _ = latest_votes(raw, args.site_book, args.rev)
        M.migrate_votes(votes, rows, args.book, args.source_rev, min_iou=args.min_iou, new_rev=args.new_rev, result=res)
        where += f"；票 {vwhere}"
    M.write_report(res, Path(args.out), cells_path=str(args.cells), extra={"人裁来源": where})
    pe = sum(res.reasons("人裁").values())
    _print(f"人裁 {res.n_events_in} → 迁出 {len(res.events)}、合并 {res.n_merged}、没迁 {pe}；"
           f"票 {res.n_votes_in} → 迁出 {len(res.votes)}、没迁 {sum(res.reasons('票').values())}  → {args.out}/report.md")


def cmd_rebase(args) -> None:
    """换图源（页号格号不变）后的人裁事件换算提案（逻辑在 `feedback/source_rebase.py`）。只读：不写事件、不写库。"""
    import re
    from ._cv import feedback_root
    from ._cv import EventLog
    from .datastore import sources as S
    from .feedback import source_rebase as R
    miss = [k for k in ("book_id", "source_rev", "out") if not getattr(args, k)]
    if miss:
        raise SystemExit("rebase 要 " + "、".join("--" + k.replace("_", "-") for k in miss))
    m = re.fullmatch(r"vol(\d+)", args.book)
    if not m:
        raise SystemExit(f"rebase 的册 id 要像 vol05：{args.book}")
    vol, src = S.norm_vol(m[1]), S._client()
    if args.events:
        events = [json.loads(line) for f in args.events
                  for line in Path(f).read_text(encoding="utf-8").splitlines() if line.strip()]
        where = "、".join(args.events)
    else:
        events = [e.model_dump(mode="json") for e in EventLog(feedback_root()).iter_all(raw=True)]   # 读旧页号：不过页表 rev 闸
        where = f"数据目录 {feedback_root()}"

    def get_table(rev: int):
        try:
            return S.read_table(src, args.book_id, vol, rev)
        except FileNotFoundError:
            return None

    res = R.rebase_events(events, args.book, int(args.source_rev), get_table)
    R.write_report(res, Path(args.out), extra={"事件来源": where})
    _print(f"事件 {res.n_in} → 迁出 {len(res.events)}、不迁 {sum(res.skipped.values())}、待办 {len(res.pending)}  → {args.out}/report.md")


def add_parser(sub) -> None:
    p = sub.add_parser("cellvotes", help="网站精校页投票 → 人裁事件：draft（只读出草稿）| write（写入并消费）| migrate（换图源迁票提案，只读）| rebase（页号不变的换图源：人裁锚换算提案，只读）")
    p.add_argument("action", choices=["draft", "write", "migrate", "rebase"])
    p.add_argument("book", help="cv 册 id，如 vol04")
    p.add_argument("dir", nargs="?", default=None, help="write：draft 的输出目录")
    p.add_argument("--site-book", help="draft：网站书 id，如 96mid1ogzk")
    p.add_argument("--rev", help="draft：待审单版本，如 004-r3")
    p.add_argument("--cord", default=None, help="draft：出单那一版 book-text 的 <册>.cord.json")
    p.add_argument("--no-box-check", action="store_true", help="draft：不核格位（自己担保产物没重切过）")
    p.add_argument("--pack", default=None, help="draft：出单版产物包标签（republish 存的 rev-<rev>），取回当产物根，免重跑")
    p.add_argument("--tol", type=float, default=8.0, help="draft：格框容差（像素，缺省 8）")
    p.add_argument("--sheet", default=None, help="draft：投票时的待审单（读 prior：复审格上有意推翻旧人裁）；"
                                                 "缺省数据目录里同 rev 的线上单")
    p.add_argument("--include-none", action="store_true", default=True, help="draft：「无字」也写（2026-11-10 起缺省就写，此项保留兼容）")
    p.add_argument("--no-none", dest="include_none", action="store_false", help="draft：「无字」票不写（挂起）")
    p.add_argument("--from", dest="from_file", default=None, help="draft：票从文件读")
    p.add_argument("--from-kv", action="store_true", help="draft：票直接管理读网站")
    p.add_argument("--items", action="store_true", help="draft：读按条目记的票（换成条目现在的格号；--rev 给现行单）")
    p.add_argument("--token-env", default="CELLREVIEW_TOKEN", help="draft --from-kv：令牌的环境变量名")
    p.add_argument("--source", default=DEFAULT_SOURCE, help="draft：写进 payload.source 的来源说明")
    p.add_argument("--out", default=None, help="draft：输出目录")
    p.add_argument("--batch", default=None, help="write：批次名，如 H-web-vol04-2026-10-20")
    p.add_argument("--reviewer", default=None, help="write：裁决人（投票的人）")
    p.add_argument("--cells", default=None, help="migrate：格级对照表 old_new_cells/<册>.tsv（可 .gz）；旧格取出单那一版")
    p.add_argument("--events", action="append", default=None, help="migrate：旧人裁事件 jsonl（可重复）；缺省读数据目录")
    p.add_argument("--source-rev", default=None, help="migrate：新页表 rev，写进迁移事件 anchor.source_rev")
    p.add_argument("--bind", default=None, help="migrate：旧 main 上的现行绑定 JSON（{事件 id: {bound, status}}，"
                                                "`bindings.book_bindings` 的输出）；给了就按绑定格查表，没认上格的不迁")
    p.add_argument("--min-iou", type=float, default=0.5, help="migrate：IoU 门槛，低于它的不迁（缺省 0.5）")
    p.add_argument("--new-rev", default=None, help="migrate：迁出的票改写成这个待审单 rev（缺省不改）")
    p.add_argument("--book-id", default=None, help="rebase：网站书 id（页表在 R2 的 <书>/<册>/r<rev>.json），如 96mid1ogzk")
    p.add_argument("--no-consume", action="store_true", help="write：只写不消费")


def cmd_cellvotes(args) -> None:
    if args.action == "draft":
        missing = [k for k in ("site_book", "rev", "out") if not getattr(args, k)]
        if missing:
            raise SystemExit("draft 要 " + "、".join("--" + k.replace("_", "-") for k in missing))
        cmd_draft(args)
    elif args.action == "migrate":
        cmd_migrate(args)
    elif args.action == "rebase":
        cmd_rebase(args)
    else:
        if not args.dir or not args.batch or not args.reviewer:
            _print("错误：write 要 <目录> --batch --reviewer（缺：" + "、".join(
                n for n, v in (("<目录>", args.dir), ("--batch", args.batch), ("--reviewer", args.reviewer)) if not v) + "）")
            raise SystemExit(2)         # 非零退出码，脚本里别把一行用法当成功
        cmd_write(args)


#: 并进 `guji` 的子命令（同插件接口 `guji.commands`；cv 侧由 `cli_v2.MANAGER_CLI_MODULES` 登记，拆分 P1）
COMMANDS = {"cellvotes": (add_parser, cmd_cellvotes)}
