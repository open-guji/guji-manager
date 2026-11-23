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
    guji cellvotes reconcile vol04 --site-book 96mid1ogzk [--rev 004-r13|all]
                                                  # 双写对账：网站 KV 管理读 vs 中心库 web_inbox 逐票比（只读，差异退出码 1）
    guji cellvotes write vol04 <目录> --batch H-web-vol04-2026-10-20 --reviewer Sheldon -w <工作区>
                                                  # 写进数据目录（锚按现行产物算）并消费；推库另跑 guji db sync

先 `guji db pull -w <工作区>`（票、人裁都从数据目录读），再把涉及的页跑到 seed_admit（锚要用现行产物）。
票的来源缺省是数据目录 `feedback/lists/web/<site-book>/<rev>.jsonl`（每日 proofing-sync 写进中心库的快照）；
刚投的票还没同步，用 `--from-kv` 直接管理读网站（令牌取 `--token-env`，缺省 CELLREVIEW_TOKEN，不打印），
或 `--from <文件>`（jsonl，或管理读接口原样存下的 JSON）。
`--from-inbox`（A20 11-21）：读中心库网站收件箱 web_inbox（`GET /v1/web/inbox`，网站 KV 与 D1 双写期），取到的是同一份 KV 值，
产出与 `--from-kv` 相同；令牌用中心库读令牌（GUJI_DATA_TOKEN 等），不用网站令牌。双写对账通过前缺省仍是 KV。

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

import datetime as dt
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
    if _live(args):
        raw, where = _live_items(args), _live_where(args, items=True)
    else:
        p = Path(args.from_file) if args.from_file else feedback_root() / "lists" / "web" / args.site_book / "items.jsonl"
        if not p.exists():
            raise SystemExit(f"没有 {p}（先 guji db pull；票刚投、还没同步就用 --from-kv）")
        raw, where = load_votes(p), str(p)
    chap = args.rev.split("-r")[0]
    store = P.ItemStore.open(feedback_root().parent, args.site_book, chap)
    out, lost = [], 0
    mine = [v for v in raw if str(v.get("vol") or "").zfill(3) == chap.zfill(3)]
    args._n_item_raw, args._item_lost = len(mine), 0      # --allow-empty 要核：这一章条目票原始条数
    for v in mine:
        it = store.items.get(v.get("item") or "")
        if it is None:
            lost += 1
            continue
        out.append({**v, "a": it["cell"], "rev": args.rev, "item": it["id"],
                    "vote_rev": v.get("rev") or args.rev, "vote_a": v.get("a") or it["cell"]})
    args._item_lost = lost
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


def _live(args) -> bool:
    """当场读全网站票：``--from-kv``（网站 KV 管理读）或 ``--from-inbox``（中心库 web_inbox，A20 11-21）。"""
    kv, inbox = bool(getattr(args, "from_kv", False)), bool(getattr(args, "from_inbox", False))
    if kv and inbox:
        raise SystemExit("--from-kv 与 --from-inbox 只能选一个")
    if not kv and not inbox and not getattr(args, "from_file", None):
        # A20 11-22：网站票缺省读中心库 web_inbox（D1 为真源）；--from 文件或 GUJI_VOTES_FROM=kv 才不走
        if (os.environ.get("GUJI_VOTES_FROM") or "inbox").strip().lower() != "kv":
            args.from_inbox = inbox = True
    return kv or inbox


def _kv_token(args) -> str:
    tok = os.environ.get(args.token_env)
    if not tok:
        raise SystemExit(f"--from-kv 要环境变量 {args.token_env}（网站管理令牌）")
    return tok


def _inbox_rows(args) -> list[dict]:
    """收件箱里本书的精校票（一次读全，缓存在 args 上；按单版、按条目两种键都在里面）。"""
    rows = getattr(args, "_inbox_rows", None)
    if rows is None:
        from .feedback import web_inbox as WI
        rows, seq = WI.fetch("cellreview", args.site_book, token_env=getattr(args, "inbox_token_env", None))
        args._inbox_rows, args._inbox_seq = rows, seq
    return rows


