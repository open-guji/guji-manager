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
    r = advance(a.book, _store(a), _pages(a.pages), dry_run=a.dry_run, force=a.force)
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

    q = s.add_parser("advance", help="切字后入账（同一份切分重跑不动）")
    common(q)
    q.add_argument("--pages", default=None, help="只入这些页（如 1-20,33）")
    q.add_argument("--dry-run", action="store_true", help="只算不写")
    q.add_argument("--force", action="store_true", help="cells_sha 没变也重入一行")

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
    for e in sorted(EventLog().iter_all(), key=lambda e: (e.ts, e.batch, e.seq)):
        t = e.target
        if (e.kind != "confirm" or t.unit != "cell" or not str(t.key).startswith(pre)
                or (e.payload or {}).get("v") not in HUMAN_VS or not counts_as_human(e)):
            continue
        an = t.anchor or {}
        hum[t.key] = {"id": e.id, "cell": t.key, "shape": (e.payload or {}).get("shape"),
                      "reading": (e.payload or {}).get("reading"),
                      "cells_sha": an.get("cells_sha"), "u": an.get("u")}
        hum_ev[e.id] = e
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
    if a.write:
        w = M.apply(res, ruling_events=rul_ev, human_events=hum_ev, ruling_log=store.log, event_log=EventLog())
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
    res = B.plan_rows(B.Resolver(led, same), rows)
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


def cmd(a) -> None:
    {"advance": cmd_advance, "init": cmd_init, "show": cmd_show, "verify": cmd_verify, "table": cmd_table,
     "migrate-plan": cmd_migrate_plan, "web-backfill": cmd_web_backfill}[a.uid_cmd](a)


COMMANDS = {"uid": (add_parser, cmd)}
