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

    q = s.add_parser("audit", help="自检：有账的书每册现行 main 包入过账没有；--submit 给缺的交 uidsync 单")
    q.add_argument("--submit", action="store_true", help="给缺的册交 uidsync 单（同册同标签只跑一次）")
    q.add_argument("--cv", default="main", help="uidsync 单用哪版 cv（缺省 main）")

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

    q = s.add_parser("tidy-recheck", help="u 迁移转待审的条目：同格并成一条、补候选字（现行字＋旧人裁字＋票字）")
    q.add_argument("book", help="cv 册（读身份账取现行字）")
    q.add_argument("--items", nargs="+", required=True, help="条目文件")
    q.add_argument("--write", action="store_true", help="真写（只追加新版本）；缺省只报数")
    q.add_argument("-w", "--workspace", default=None)

    q = s.add_parser("check-u", help="自检：有账册每格最新人裁没 u、也没记作废／转待审的；~u 人裁抄件缺补锚档的（都应为 0；有则退出码 1）")
    q.add_argument("books", nargs="*", help="册（缺省：事件里出现的、有账的全部册）")
    q.add_argument("-o", "--out", default=None, help="清单写到这个 tsv")
    q.add_argument("-v", "--verbose", action="store_true", help="0 的册也列")
    q.add_argument("-w", "--workspace", default=None)

    q = s.add_parser("anchor-fill", help="~u 人裁抄件补锚档：原件有档的照抄；无框无档的按身份账取 u 在现行切分的框（缺省只报数）")
    q.add_argument("books", nargs="*", help="册（缺省：有 ~u 抄件的全部册）")
    q.add_argument("--write", action="store_true", help="真写 feedback/anchors/<册>.jsonl（只追加）")
    q.add_argument("-o", "--out", default=None, help="补不了的清单（jsonl）")
    q.add_argument("-w", "--workspace", default=None)

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


def cmd_migrate_plan(a) -> None:
    from .. import u_migrate as M
    from .._cv import RULING_KIND, EventLog, RulingStore, counts_as_human, replay_key
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
    raw = [e for e in log.iter_all(raw=True) if M.is_human_cell(e, HUMAN_VS, counts_as_human)]
    gated = {e.id for e in log.iter_all() if M.is_human_cell(e, HUMAN_VS, counts_as_human)}
    for e in sorted((e for e in raw if e.id in gated), key=lambda e: (e.ts, e.batch, e.seq)):
        t = e.target
        if not str(t.key).startswith(pre):
            continue
        an = t.anchor or {}
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
        rescued, rest = M.rescue_human(led, res["清单"], same=load_norm(a.book).same, variant=variant, taken=taken)
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


def cmd_check_u(a) -> None:
    """全库自检：有账册每格最新人裁没 u、也没记作废／转待审的（GM2 口径）。有就列出并退出码 1。"""
    from .. import u_migrate as M
    from .._cv import EventLog, counts_as_human
    from ..feedback.web_votes import HUMAN_VS
    from .ledger import Ledger
    _ws(a)
    log = EventLog()
    raw = [e for e in log.iter_all(raw=True) if M.is_human_cell(e, HUMAN_VS, counts_as_human)]
    books = a.books or sorted({str(e.target.key).split(":", 1)[0] for e in raw})
    fb = Path(log.events_dir).parent
    total, rows, n_anc = 0, [], 0
    for b in books:
        if not Ledger.load(b).exists:
            continue
        bad = M.unaccounted(M.latest_by_key(raw, f"{b}:"), M.void_seen(log, b))
        # 第二项（11-25）：~u 抄件要有补锚档（cv 按事件 id 查框；缺了老人裁判 unanchored、seed_admit 报 human_unbound）
        mine = [e for e in raw if str(e.target.key).startswith(f"{b}:")]
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
    if a.out:
        Path(a.out).write_text("册\t格\t事件\t问题\n" + "".join(r + "\n" for r in rows), encoding="utf-8")
    print(f"合计 {total}" + (f"（其中 ~u 抄件绑不上格 {n_anc}：guji uid anchor-fill 补）" if n_anc else ""))
    if total:
        sys.exit(1)


def cmd_anchor_fill(a) -> None:
    """~u 人裁抄件补锚档：原件有档的抄一行；无框无档的按身份账取 u 在现行切分里的框。只追加 ``feedback/anchors/<册>.jsonl``。
    产物用现行产物根（``GUJI_PRODUCTS_DIR``）：先把各册 main 包取下来（``guji products pack fetch <册> --to …``）。"""
    from .. import u_migrate as M
    from .._cv import EventLog, ProductStore, counts_as_human
    from ..feedback.web_votes import HUMAN_VS
    from .ledger import Ledger
    _ws(a)
    log = EventLog()
    fb = Path(log.events_dir).parent
    raw = [e for e in log.iter_all(raw=True) if M.is_human_cell(e, HUMAN_VS, counts_as_human)]
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
    r = sync(a.book, a.label, ws, products="local" if a.local else a.products, push=not a.no_push)
    _print(r)
    if r["status"] in ("pull_failed", "push_failed"):
        sys.exit(1)


def cmd_audit(a) -> None:
    from . import audit
    r = audit.run(submit=a.submit, cv=a.cv)
    _print({"missing": r["missing"], "submitted": r["submitted"]})


def cmd(a) -> None:
    {"sync": cmd_sync, "audit": cmd_audit, "check-u": cmd_check_u, "anchor-fill": cmd_anchor_fill, "tidy-recheck": cmd_tidy_recheck, "advance": cmd_advance, "init": cmd_init, "show": cmd_show, "verify": cmd_verify, "table": cmd_table,
     "migrate-plan": cmd_migrate_plan, "web-backfill": cmd_web_backfill}[a.uid_cmd](a)


COMMANDS = {"uid": (add_parser, cmd)}