def _live_rev(args) -> list[dict]:
    if getattr(args, "from_inbox", False):
        from .feedback import web_inbox as WI
        return WI.rev_votes(_inbox_rows(args), args.site_book, args.rev)
    return _fetch_kv(args.site_book, args.rev, _kv_token(args))


def _live_items(args) -> list[dict]:
    if getattr(args, "from_inbox", False):
        from .feedback import web_inbox as WI
        return WI.item_votes(_inbox_rows(args), args.site_book)
    return _fetch_kv_items(args.site_book, _kv_token(args))


def _live_where(args, items: bool = False) -> str:
    if getattr(args, "from_inbox", False):
        return f"中心库网站收件箱 web_inbox（{'按条目' if items else '按单版'}，seq≤{getattr(args, '_inbox_seq', 0)}）"
    return "网站管理读 /api/cellreview" + ("?items=1" if items else "")


def _votes(args) -> tuple[list[dict], str]:
    from ._cv import feedback_root
    from ._cv import load_votes
    if getattr(args, "items", False):
        return _item_votes(args)
    if args.from_file:
        return load_votes(Path(args.from_file)), f"文件 {args.from_file}"
    if _live(args):
        items = _live_rev(args)
        args._n_rev_raw = len(items)                       # 按单版读到几条（读失败会直接抛，到这里就是读全了）
        if items:
            # 两种记法并存（旧网站按单版、新网站按条目）：只读了其中一种，另一种的票不会落——11-13 第五册 005-r13 的 25 票就这么漏的
            chap = args.rev.split("-r")[0].zfill(3)
            n_item = sum(1 for v in _live_items(args) if str(v.get("vol") or "").zfill(3) == chap)
            if n_item:
                _print(f"⚠ 这一册还有 {n_item} 条按条目记的票没读（本次按单版读了 {len(items)} 票）：另跑一遍 --items 落它们，别漏。")
        if not items:
            # 新网站按条目记票，旧口径读到 0 条：自动改读条目票（下游 meta／write 也按条目处理）
            args.items = True
            raw, where = _item_votes(args)
            _print(f"按格号读到 0 票，自动改读条目票：{where}")
            return raw, where
        return items, f"{_live_where(args)}（{len(items)} 条）"
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


def _confirm_empty(args, where: str) -> dict:
    """``--allow-empty``：这张单确实没人投（殿本 21–99 册旧单，ZM 11-18）。只认刚从网站读全的结果：
    必须 ``--from-kv``（数据目录里的票文件可能是没同步的旧副本），按单版、按条目两种记法都读成功且这一章都是 0 条，
    且没有「条目找不到」被丢掉的票。读接口失败会直接抛错，走不到这里，所以守卫防的读票断连不会被放过去。"""
    if not _live(args) or getattr(args, "from_file", None):
        raise SystemExit(f"读到 0 票（{where}）：--allow-empty 只认 --from-kv／--from-inbox 当场读全的结果，不认票文件")
    n_rev = getattr(args, "_n_rev_raw", None)
    n_item = getattr(args, "_n_item_raw", None)
    if n_item is None:                                  # 按单版读到 0 条时会自动改读条目票；没走到就补读一次
        _item_votes(args)
        n_item = getattr(args, "_n_item_raw", None)
    lost = getattr(args, "_item_lost", 0)
    if n_rev is None:                                   # 一开始就按条目读（--items）：按单版也核一遍
        n_rev = len(_live_rev(args))
    if n_rev or n_item or lost:
        raise SystemExit(f"读到 0 条可用票，但网站上按单版 {n_rev or 0} 条、按条目 {n_item or 0} 条"
                         f"（条目找不到 {lost} 条）：不是零票，别用 --allow-empty")
    at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _print(f"确认零票：{args.site_book} {args.rev} 按单版 0 条、按条目 0 条（{at} 从网站读全），照出空草稿")
    return {"by_rev": 0, "by_item": 0, "read_at": at, "site": SITE}


