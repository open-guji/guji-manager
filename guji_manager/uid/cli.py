"""`guji uid …`：字格身份账（字格永久编号 u）。格式与口径见 `doc/参考/字格身份账.md`。

    guji uid advance vol31 [-w <工作区>] [--products <产物根>] [--pages 1-20,33] [--dry-run]
                                     # 切字后入账：现行产物每页的切分 cells_sha 与账不同就入一行（同一份重跑不动）
    guji uid init vol31 --from-book-text <book-text 仓> --text-id <书 ID> [--edition default] [--with-products]
    guji uid init vol31 --char 031.char.json --cord 031.cord.json   # 直接给文件
                                     # 用现行 book-text 建第一份账：char 带 u（v0.6）就照抄，不带按读序 1..N
    guji uid show vol31 [--page 12] [--cell vol31:12:3:4 | --u 1234] [--json]
    guji uid verify vol31 [--products …]   # 账自洽；给了产物再核每页现行切分都入了账
    guji uid table vol31 [--pages …] [-o 格级表.tsv]   # 账上「上一份切分→当前切分」出 old_new_cells 同格式的格级表
                                     # （给 cellvotes migrate、ops cell-rekey、swap 用，不再另跑框 IoU；T2）
    guji uid migrate-plan vol31 -o <目录> [--items <章>.items.jsonl …]
                                     # 存量裁定／人裁／待审条目配 u 的**提案**（不写库）：rulings.jsonl、human.jsonl、
                                     # items.jsonl、清单.tsv、守恒.json（T2，口径见 guji_manager/u_migrate.py）
    guji uid web-backfill vol28 --ws siku-zongmu --site-book 96mid1ogzk --site-vol 028 -o <目录> [--write]
                                     # 中心库 web_inbox 里没带 u 的网站旧票（精校票、改字意见）按账补 u（只补字段、换新 seq）；
                                     # 账读中心库 events（stream=uid）。口径见 guji_manager/u_web_backfill.py

`guji pipeline` 跑完、该册已有账时自动 advance（`hooks.finished`），一般不用手跑。
写账只写本地数据目录 `<feedback>/uid/`；推中心库另跑 `guji db sync`。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path


def _pages(spec: str | None) -> list[int] | None:
    if not spec:
        return None
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out += range(int(a), int(b) + 1)
        elif part:
            out.append(int(part))
    return out


def _store(a):
    from .._cv import ProductStore
    return ProductStore(Path(a.products)) if getattr(a, "products", None) else ProductStore()


def _ws(a) -> None:
    if getattr(a, "workspace", None):
        os.environ["GUJI_WORKSPACE"] = str(Path(a.workspace).resolve())


def _print(d, as_json: bool = True) -> None:
    print(json.dumps(d, ensure_ascii=False, indent=None if as_json else 1))


def cmd_advance(a) -> None:
    from . import advance
    _ws(a)
    bt = "auto"
    if a.no_book_text:
        bt = None
    elif a.book_text:
        from . import booktext
        bt = booktext.load(a.book, repo=a.book_text)
        if bt is None:
            sys.exit(f"✗ {a.book_text} 里找不到 {a.book} 的 char.json（书 id／章号按册配置）")
    r = advance(a.book, _store(a), _pages(a.pages), dry_run=a.dry_run, force=a.force, booktext=bt)
    _print(r)


def cmd_init(a) -> None:
    from . import init_from_book_text
    from .source import load_json
    _ws(a)
    if a.char:
        char = load_json(a.char)
        cord = load_json(a.cord) if a.cord else None
    elif a.from_book_text:
        if not a.text_id:
            sys.exit("--from-book-text 要给 --text-id <书 ID>")
        from ..online_lists import book_text_dir
        from ..swap import chapter_of
        d = Path(book_text_dir(a.from_book_text, a.text_id)) / a.edition
        ch = a.chapter or chapter_of(a.book)
        char = load_json(d / f"{ch}.char.json")
        cp = d / f"{ch}.cord.json"
        cord = load_json(cp) if cp.exists() else None
    else:
        sys.exit("要给 --from-book-text <仓> --text-id <书 ID>，或 --char <文件>")
    if cord is None:
        print("⚠ 没有 cord：账里不带框，之后 advance 只能按字序列对照", file=sys.stderr)
    store = _store(a) if a.with_products else None
    _print(init_from_book_text(a.book, char, cord, dry_run=a.dry_run, store=store))


def retire_into_line(led, pairs: list[tuple[int, int]], *, why: str = "", by: str | None = None) -> tuple[dict | None, list[str]]:
    """并账记录：旧 u（须已作废、不在现行账里）→ 新 u（须在现行账里）。写成册级一行（page=0、map 空、lineage 记 into），
    不动各页的「上一份／当前一份」（换单对照表照旧按页配对）。``retired()`` 取最后一次记的，所以会盖过原先的 gone。
    → (账行或 None, 问题)。"""
    from .ledger import make_line
    cur = set(led.current().values())
    ret = led.retired()
    probs, lin = [], []
    for old, new in pairs:
        if old in cur:
            probs.append(f"u{old} 还在现行账里（{led.cell_of(old)}），不能并")
        elif old not in ret and old > led.u_max():
            probs.append(f"u{old} 账里没发过")
        elif new not in cur:
            probs.append(f"u{new} 不在现行账里")
        elif ret.get(old, {}).get("into") == new:
            probs.append(f"u{old} 已并入 u{new}（不用再记）")
        else:
            lin.append({"u": old, "into": new, "was": "gone" if ret.get(old, {}).get("gone") else
                        (f"into:{ret[old]['into']}" if old in ret else "untracked")})
    if not lin:
        return None, probs
    d = make_line(led.book, 0, None, {}, lineage=lin, src="retire-into", by=by,
                  via={"retire_into": len(lin)})
    d["id"] = d["id"] + "-ri" + "-".join(str(x["u"]) for x in lin)[:40]
    if why:
        d["why"] = why
    return d, probs


def cmd_retire_into(a) -> None:
    from .ledger import Ledger, verify
    _ws(a)
    led = Ledger.load(a.book)
    if not led.exists:
        sys.exit(f"✗ {a.book} 没有字格身份账")
    try:
        pairs = [tuple(int(x) for x in p.split(":")) for p in a.pairs]
    except ValueError:
        sys.exit("✗ 参数写成 旧u:新u，如 26626:34455")
    d, probs = retire_into_line(led, pairs, why=a.why)
    for p in probs:
        print(f"⚠ {p}", file=sys.stderr)
    if d is None:
        sys.exit(1 if probs else 0)
    for x in d["lineage"]:
        print(f"u{x['u']}（原 {x['was']}）→ 并入 u{x['into']}（现 {led.cell_of(x['into'])}）")
    if not a.write:
        print("（干跑；加 --write 真写）")
        return
    led.append([d])
    errs = verify(Ledger.load(a.book))
    print(json.dumps({"写": 1, "并": len(d["lineage"]), "verify": errs[:5]}, ensure_ascii=False))
    if errs:
        sys.exit(1)


def revive_line(led, u: int, cell: str, *, box: list | None = None, char: str | None = None,
                why: str = "", by: str | None = None) -> tuple[dict | None, list[str]]:
    """复活：已作废（gone）的 u 回到 ``cell``（新切分漏切了这格，看图确认后人工补回）。抄这一页现行最后一行
    （cells_sha 不变，cv 照旧按它找行），map 里插入这格（按读序），lineage 记 ``{u, revived: true}``；
    ``retired()`` 遇 revived 把它从作废号里拿掉。→ (账行或 None, 问题)。"""
    from .ledger import _CELL, make_line
    full = cell if cell.startswith(led.book + ":") else f"{led.book}:{cell}"
    m = _CELL.match(full)
    probs: list[str] = []
    if not m:
        return None, [f"不是格号：{cell}"]
    page = int(m["page"])
    cur, ret = led.current(), led.retired()
    if u in cur.values():
        probs.append(f"u{u} 还在现行账里（{led.cell_of(u)}），不用复活")
    elif u > led.u_max():
        probs.append(f"u{u} 账里没发过")
    elif u not in ret:
        probs.append(f"u{u} 没记作废")
    elif "into" in ret[u]:
        probs.append(f"u{u} 已并入 u{ret[u]['into']}，要先确认不是同一格；复活只收 gone 的")
    if full in cur:
        probs.append(f"{full} 现行已有 u{cur[full]}")
    last = led.page(page)
    if last is None:
        probs.append(f"第 {page} 页没有账行")
    if probs:
        return None, probs

    def key(k):
        x = _CELL.match(k)
        return (int(x["col"]), int(x["slot"]), x["sub"])
    umap = dict(sorted({**last["map"], full: int(u)}.items(), key=lambda kv: key(kv[0])))
    boxes = dict(last.get("boxes") or {})
    if box:
        boxes[full] = list(box)
    chars = dict(last.get("chars") or {})
    if char:
        chars[full] = char
    d = make_line(led.book, page, last.get("cells_sha"), umap, boxes=boxes or None, chars=chars or None,
                  lineage=[{"u": int(u), "revived": True, "cell": full}], src="revive", by=by,
                  via={"revive": 1, "from": last["id"]})
    if why:
        d["why"] = why
    return d, []


def cmd_revive(a) -> None:
    from .ledger import Ledger, verify
    _ws(a)
    led = Ledger.load(a.book)
    if not led.exists:
        sys.exit(f"✗ {a.book} 没有字格身份账")
    try:
        u, cell = a.target.split(":", 1)
        u = int(u)
        box = [int(x) for x in a.box.split(",")] if a.box else None
    except ValueError:
        sys.exit("✗ 参数写成 u:页:列:格，如 37207:229:1:1；--box 写 x,y,w,h")
    d, probs = revive_line(led, u, cell, box=box, char=a.char, why=a.why)
    for p in probs:
        print(f"⚠ {p}", file=sys.stderr)
    if d is None:
        sys.exit(1)
    print(f"u{u} 复活到 {d['lineage'][0]['cell']}（第 {d['page']} 页，cells_sha 同现行行 {d['cells_sha']}）")
    if not a.write:
        print("（干跑；加 --write 真写）")
        return
    led.append([d])
    errs = verify(Ledger.load(a.book))
    print(json.dumps({"写": 1, "verify": errs[:5]}, ensure_ascii=False))
    if errs:
        sys.exit(1)


def cmd_show(a) -> None:
    from .ledger import Ledger
    _ws(a)
    led = Ledger.load(a.book)
    if not led.exists:
        sys.exit(f"{led.path}：没有账（{a.book} 还没启用 u）")
    if a.cell:
        from .ledger import parse_cell
        _, pg = parse_cell(a.cell)
        u = (led.page(pg) or {}).get("map", {}).get(a.cell)
        _print({"cell": a.cell, "u": u, "history": led.history(u) if u else []})
        return
    if a.u is not None:
        _print({"u": a.u, "cell": led.cell_of(a.u), "retired": led.retired().get(a.u), "history": led.history(a.u)})
        return
    if a.page is not None:
        prev, cur = led.page_pair(a.page)
        if cur is None:
            sys.exit(f"第 {a.page} 页没有入账")
        if a.json:
            _print(cur)
            return
        print(f"{a.book} 第 {a.page} 页：入账 {sum(1 for d in led.lines if int(d['page']) == a.page)} 次，现行 {cur['id']}"
              f"（{cur.get('src')}，{cur.get('ts')}，cells_sha={cur.get('cells_sha')}）")
        print(f"  {len(cur['map'])} 格；本次 {json.dumps(cur.get('via') or {}, ensure_ascii=False)}")
        for k, v in cur["map"].items():
            print(f"  {k}\t{v}\t{(cur.get('chars') or {}).get(k, '')}")
        for x in cur.get("lineage") or []:
            if not x.get("new"):
                print(f"  谱系 {json.dumps(x, ensure_ascii=False)}")
        return
    lat = led.latest()
    pages = [p for p in lat if p > 0]
    out = {"book": a.book, "path": str(led.path), "lines": len(led.lines), "pages": len(pages),
           "cells": sum(len(lat[p]["map"]) for p in pages), "u_max": led.u_max(), "retired": len(led.retired()),
           "no_cells_sha": sum(1 for p in pages if not lat[p].get("cells_sha"))}
    _print(out)


def cmd_verify(a) -> None:
    from .ledger import Ledger, verify
    _ws(a)
    led = Ledger.load(a.book)
    if not led.exists:
        sys.exit(f"{led.path}：没有账")
    errs = verify(led)
    if a.products or a.check_products:
        from . import source
        store = _store(a)
        pages = _pages(a.pages) or source.product_pages(store, a.book)
        for pg in pages:
            sha = source.cells_sha(store, a.book, pg)
            if sha and led.by_sha(pg, sha) is None:
                errs.append(f"第 {pg} 页现行切分（cells_sha {sha[:12]}…）没入账")
    for e in errs:
        print(f"✗ {e}")
    print(f"{a.book}：{len(led.lines)} 行，u_max={led.u_max()}，问题 {len(errs)} 条", file=sys.stderr)
    if errs:
        sys.exit(1)


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("uid", help="字格身份账（字格永久编号 u）：advance／init／show／verify")
    s = p.add_subparsers(dest="uid_cmd", required=True)

    def common(q, products=True):
        q.add_argument("book", help="册（如 vol31）")
        q.add_argument("-w", "--workspace", default=None, help="工作区（定 feedback 根；缺省 GUJI_WORKSPACE）")
        if products:
            q.add_argument("--products", default=None, help="产物根（缺省按工作区）")

    q = s.add_parser("sync", help="把 main 包（缺省现行 main）的切分入账并推中心库：标 main 钩子漏了时补，执行机／自检也用它")
    common(q)
    q.add_argument("--label", default=None, help="包标签（缺省现行 main）")
    q.add_argument("--local", action="store_true", help="用本机现行产物（已铺好这份包），不另取")
    q.add_argument("--no-push", action="store_true", help="只入本机账，不拉不推中心库")
    q.add_argument("--reconfirm", action="store_true", help="这个包已对过账也再记一笔带时间的（重标 main 后自检才不报缺）")

    q = s.add_parser("audit", help="自检：有账的书每册现行 main 包入过账没有；--submit 给缺的交 uidsync 单")
    q.add_argument("--submit", action="store_true", help="给缺的册交 uidsync 单（同册同标签只跑一次）")
    q.add_argument("--cv", default=None, help="uidsync 单用哪版 cv（缺省按册用产出 main 包的那版，解析不出退回 main）")

    q = s.add_parser("advance", help="切字后入账（同一份切分重跑不动）")
    common(q)
    q.add_argument("--pages", default=None, help="只入这些页（如 1-20,33）")
    q.add_argument("--dry-run", action="store_true", help="只算不写")
    q.add_argument("--force", action="store_true", help="cells_sha 没变也重入一行")
    q.add_argument("--book-text", default=None, metavar="仓",
                   help="参考这份 book-text 已发的号（缺省按 GUJI_BOOK_TEXT 找，找不到就不参考）")
    q.add_argument("--no-book-text", action="store_true", help="不参考 book-text，只看账")

    q = s.add_parser("init", help="用 book-text 现行 char＋cord 建第一份账")
    common(q)
    q.add_argument("--from-book-text", default=None, metavar="仓", help="book-text 仓目录")
    q.add_argument("--text-id", default=None, help="书 ID（如 96mid1ogzk）")
    q.add_argument("--edition", default="default", help="版本目录（缺省 default）")
    q.add_argument("--chapter", default=None, help="章号（缺省按册号三位）")
    q.add_argument("--char", default=None, help="直接给 char.json")
    q.add_argument("--cord", default=None, help="直接给 cord.json")
    q.add_argument("--with-products", action="store_true",
                   help="对上现行产物：某页格号集合与 char 一致就记该页 cells_sha（cv 能直接用这一行）")
    q.add_argument("--dry-run", action="store_true")

    q = s.add_parser("retire-into", help="并账：已作废（gone）的旧 u 改记为并进现行某格的 u（重切后同一格换了号、自动没认上时用；缺省只报）")
    q.add_argument("book", help="cv 册（如 vol16）")
    q.add_argument("pairs", nargs="+", metavar="旧u:新u", help="如 26626:34455（可多对）")
    q.add_argument("--why", default="", help="说明（看图确认等），记进账行")
    q.add_argument("--write", action="store_true", help="真写（只追加一行册级记录 page=0）；推库另跑 db push --only feedback/uid/<册>.jsonl")
    q.add_argument("-w", "--workspace", default=None)

    q = s.add_parser("revive", help="复活：已作废（gone）的 u 回到原格（新切分漏切了这格、看图确认后人工补回；缺省只报）")
    q.add_argument("book", help="cv 册（如 vol20）")
    q.add_argument("target", metavar="u:页:列:格", help="如 37207:229:1:1")
    q.add_argument("--box", default=None, help="这格的框 x,y,w,h（cord 空间，可取旧 cord）")
    q.add_argument("--char", default=None, help="这格的字（记进账行 chars，字序列兜底用）")
    q.add_argument("--why", default="", help="说明（看图确认等），记进账行")
    q.add_argument("--write", action="store_true", help="真写（追加该页一行）；推库另跑 db push --only feedback/uid/<册>.jsonl")
    q.add_argument("-w", "--workspace", default=None)

    q = s.add_parser("show", help="看账：全册概况／一页／一格／一个 u 的来历")
    common(q, products=False)
    q.add_argument("--page", type=int, default=None)
    q.add_argument("--cell", default=None, help="完整格号（册:页:列:格）")
    q.add_argument("--u", type=int, default=None)
    q.add_argument("--json", action="store_true")

    q = s.add_parser("verify", help="核账自洽；--check-products 再核现行切分都入了账")
    common(q)
    q.add_argument("--check-products", action="store_true")
    q.add_argument("--pages", default=None)

    q = s.add_parser("table", help="账上「上一份切分→当前切分」出格级对照表（old_new_cells 同格式）")
    common(q, products=False)
    q.add_argument("--pages", default=None)
    q.add_argument("-o", "--out", default=None, help="写到文件（缺省打到 stdout）")

    q = s.add_parser("migrate-plan", help="存量裁定／人裁／待审条目配 u 的提案（只出文件，不写库）")
    common(q, products=False)
    q.add_argument("-o", "--out", required=True, help="输出目录")
    q.add_argument("--items", nargs="*", default=None, help="待审条目文件（<数据目录>/feedback/lists/pending/<书>/<章>.items.jsonl）")
    q.add_argument("--write", action="store_true",
                   help="真写本地数据目录（只追加）：裁定、人裁各抄一条带 u 的（id、批次加 ~u，ts、seq 不变）；待审条目追加补 u 的新版本。"
                        "推中心库另跑 guji db push --only（写入.json 列了文件）")
    q.add_argument("--close", action="store_true",
                   help="收口（u_migrate.rescue_human／close_out）：清单上的人裁按异体、列内近邻同字再救一批；其余裁定、人裁作废记档"
                        "（feedback/lists/u_void/<册>.jsonl，原事件不动），字不同的人裁转待审条目（recheck），格号不在账的条目撤下。出 收口.tsv／收口.json")
    q.add_argument("--review-items", default=None, help="转待审的条目写进哪个文件（缺省 --items 第一个）")
    q.add_argument("--bind-products", default=None,
                   help="收口先用 cv 绑定认格（book_bindings）读哪份产物（现行 main 包的目录；缺省工作区产物）")
    q.add_argument("--no-bind", action="store_true", help="收口不跑 cv 绑定认格（没装 cv／没产物时）")

    q = s.add_parser("tidy-recheck", help="u 迁移转待审的条目：同格并成一条、补候选字（现行字＋旧人裁字＋票字）")
    q.add_argument("book", help="cv 册（读身份账取现行字）")
    q.add_argument("--items", nargs="+", required=True, help="条目文件")
    q.add_argument("--write", action="store_true", help="真写（只追加新版本）；缺省只报数")
    q.add_argument("-w", "--workspace", default=None)

    q = s.add_parser("stamp", help="事件文件里册有账却没带 u 的行就地补 u（只补锚在同一份切分上的；推库闸拦下时用，缺省只报）")
    q.add_argument("files", nargs="+", help="事件文件（feedback/events/*.jsonl、feedback/rulings/*.jsonl）")
    q.add_argument("--write", action="store_true", help="真改文件（只给没带 u 的行加 u，别的行逐字节不动）")
    q.add_argument("-w", "--workspace", default=None)

    q = s.add_parser("check-u", help="自检：有账册每格最新人裁没 u、也没记作废／转待审的；~u 人裁抄件缺补锚档的（都应为 0；有则退出码 1）")
    q.add_argument("books", nargs="*", help="册（缺省：事件里出现的、有账的全部册）")
    q.add_argument("-o", "--out", default=None, help="清单写到这个 tsv")
    q.add_argument("-v", "--verbose", action="store_true", help="0 的册也列")
    q.add_argument("-w", "--workspace", default=None)

    q = s.add_parser("items-u", help="待审条目活着却没 u 的按身份账补 u（缺省只报；--write 追加 op=u-fill 一版）")
    q.add_argument("books", nargs="*", help="册（缺省：有账的全部册）")
    q.add_argument("--write", action="store_true")
    q.add_argument("-w", "--workspace", default=None)

    q = s.add_parser("anchor-fill", help="~u 人裁抄件补锚档：原件有档的照抄；无框无档的按身份账取 u 在现行切分的框（缺省只报数）")
    q.add_argument("books", nargs="*", help="册（缺省：有 ~u 抄件的全部册）")
    q.add_argument("--write", action="store_true", help="真写 feedback/anchors/<册>.jsonl（只追加）")
    q.add_argument("-o", "--out", default=None, help="补不了的清单（jsonl）")
    q.add_argument("-w", "--workspace", default=None)

    q = s.add_parser("check-u-report", help="本机各工作区跑 check-u，非 0 通知 CV0 和该书项目（只报不改；执行方定时用）")
    q.add_argument("--roots", nargs="+", default=None, help="找工作区的根目录（缺省 ~ 与当前目录）")
    q.add_argument("--notify", action="store_true", help="非 0 且和上次不同就发通知")

    q = s.add_parser("web-backfill", help="网站旧票（web_inbox 精校票、改字意见）按账补 u（缺省只出提案）")
    q.add_argument("book", help="cv 册（如 vol28）")
    q.add_argument("--ws", required=True, help="中心库工作区（如 siku-zongmu）")
    q.add_argument("--site-book", required=True, help="网站书 ID（如 96mid1ogzk）")
    q.add_argument("--site-vol", required=True, help="网站册号（票上的 vol／volume，如 028）")
    q.add_argument("--branch", default="main", help="中心库分支（缺省 main）")
    q.add_argument("-o", "--out", required=True, help="输出目录：配上.jsonl、清单.tsv、结果.json")
    q.add_argument("--write", action="store_true", help="真写中心库 web_inbox（只补 u 字段、换新 seq；写前先记 D1 时间旅行书签）")


def cmd_table(a) -> None:
    from collections import Counter

    from ..u_table import table_rows, to_tsv
    from .ledger import Ledger
    _ws(a)
    led = Ledger.load(a.book)
    if not led.exists:
        sys.exit(f"✗ {a.book} 没有字格身份账")
    rows = table_rows(led, _pages(a.pages))
    txt = to_tsv(rows)
    if a.out:
        Path(a.out).write_text(txt, encoding="utf-8")
        print(json.dumps({"rows": len(rows), **Counter(r["类别"] for r in rows), "out": a.out}, ensure_ascii=False),
              file=sys.stderr)
    else:
        sys.stdout.write(txt)


def _cv_bound(book: str, products: str | None) -> dict[str, str]:
    """cv 绑定（book_bindings → usable）：{事件 id: 现格号}。跑不了（没装 cv、没产物）就报一行、返回空（收口照旧）。"""
    try:
        from .._cv import EventLog, ProductStore, bindings_usable, book_bindings
        rows = book_bindings(book, log=EventLog(), store=ProductStore(Path(products)) if products else None, refresh=True)
    except Exception as ex:                 # noqa: BLE001
        print(f"⚠ cv 绑定认格没跑成（{type(ex).__name__}: {ex}），收口不用这一步", file=sys.stderr)
        return {}
    out = {}
    for eid, row in rows.items():
        cell = bindings_usable(row)
        if cell:
            out[eid] = cell
    return out


def cmd_migrate_plan(a) -> None:
    from .. import u_migrate as M
    from .._cv import RULING_KIND, EventLog, RulingStore, replay_key
    from ..feedback.levels import counts_as_pin
    from ..feedback.web_votes import HUMAN_VS
    from .ledger import Ledger
    _ws(a)
    led = Ledger.load(a.book)
    if not led.exists:
        sys.exit(f"✗ {a.book} 没有字格身份账，先 guji uid init／advance")
    pre = f"{a.book}:"
    rul: dict[str, dict] = {}
    rul_ev: dict[str, object] = {}
    hum_ev: dict[str, object] = {}
    store = RulingStore()
    if store.log.events_dir.exists():
        for e in sorted((e for e in store.log.iter_all(raw=True) if e.kind == RULING_KIND), key=replay_key):
            p = e.payload or {}
            if str(p.get("cell") or "").startswith(pre):
                rul[p["cell"]] = p
                rul_ev[p["cell"]] = e
    hum: dict[str, dict] = {}
    log = EventLog()
    # 收口时记过作废／转待审的（u_void）不再配 u：重跑 migrate-plan 不把作废的旧裁定、人裁抄回来（史記 08，11-26）
    voided, rul_void = M.void_ids(log, a.book)
    def _iso(t) -> str:
        return t.strftime("%Y-%m-%dT%H:%M:%SZ") if hasattr(t, "strftime") else str(t)
    for c in [c for c, e in rul_ev.items() if e.id in voided or _iso(e.ts) <= rul_void.get(c, "")]:
        rul.pop(c, None)
        rul_ev.pop(c, None)
    raw = [e for e in log.iter_all(raw=True) if M.is_human_cell(e, HUMAN_VS, counts_as_pin)]
    gated = {e.id for e in log.iter_all() if M.is_human_cell(e, HUMAN_VS, counts_as_pin)}
    for e in sorted((e for e in raw if e.id in gated), key=lambda e: (e.ts, e.batch, e.seq)):
        t = e.target
        if not str(t.key).startswith(pre):
            continue
        an = t.anchor or {}
        if e.id in voided:
            hum.pop(t.key, None)
            continue
        hum[t.key] = {"id": e.id, "cell": t.key, "shape": (e.payload or {}).get("shape"),
                      "reading": (e.payload or {}).get("reading"),
                      "cells_sha": an.get("cells_sha"), "u": an.get("u")}
        hum_ev[e.id] = e
    # 页表 rev 闸挡掉的（换图源前的旧事件，cv 不采信；换算件 ~r 另挂在新格号上）：每格最新的是它、又没 u → 作废记档
    rev_void = [{"stream": "events", "id": e.id, "key": k,
                 "reason": "页表 rev 不符（换图源前的旧事件，cv 本就不采信；换算件另挂新格号）"}
                for k, e in M.latest_by_key(raw, pre).items()
                if e.id not in gated and not isinstance((e.target.anchor or {}).get("u"), int)]
    items = []
    for f in a.items or []:
        cur: dict[str, dict] = {}
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                cur[r["id"]] = r
        items += [{**r, "_file": f} for r in cur.values() if r.get("state") != "closed"]
    from ..charnorm import load_norm
    res = M.plan(led, rulings=list(rul.values()), humans=list(hum.values()), items=items, same=load_norm(a.book).same)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name in ("rulings", "human", "items"):
        with open(out / f"{name}.jsonl", "w", encoding="utf-8") as fh:
            for x in res[name]:
                fh.write(json.dumps(x, ensure_ascii=False) + "\n")
    with open(out / "清单.tsv", "w", encoding="utf-8") as fh:
        fh.write("类别\t键\t理由\n")
        for x in res["清单"]:
            fh.write(f"{x['类别']}\t{x['键']}\t{x['理由']}\n")
    (out / "守恒.json").write_text(json.dumps({"守恒": res["守恒"], "裁定迁出方式": res["迁出方式"], "人裁迁出方式": res["人裁迁出方式"]},
                                             ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"守恒": res["守恒"], "裁定迁出方式": res["迁出方式"], "人裁迁出方式": res["人裁迁出方式"], "out": str(out)}, ensure_ascii=False))
    co = rescued = None
    if a.close:
        from .._cv import variant_group
        vg: dict = {}

        def variant(x, y):
            if not x or not y or x == y:
                return False
            if x not in vg:
                vg[x] = variant_group(x)
            return y in vg[x]
        taken = {int(h["u"]) for h in hum.values() if h.get("u") is not None} | {int(x["u"]) for x in res["human"]}
        # ⓪ 先用 cv 绑定认格：「格号不在账」「字不同、切分变过」的人裁多是整列平移，cv 按锚框顺移绑对了（11-26 救回 61 格）
        bound = {} if a.no_bind else _cv_bound(a.book, a.bind_products)
        by_bind, left = M.bind_rescue(led, res["清单"], bound, same=load_norm(a.book).same, variant=variant, taken=taken)
        rescued, rest = M.rescue_human(led, left, same=load_norm(a.book).same, variant=variant,
                                       taken=taken | {int(x["u"]) for x in by_bind})
        rescued = by_bind + rescued
        co = M.close_out(led, rest, human_u=taken | {int(x["u"]) for x in rescued})
        co["void"] += rev_void
        summ = {"人裁救回": dict(Counter(x["how"] for x in rescued)), "作废": dict(Counter(v["stream"] for v in co["void"])),
                "转待审": len(co["review"]), "撤下": len(co["withdraw"])}
        with open(out / "收口.tsv", "w", encoding="utf-8") as fh:
            fh.write("去向\t类别\t键\t理由\n")
            for x in rescued:
                fh.write(f"救回\t人裁\t{x['cell']}\t{x['how']} → u{x['u']}{'（现 ' + x['now'] + '）' if x.get('now') else ''}\n")
            for v in co["void"]:
                fh.write(f"作废\t{'裁定' if v['stream'] == 'rulings' else '人裁'}\t{v['key']}\t{v['reason']}\n")
            for r in co["review"]:
                fh.write(f"转待审\t人裁\t{r['cell']}\t{r['detail']}\n")
            for w_ in co["withdraw"]:
                fh.write(f"撤下\t待审条目\t{w_['id']}\t{w_['reason']}\n")
        (out / "收口.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"收口": summ}, ensure_ascii=False))
    if a.write:
        M.check_close_inputs(co, a.review_items or ((a.items or [None])[0]))      # 先核再写：别写一半才报错
        w = M.apply(res, ruling_events=rul_ev, human_events=hum_ev, ruling_log=store.log, event_log=EventLog())
        if co is not None:
            c = M.write_close(a.book, co, rescued=rescued, unscreened=w["裁定没抄"], human_events=hum_ev,
                              event_log=EventLog(), review_file=a.review_items or ((a.items or [None])[0]))
            w["收口"] = {k: v for k, v in c.items() if k != "files"}
            w["files"] = sorted(set(w["files"]) | set(c["files"]))
        (out / "写入.json").write_text(json.dumps(w, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"写入": w}, ensure_ascii=False))


def cmd_web_backfill(a) -> None:
    from .. import u_web_backfill as B
    from ..charnorm import load_norm
    from ..datastore.connect import connect
    conn = connect(branch=a.branch)
    led = B.load_ledger(conn, a.ws, a.book)
    if not led.exists:
        sys.exit(f"✗ 中心库没有 {a.ws}/{a.book} 的字格身份账")
    try:
        same = load_norm(a.book).same
    except Exception:                       # 没装 cv、读不到书配置：退化成 ==
        same = None
    rows = B.load_votes(conn, a.site_book, a.site_vol)
    res = B.plan_rows(B.Resolver(led, same), rows, B.load_vote_events(conn, a.ws, a.book))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "配上.jsonl", "w", encoding="utf-8") as fh:
        for f in res["fills"]:
            fh.write(json.dumps({k: f[k] for k in ("kind", "key", "格", "set", "how")}, ensure_ascii=False) + "\n")
    with open(out / "清单.tsv", "w", encoding="utf-8") as fh:
        fh.write("类别\t键\t格\t理由\n")
        for x in res["清单"]:
            fh.write(f"{x['kind']}\t{x['key']}\t{x['格']}\t{x['理由']}\n")
    summ = {"册": a.book, "网站": f"{a.site_book}/{a.site_vol}", "守恒": res["守恒"], "方式": res["方式"],
            "配上的u已作废": res["配上的u已作废"]}
    if a.write:
        summ["写"] = B.apply(conn, res["fills"])
    (out / "结果.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    _print(summ)


def stamp_lines(lines: list[str], ledger_of) -> tuple[list[str], list[dict], list[dict]]:
    """一个事件文件的各行 → (新各行, 补上 [{id, cell, u}], 补不上 [{id, cell, why}])。

    只补「锚在同一份切分上」的：人裁锚 `cells_sha` 主段＝账上该页某行主段（`u_migrate.plan_human` 的「锚同切分」），
    裁定 `payload.cells_sha` 命中账行（`plan_rulings` 的「直接」）。别的（锚是旧切分、没锚）不猜，列出来交
    `guji uid migrate-plan`。没带 u 的判定同推库闸（`u_stamp.lacks_u`）。`ledger_of(册)` → `Ledger`（没账 → None）。"""
    from .. import u_migrate as M
    from ..u_stamp import lacks_u
    cache: dict = {}

    def led(book):
        if book not in cache:
            lg = ledger_of(book)
            cache[book] = lg if lg is not None and lg.exists else None
        return cache[book]
    out, done, left = [], [], []
    for line in lines:
        if not line.strip():
            out.append(line)
            continue
        e = json.loads(line)
        cell = lacks_u(e.get("kind"), e.get("target"), e.get("payload"), lambda b: led(b) is not None)
        if not cell:
            out.append(line)
            continue
        lg = led(cell.split(":", 1)[0])
        if e.get("kind") == "ctx_ruling":
            got, _ = M.plan_rulings(lg, [e["payload"]])
            hit = [x for x in got if x["how"] == "直接"]
            if hit:
                e["payload"]["u"] = hit[0]["u"]
        else:
            an = (e.get("target") or {}).get("anchor") or {}
            got, _ = M.plan_human(lg, [{"id": e.get("id"), "cell": cell, "cells_sha": an.get("cells_sha")}])
            hit = [x for x in got if x["how"] == "锚同切分"]
            if hit:
                e["target"].setdefault("anchor", {})
                e["target"]["anchor"]["u"] = hit[0]["u"]
        if hit:
            done.append({"id": e.get("id"), "cell": cell, "u": hit[0]["u"]})
            out.append(json.dumps(e, ensure_ascii=False))
        else:
            left.append({"id": e.get("id"), "cell": cell, "why": "锚不在账上的同一份切分（或没锚）：用 guji uid migrate-plan"})
            out.append(line)
    return out, done, left


def cmd_stamp(a) -> None:
    from .ledger import Ledger
    _ws(a)
    tot_done, tot_left = 0, 0
    for f in a.files:
        p = Path(f)
        lines = p.read_text(encoding="utf-8").split("\n")
        new, done, left = stamp_lines(lines, Ledger.load)
        tot_done += len(done)
        tot_left += len(left)
        print(f"{f}：补 u {len(done)}、补不上 {len(left)}")
        for x in left[:20]:
            print(f"   ✗ {x['id']}（{x['cell']}）：{x['why']}")
        if a.write and done:
            p.write_text("\n".join(new), encoding="utf-8")
    if not a.write and tot_done:
        print("（只报数；加 --write 真改）")
    if tot_left:
        sys.exit(1)


def cmd_check_u(a) -> None:
    """全库自检：有账册每格最新人裁没 u、也没记作废／转待审的（GM2 口径）。有就列出并退出码 1。"""
    from .. import u_migrate as M
    from .._cv import EventLog
    from ..feedback.levels import counts_as_pin
    from ..feedback.web_votes import HUMAN_VS
    from .ledger import Ledger
    _ws(a)
    log = EventLog()
    raw = [e for e in log.iter_all(raw=True) if M.is_human_cell(e, HUMAN_VS, counts_as_pin)]
    books = a.books or sorted({str(e.target.key).split(":", 1)[0] for e in raw})
    fb = Path(log.events_dir).parent
    total, rows, n_anc = 0, [], 0
    for b in books:
        if not Ledger.load(b).exists:
            continue
        voided = M.void_seen(log, b)
        bad = M.unaccounted(M.latest_by_key(raw, f"{b}:"), voided)
        # 第二项（11-25）：~u 抄件要有补锚档（cv 按事件 id 查框；缺了老人裁判 unanchored、seed_admit 报 human_unbound）
        mine = [e for e in raw if str(e.target.key).startswith(f"{b}:") and e.id not in voided]   # 记过作废的不用绑
        pid = M.anchor_patch_ids(fb, b)
        anc = M.missing_anchor_copies(mine, pid)
        nob = [e for e in M.boxless_copies(mine, pid) if e not in anc]     # 第三项：~u 抄件无框无档（guji uid anchor-fill 补）
        total += len(bad) + len(anc) + len(nob)
        n_anc += len(anc) + len(nob)
        rows += [f"{b}\t{e.target.key}\t{e.id}\t没u没记档" for e in bad]
        rows += [f"{b}\t{e.target.key}\t{e.id}\t抄件缺补锚档" for e in anc]
        rows += [f"{b}\t{e.target.key}\t{e.id}\t抄件无框无档" for e in nob]
        if bad or anc or nob or a.verbose:
            print(f"{b}\t{len(bad)}" + (f"\t缺补锚档 {len(anc)}" if anc else "") + (f"\t无框无档 {len(nob)}" if nob else ""))
    # 第四项（11-26，只报不计入退出码）：待审条目活着却没 u（换单开条目没盖 u；guji uid items-u --write 补）
    from .._cv import chapter_of
    n_item = 0
    for b in books:
        if not Ledger.load(b).exists:
            continue
        ch = chapter_of(b, None)
        k = sum(len(M.live_items_without_u(f)) for f in (M.item_files(fb, ch) if ch else []))
        if k:
            n_item += k
            print(f"{b}\t活条目没u {k}")
    if n_item:
        print(f"ⓘ 待审条目活着却没 u {n_item} 条（只报；guji uid items-u --write 补）")
    if a.out:
        Path(a.out).write_text("册\t格\t事件\t问题\n" + "".join(r + "\n" for r in rows), encoding="utf-8")
    print(f"合计 {total}" + (f"（其中 ~u 抄件绑不上格 {n_anc}：guji uid anchor-fill 补）" if n_anc else ""))
    if total:
        sys.exit(1)


def cmd_items_u(a) -> None:
    from .. import u_migrate as M
    from .._cv import EventLog, chapter_of
    _ws(a)
    fb = Path(EventLog().events_dir).parent
    books = a.books or sorted(p.stem for p in (fb / "uid").glob("*.jsonl"))
    by = os.environ.get("GUJI_ACTOR", "") or "u-fill"
    tot = Counter()
    for b in books:
        ch = chapter_of(b, None)
        for f in (M.item_files(fb, ch) if ch else []):
            r = M.fill_items_u(f, b, by=by, write=a.write)
            if r["补"] or r["缺格"]:
                print(f"{b}\t{f.relative_to(fb.parent)}\t补 {r['补']}" + (f"\t现行账没这格 {r['缺格']}：{r['缺格列表'][:5]}" if r["缺格"] else ""))
            tot.update({k: v for k, v in r.items() if k != "缺格列表"})
    print(json.dumps({"补": tot["补"], "缺格": tot["缺格"], "write": a.write}, ensure_ascii=False))


def cmd_anchor_fill(a) -> None:
    """~u 人裁抄件补锚档：原件有档的抄一行；无框无档的按身份账取 u 在现行切分里的框。只追加 ``feedback/anchors/<册>.jsonl``。
    产物用现行产物根（``GUJI_PRODUCTS_DIR``）：先把各册 main 包取下来（``guji products pack fetch <册> --to …``）。"""
    from .. import u_migrate as M
    from .._cv import EventLog, ProductStore
    from ..feedback.levels import counts_as_pin
    from ..feedback.web_votes import HUMAN_VS
    from .ledger import Ledger
    _ws(a)
    log = EventLog()
    fb = Path(log.events_dir).parent
    raw = [e for e in log.iter_all(raw=True) if M.is_human_cell(e, HUMAN_VS, counts_as_pin)]
    books = a.books or sorted({str(e.target.key).split(":", 1)[0] for e in raw if str(e.id).endswith(M.SUFFIX)})
    store = ProductStore()
    out, bads = {}, []
    for b in books:
        mine = [e for e in raw if str(e.target.key).startswith(f"{b}:")]
        if a.write:
            M.copy_anchor_patches(log, [(e.id[:-len(M.SUFFIX)], e.id, b) for e in mine if str(e.id).endswith(M.SUFFIX)])
        todo = M.boxless_copies(mine, M.anchor_patch_ids(fb, b))
        if not todo:
            continue
        lines, bad = M.u_anchor_fill(b, todo, Ledger.load(b), store)
        bads += [{"book": b, **x} for x in bad]
        if a.write and lines:
            f = fb / "anchors" / f"{b}.jsonl"
            f.parent.mkdir(parents=True, exist_ok=True)
            raw_txt = f.read_text(encoding="utf-8") if f.exists() else ""
            with open(f, "a", encoding="utf-8") as fh:
                if raw_txt and not raw_txt.endswith("\n"):
                    fh.write("\n")
                fh.writelines(json.dumps(d, ensure_ascii=False, separators=(",", ":")) + "\n" for d in lines)
        out[b] = {"补": len(lines), "补不了": len(bad), **({"why": dict(Counter(x["why"] for x in bad))} if bad else {})}
    if a.out and bads:
        Path(a.out).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in bads), encoding="utf-8")
    _print(out)


def cmd_checku_report(a) -> None:
    from . import checku_report as R
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VIRTUAL_ENV", "GUJI_WORKSPACE")}
    guji = str(Path(sys.executable).with_name("guji"))
    r = R.run(a.roots or [str(Path.home()), os.getcwd()], notify=a.notify, guji=guji, env=env)
    _print({ws: {"total": x["total"], **({"error": x["error"]} if "error" in x else {})} for ws, x in r.items()})
    if any(x["total"] for x in r.values()):
        sys.exit(1)


def cmd_tidy_recheck(a) -> None:
    """就地整理 u 迁移转待审的条目：同格并成一条、补候选字（现行字＋旧人裁字＋票字）。"""
    from .. import u_migrate as M
    from ..review import pending_items as P
    from .ledger import Ledger
    _ws(a)
    led = Ledger.load(a.book)
    cur = led.current() if led.exists else {}
    chars: dict[str, str] = {}
    if led.exists:
        for pg in sorted({int(k.split(":")[1]) for k in cur}):
            line = led.page(pg) or {}
            for k, c in (line.get("chars") or {}).items():
                chars[k.split(":", 1)[1]] = c
    out = {}
    for f in a.items:
        st = P.ItemStore(Path(f))
        r = M.tidy_recheck(st, chars)
        n = st.save() if a.write else 0
        out[f] = {**r, "写行": n}
    _print(out)


def cmd_sync(a) -> None:
    from .promote import sync
    ws = str(Path(a.workspace).resolve()) if a.workspace else os.environ.get("GUJI_WORKSPACE")
    r = sync(a.book, a.label, ws, products="local" if a.local else a.products, push=not a.no_push,
             reconfirm=a.reconfirm)
    _print(r)
    if r["status"] in ("pull_failed", "push_failed"):
        sys.exit(1)


def cmd_audit(a) -> None:
    from . import audit
    r = audit.run(submit=a.submit, cv=a.cv)
    _print({"missing": r["missing"], "submitted": r["submitted"]})


def cmd(a) -> None:
    {"sync": cmd_sync, "audit": cmd_audit, "stamp": cmd_stamp, "items-u": cmd_items_u, "retire-into": cmd_retire_into, "revive": cmd_revive, "check-u": cmd_check_u, "check-u-report": cmd_checku_report, "anchor-fill": cmd_anchor_fill, "tidy-recheck": cmd_tidy_recheck, "advance": cmd_advance, "init": cmd_init, "show": cmd_show, "verify": cmd_verify, "table": cmd_table,
     "migrate-plan": cmd_migrate_plan, "web-backfill": cmd_web_backfill}[a.uid_cmd](a)


COMMANDS = {"uid": (add_parser, cmd)}