def _split_old_sheet(book: str, rev: str, raw: list[dict], human: dict, items: dict | None = None, shown_now: dict | None = None) -> tuple[list[dict], list[tuple]]:
    """条目票里投在旧单上的（``vote_rev`` 不是现行单 ``rev``）拿出来，**图没变的**并回现行票，**图变了的**不写。

    ZM 11-19（v0.4.68）：vol01 r9／r15／r16 单上投的票，格号是当年的切分；拿现行包同号格的框建锚写成新事件，
    88:1:12a 写成「領」（现格图是保）。当时一律挡下旧单票。GM4 11-23（用户定「永远是新结果覆盖旧的」）：条目 id 按图块
    指纹认，条目还在、没有 ``fp_changed``（图没换）、没被人工撤下，它就还是读者当年看的那块图，票的含义没变，按条目**现格**落
    （``items`` 给了才判；票上记 ``_old_rev``，报告里分开数）。仍挡下、交人看的（特殊需要分析）：条目 ``fp_changed``、
    人工撤下、条目找不到。旧单票遇到更新的人裁不再跳过，同格同人后到的覆盖先到的（``latest_votes``）。
    返回 (现行单的票＋并回的旧单票, [(现格, 投票时格, 投票时单, 票, 当年人裁事件或 None, 挡下原因)])。"""
    cur, old = [], []
    for v in raw:
        vr = v.get("vote_rev")
        if not vr or vr == rev:
            cur.append(v)
            continue
        it = (items or {}).get(v.get("item") or "")
        why = ""
        if items is None:
            why = "旧单票（没给条目表，不判）"
        elif it is None:
            why = "条目找不到"
        elif it.get("fp_changed"):
            why = "条目 fp_changed（图块变了，需人看）"
        elif it.get("state") == "withdrawn":
            why = "条目被人工撤下"
        elif v.get("vote_a") and v.get("vote_a") != it.get("cell"):
            # ZM 11-23（vol01 职名页 11-20 改号后旧单条目票落到邻格）：条目现格≠投票时的格，说明这之间改过格号，
            # 条目存的格号不一定是换好的；没有对照表换号就不落，列进报告
            why = f"条目格号变过（投票时 {v.get('vote_a')}→现 {it.get('cell')}），要按对照表换号，不自动落"
        elif shown_now is not None and v.get("shown") and shown_now.get(it.get("cell")) not in (None, v["shown"]):
            why = f"页面显示字「{v['shown']}」≠现格现字「{shown_now[it['cell']]}」，格号对不上"
        if not why:
            cur.append({**v, "_old_rev": vr})
            continue
        e = human.get(f"{book}:{v.get('vote_a')}")
        tag = v.get("choice", "") + (("=" + v["char"]) if v.get("char") else "")
        old.append((v.get("a"), v.get("vote_a"), vr, tag, getattr(e, "id", None) if e is not None else None, why))
    return cur, old


def _bound_only(book: str, human: dict, votes: list[dict]) -> tuple[dict, list[tuple[str, str]]]:
    """``latest_human`` 里有票的格，只留在现行产物根（出单版包）上绑定有效、且就绑在这一格的人裁。

    ZM 11-19：vol02 75:7:11、vol18 33:4:7a／70:6:16 的旧人裁是迁移锚（``~q~r~r``），现行绑定不生效，格子照样上单待审；
    用户又投了同字，draft 判「与已有人裁一致」跳过，票就永远落不进去。绑不上的旧人裁在这里拿掉：同字票照写新事件
    （带新锚），推翻也不再算「推翻已有人裁」。只看有票的页（绑定按页缓存）。算不出绑定表时退回旧口径并醒目提示。
    返回 (过滤后的 human, [(格, 原因)])。"""
    from ._cv import bindings_usable, book_bindings
    pre = f"{book}:"
    voted = {v["a"] for v in votes if v.get("a")}
    cand = {k: e for k, e in human.items() if k.startswith(pre) and k[len(pre):] in voted}
    if not cand:
        return human, []
    pages = sorted({int(k[len(pre):].split(":")[0]) for k in cand})
    try:
        rows = book_bindings(book, pages=pages)
    except Exception as e:  # noqa: BLE001
        _print(f"⚠ 绑定表算不出来（{type(e).__name__}: {e}）：「与已有人裁一致」退回按格号判，迁移锚等没生效的旧人裁可能被误判一致；"
               f"先 guji db pull、确认产物根有 {book} 的 Step3 再重跑 draft")
        return human, []
    try:                                  # 定字人裁再按 seed_admit 的口径核（绑定之外还有撤库标记、被推翻、换图源 rev 不符）
        from ._cv import human_chars
        hc = human_chars(book)
    except Exception as e:  # noqa: BLE001
        _print(f"⚠ human_chars 算不出来（{type(e).__name__}: {e}）：只按绑定表核")
        hc = None
    from .charnorm import load_norm
    same = load_norm(book).same
    out, gone = dict(human), []
    for k, e in cand.items():
        r = rows.get(e.id)
        cell = bindings_usable(r, getattr(e, "ts", None))
        why = None
        if cell != k:
            why = f"{(r or {}).get('status', '无绑定')}" + (f"→{cell}" if cell else "")
        elif hc is not None and (e.payload or {}).get("shape") and (e.payload or {}).get("v") in ("confirm", "seg_defect"):
            got = hc.get(k)
            if got is None or not same(got, e.payload["shape"]):
                why = f"seed_admit 不采信（现行人裁字 {got or '无'}）"
        if why:
            out.pop(k)
            gone.append((k[len(pre):], why))
    return out, gone


def _ts_s(x) -> float:
    """票的 ts（网站毫秒时间戳）或事件的 ts（ISO 字符串）→ 秒。"""
    if isinstance(x, (int, float)):
        return x / 1000 if x > 1e11 else float(x)
    try:
        return dt.datetime.fromisoformat(str(x).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _yield_to_newer_human(book: str, votes: list[dict], human: dict) -> tuple[list[dict], list[tuple]]:
    """「按新的判定结果走」（用户 11-23）：票比这格现行人裁**早**（票的时间 < 人裁事件时间），票让位，不写、不推翻，
    只列进 ``stale_votes.tsv``（旧单上较早的票最常见）。票比人裁晚才照常走（一致跳过／推翻）。
    返回 (留下的票, [(格, 票, 票时间, 人裁事件, 人裁时间)])。"""
    keep, out = [], []
    for v in votes:
        e = human.get(f"{book}:{v['a']}")
        if e is not None and _ts_s(v.get("ts") or 0) < _ts_s(getattr(e, "ts", 0)):
            if v.get("choice") == "char" and v.get("char") and v["char"] == (getattr(e, "payload", None) or {}).get("shape"):
                continue                                  # 票的字就是现行人裁的字（多半是这票自己落的）：不冲突，不报
            tag = v.get("choice", "") + (("=" + v["char"]) if v.get("char") else "")
            out.append((v["a"], tag, str(v.get("ts")), getattr(e, "id", ""), str(getattr(e, "ts", ""))))
        else:
            keep.append(v)
    return keep, out


def cmd_draft(args) -> None:
    from ._cv import feedback_root
    from ._cv import EventLog
    from ._cv import latest_human, latest_votes, recheck_rows, triage
    pack_root = _use_pack(args.book, args.pack) if args.pack else None
    if not args.cord and not args.no_box_check and not pack_root:
        raise SystemExit("要给 --cord（出单那一版 book-text 的 <册>.cord.json）或 --pack（出单版产物包），或显式 --no-box-check")
    raw, where = _votes(args)
    human_all = latest_human(EventLog(feedback_root()).iter_all())
    item_tab = None
    if getattr(args, "items", False):
        from .review import pending_items as P
        item_tab = P.ItemStore.open(feedback_root().parent, args.site_book, args.rev.split("-r")[0]).items
    shown_now = None
    _sh = _sheet(args) if item_tab is not None else None
    if _sh:
        shown_now = {c["cell"]: (c.get("ref") or {}).get("c") for c in _sh.get("cells", []) if (c.get("ref") or {}).get("c")}
    raw, old = _split_old_sheet(args.book, args.rev, raw, human_all, item_tab, shown_now)
    n_old_in = sum(1 for v in raw if v.get("_old_rev"))
    if n_old_in:
        _print(f"旧单上投的条目票 {n_old_in} 条：条目图没变，按条目现格并入（永远新结果覆盖旧的）")
    if old:
        _print(f"旧单上投的条目票 {len(old)} 条仍挡下（图变了／撤下／找不到条目，需人看，见 old_sheet.tsv）："
               + "；".join(sorted({o[5] for o in old})))
    empty_ok = None
    if not raw and old:
        empty_ok = {"only_old_sheet": len(old)}
    elif not raw:
        if not getattr(args, "allow_empty", False):
            raise SystemExit(f"读到 0 票（{where}）：核对 --rev／--site-book／--items，别拿空草稿往下走"
                             f"（确实没人投、要照换单：加 --from-kv --allow-empty）")
        empty_ok = _confirm_empty(args, where)
    votes, dropped = latest_votes(raw, args.site_book, args.rev)
    from .feedback import landing_policy as LP
    policy = LP.get_policy(getattr(args, "policy", None))
    votes, waiting = LP.apply_policy(policy, votes)       # 落票策略：按审阅人身份决定自动落还是等多人（缺省 auto＝都落）
    if waiting:
        _print(f"落票策略 {policy.name}：{len(waiting)} 格没到门槛，不落（票留在收件箱，条目仍开着；见 waiting.tsv）")
    human = human_all
    human, unbound = _bound_only(args.book, human, votes) if not getattr(args, "no_bind_check", False) else (human, [])
    votes, stale = _yield_to_newer_human(args.book, votes, human)
    if stale:
        _print(f"票比现行人裁早 {len(stale)} 格：按新的判定结果走，票让位不写（见 stale_votes.tsv）")
    if unbound:
        _print(f"旧人裁在现行产物上没生效（绑定不是 valid／rebound 到本格）{len(unbound)} 格：不算「已有人裁」，这些格的票照写新事件"
               + "（" + "、".join(f"{a} {why}" for a, why in unbound[:8]) + ("…" if len(unbound) > 8 else "") + "）")
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
    with open(out / "old_sheet.tsv", "w", encoding="utf-8") as f:
        f.write("现格\t投票时格\t投票时单\t票\t当年人裁\t挡下原因\n")
        for row in old:
            f.write("\t".join(x or "" for x in row) + "\n")
    with open(out / "stale_votes.tsv", "w", encoding="utf-8") as f:
        f.write("格位\t票\t票时间\t现行人裁\t人裁时间\n")
        for row in stale:
            f.write("\t".join(row) + "\n")
    with open(out / "waiting.tsv", "w", encoding="utf-8") as f:
        f.write("格位\t原因\t票\n")
        for a_, why, vs in waiting:
            f.write(f"{a_}\t{why}\t" + "；".join(f"{v.get('voter')}:{v.get('choice')}{('=' + v['char']) if v.get('char') else ''}" for v in vs) + "\n")
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
            "dropped": dropped, "old_sheet": len(old), "old_landed": n_old_in,
            "policy": policy.name, "waiting": len(waiting), "stale_votes": len(stale), "ready": len(t.ready), "held": len(t.held), "skipped": t.skipped,
            **({"empty_confirmed": empty_ok} if empty_ok else {})}
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
    if not getattr(args, "no_cache_check", False):
        _check_patch_cache(args.book, rows)
    # 幂等键：同一份草稿重跑 write 不重复写（控制台写入路径按 payload.request_id 判重）
    rid = "cellvotes-" + hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    res = write_events(EventLog(feedback_root()), BatchStore(batches_root()), GoldStore(verdicts_root()),
                       ProductStore(None), batch=args.batch, step="seed_admit", unit="cell", kind="confirm",
                       events=rows, request_id=rid, consume=not args.no_consume, reviewer=args.reviewer)
    _print(json.dumps(res, ensure_ascii=False, indent=1))
    if args.no_consume and not res.get("duplicate"):
        _exclude_now(args.batch, rows)
    if meta.get("items") and not res.get("duplicate"):
        _resolve_items(meta, rows, res, args.reviewer or "")
    if not res.get("duplicate"):
        _print("已写进数据目录；推库：guji db sync -w <工作区>（写中心库前先报告、等点头）")


def _draft_pages(rows: list[dict]) -> list[int]:
    """草稿行 id 形如 `vol15:25:4:11a`（册:页:列:格），旧草稿可能不带册前缀（`25:4:11a`）；取页号，解析不了的跳过。"""
    out = set()
    for r in rows:
        parts = str(r.get("id") or "").split(":")
        pg = parts[1] if len(parts) == 4 else parts[0] if len(parts) == 3 else ""
        if pg.isdigit():
            out.add(int(pg))
    return sorted(out)


def _check_patch_cache(book: str, rows: list[dict]) -> None:
    """写人裁前核本地字块缓存是不是对着当前产物根切的（ZM 11-17 框架建议 2）。

    事件锚的内容指纹按本地 `char_patch` 缓存算；重切后换了产物根（出单版包）却没重建缓存，
    会**静默**写出指纹不符的锚（绑定 status=review，人裁不生效）。这里对草稿涉及的页跑
    `cache verify --fix`：有戳的页免查；查出错位就清掉这些页的缓存并拒写，提示先重建再写。
    引擎起不来（没有册配置、测试环境）只提示一句，不挡。"""
    pages = _draft_pages(rows)
    if not pages:
        return
    try:
        from ._cv import _engine, default_pipeline_id, load_book
        from .ops.cache_verify import verify_book
        eng = _engine(book, default_pipeline_id(load_book(book)), quiet=True)
        res = verify_book(eng, pages, fix=True, log=lambda *_: None)
    except Exception as e:                               # noqa: BLE001
        _print(f"（没核字块缓存：{type(e).__name__}: {e}；重切过的册写前请自己 `guji cache verify --book {book} --fix`）")
        return
    if res.get("bad_columns"):
        pg = ",".join(str(p) for p in res.get("bad_pages") or [])
        raise SystemExit(
            f"字块缓存与当前产物根对不上：{len(res.get('bad_pages') or [])} 页、{res['bad_columns']} 列（已清掉这些页的缓存）。\n"
            f"照这样写出的锚指纹会不符。先重建：guji cache warm --book {book} --pages {pg}（产物根同本次 write），"
            f"再重跑这条 write；确知无碍可加 --no-cache-check")


EXCLUDE_VS = ("figure", "not_a_char", "damaged")


def _exclude_now(batch: str, rows: list[dict]) -> None:
    """`--no-consume` 也要把图形／无字／破损票写进排除名单（只跑 `crop_exclude` 一个消费者）。

    名单才是「不进库、不再出审查卡」的执行者：以前 `--no-consume` 连它一起跳过，图形票落了事件，
    格子下一轮照样回待审单，用户在网站上又标一遍（ZM 11-16，019 的 5 格图形）。金标、产物失效等
    其余消费者仍按 `--no-consume` 不跑。"""
    if not any(r.get("v") in EXCLUDE_VS for r in rows):
        return
    from ._cv import EventLog, feedback_root
    from .feedback.consumers import route_and_consume
    out = route_and_consume(EventLog(feedback_root()), batch, only={"crop_exclude"})
    n = sum(r.get("added", 0) for r in out.get("results", []))
    errs = [x for r in out.get("results", []) for x in r.get("errors") or []]
    _print(f"排除名单（图形／无字／破损）：新增 {n} 格" + (f"；出错 {errs[:3]}" if errs else ""))
    if errs:
        raise SystemExit("✗ 写排除名单出错（事件已落，补跑：guji events route <批次>）")


def _resolve_items(meta: dict, rows: list[dict], res: dict, by: str) -> None:
    """落了票的条目标 resolved（待审条目化），并重导整张单。"""
    from ._cv import feedback_root
    from .review import pending_items as P
    data = feedback_root().parent
    store = P.ItemStore.open(data, meta["site_book"], meta["rev"].split("-r")[0])
    def cell(r: dict) -> str:
        # 草稿行（``Draft.row``）只有 ``id``（``vol04:15:8:20``），没有 ``a``：11-19 前这里只认 ``a``，条目一条都没结（ZM 收单要手工 pending resolve）
        return r.get("a") or P.norm_cell(r.get("id") or "")

    ids = dict(zip([cell(r) for r in rows], res.get("ids") or [None] * len(rows)))
    n = 0
    for r in rows:
        if not cell(r):
            continue
        hit = [x for x in store.find(cell(r)) if x["state"] in ("open", "withdrawn")]
        if hit:
            store.resolve(hit[0]["id"], by=by or "cellvotes", event=ids.get(cell(r)) or "", why=f"落票 {meta['rev']}")
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


def _kv_retry(fn, *a, tries: int = 4, reads: int = 3, wait: float = 5.0):
    """KV 管理读偶发 500／断连，翻页还会少回条目（11-21：殿本 001-r2 首读 10 条、重读 11 条；995ejelvk0 条目票
    两次都是 372 条但缺的不是同一票）：读 ``reads`` 遍成功的，按票身份取并集（同一票取后读到的）；失败的重试，
    总共最多 ``tries + reads`` 次。"""
    import time
    from .feedback import web_inbox as WI
    seen: dict[str, dict] = {}
    ok, err = 0, None
    for _ in range(tries + reads):
        try:
            got = fn(*a)
        except Exception as e:      # noqa: BLE001
            err = e
            time.sleep(wait)
            continue
        for v in got:
            seen[WI.vote_id(v)] = v
        ok += 1
        if ok >= reads:
            break
    if not ok:
        raise SystemExit(f"KV 管理读失败（试了 {tries + reads} 次）：{err}")
    return list(seen.values())


def cmd_reconcile(args) -> int:
    """双写对账（A20 11-21）：网站 KV 管理读 vs 中心库 web_inbox，逐票比。按条目的票全书比；按单版的票比 --rev 给的那张单
    （可逗号分隔多张）。只读。有差异退出码 1。两边都只看本书（``book`` 是 cv 册 id 时不用，只认 --site-book）。"""
    from .feedback import web_inbox as WI
    if not args.site_book:
        raise SystemExit("reconcile 要 --site-book")
    tok = _kv_token(args)
    rows, seq = WI.fetch("cellreview", args.site_book, token_env=getattr(args, "inbox_token_env", None))
    pairs = [("按条目", _kv_retry(_fetch_kv_items, args.site_book, tok), WI.item_votes(rows, args.site_book))]
    revs = [r.strip() for r in (args.rev or "").split(",") if r.strip()]
    if revs == ["all"]:                     # 收件箱里这本书出现过的每张单（含已过期、只剩墓碑的不算）
        revs = sorted(f[: -len(".jsonl")] for f in WI.rev_files(rows, args.site_book))
    for rev in revs:
        pairs.append((f"按单版 {rev}", _kv_retry(_fetch_kv, args.site_book, rev, tok), WI.rev_votes(rows, args.site_book, rev)))
    bad = 0
    _print(f"{args.site_book}：收件箱精校票 {len(rows)} 行（seq≤{seq}）")
    for name, kv, ib in pairs:
        d = WI.diff_votes(kv, ib)
        n = sum(len(v) for v in d.values())
        bad += n
        _print(f"- {name}：KV {len(kv)}，收件箱 {len(ib)}；只在 KV {len(d['only_kv'])}、只在收件箱 {len(d['only_inbox'])}、值不同 {len(d['differ'])}")
        for k in ("only_kv", "only_inbox", "differ"):
            for x in d[k][:10]:
                _print(f"    {k} {x}")
    _print("✓ 两边一致" if not bad else f"✗ 差 {bad} 票")
    if bad:
        raise SystemExit(1)
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("cellvotes", help="网站精校页投票 → 人裁事件：draft（只读出草稿）| write（写入并消费）| migrate（换图源迁票提案，只读）| rebase（页号不变的换图源：人裁锚换算提案，只读）")
    p.add_argument("action", choices=["draft", "write", "migrate", "rebase", "reconcile"])
    p.add_argument("book", help="cv 册 id，如 vol04")
    p.add_argument("dir", nargs="?", default=None, help="write：draft 的输出目录")
    p.add_argument("--site-book", help="draft：网站书 id，如 96mid1ogzk")
    p.add_argument("--rev", help="draft：待审单版本，如 004-r3")
    p.add_argument("--cord", default=None, help="draft：出单那一版 book-text 的 <册>.cord.json")
    p.add_argument("--policy", default=None, help="draft：落票策略（auto 缺省＝有票就落；quorum:N＝高等级一票即定、其余要 N 人同一结论；也读 GUJI_LANDING_POLICY）")
    p.add_argument("--no-box-check", action="store_true", help="draft：不核格位（自己担保产物没重切过）")
    p.add_argument("--no-bind-check", action="store_true",
                   help="draft：「与已有人裁一致」不核旧人裁在现行产物上的绑定（缺省核：绑不上的旧人裁不算已有，票照写）")
    p.add_argument("--pack", default=None, help="draft：出单版产物包标签（republish 存的 rev-<rev>），取回当产物根，免重跑")
    p.add_argument("--tol", type=float, default=8.0, help="draft：格框容差（像素，缺省 8）")
    p.add_argument("--sheet", default=None, help="draft：投票时的待审单（读 prior：复审格上有意推翻旧人裁）；"
                                                 "缺省数据目录里同 rev 的线上单")
    p.add_argument("--include-none", action="store_true", default=True, help="draft：「无字」也写（2026-11-10 起缺省就写，此项保留兼容）")
    p.add_argument("--no-none", dest="include_none", action="store_false", help="draft：「无字」票不写（挂起）")
    p.add_argument("--from", dest="from_file", default=None, help="draft：票从文件读")
    p.add_argument("--from-kv", action="store_true", help="draft：票直接管理读网站")
    p.add_argument("--from-inbox", action="store_true",
                   help="draft：票读中心库网站收件箱 web_inbox（GET /v1/web/inbox，网站 KV 与 D1 双写；读令牌 GUJI_DATA_TOKEN 等）")
    p.add_argument("--inbox-token-env", default=None, help="draft --from-inbox：读令牌的环境变量（缺省依次试 GUJI_DATA_TOKEN、_PROD、_READ）")
    p.add_argument("--allow-empty", action="store_true",
                   help="draft：确实没人投（0 票）也出空草稿，好照常换单；只认 --from-kv 当场读全、按单版和按条目都是 0 条")
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
    p.add_argument("--no-cache-check", action="store_true",
                   help="write：不核本地字块缓存（缺省对草稿涉及的页跑 cache verify --fix，缓存与产物根对不上就拒写）")


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
    elif args.action == "reconcile":
        cmd_reconcile(args)
    else:
        if not args.dir or not args.batch or not args.reviewer:
            _print("错误：write 要 <目录> --batch --reviewer（缺：" + "、".join(
                n for n, v in (("<目录>", args.dir), ("--batch", args.batch), ("--reviewer", args.reviewer)) if not v) + "）")
            raise SystemExit(2)         # 非零退出码，脚本里别把一行用法当成功
        cmd_write(args)


#: 并进 `guji` 的子命令（同插件接口 `guji.commands`；cv 侧由 `cli_v2.MANAGER_CLI_MODULES` 登记，拆分 P1）
COMMANDS = {"cellvotes": (add_parser, cmd_cellvotes)}
