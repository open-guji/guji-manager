"""python -m guji_manager.review_pages <命令>（也挂在 `guji-manager review-pages`）。

  list                                      页型、版本、用途
  preselect  --cells cells.jsonl --out DIR  预选：三方一致的格归 auto（不上页），其余出 page.jsonl 与统计
  build      TYPE --items items.jsonl --book B --out page.html   出页（一字一卡同时写 page.cards.json）
  seg-cards  --per-page 逐页.tsv --per-cell 逐格.tsv --out items.json   A22 seg_causes → 切分归因卡片
  build ... --exclude landed.json            撤掉已录入的格（点过即录入、不再上页；可给多个文件）
  expand     --cards page.cards.json --results DIR  把卡片页结果展开成逐格决定（ok/pick/seg/unclear/bad/follow/audit）
  crop       --cells ids.txt --shrink-dir D --pages-dir D --out DIR   按 cell_shrink 字框裁审页图
  char sheet|pull|ingest ...                冷启动快审页的生成与落库（char_grid；原 ai-team 冷启动快审流程模板）
  ledger     add|summary                    用时与改判台账（--from-results DIR 从结果文档入账）
  cp-items   --groups groups.json --cache DIR --out items.jsonl   按组看图的 groups.json → 码位定夺页 items
  unconfirmed --items items.jsonl --results DIR   列出还没确认的项（逐项文档里没有、也没翻过去的）
  closeout-sum --results DIR                  收口单：各去向的格数合计
  pair-events TYPE --items X.items.json --results DIR --book B --out events.jsonl [--apply --batch 批名 --reviewer 名]
                                            形近字对比卡（near_pair）/库内刻例审阅卡（lib_audit）结果 → relabel/evict/near_form/confirm 事件；
                                            缺省只写说明文件复核，--apply 才追加本机事件日志（推库、出 g 另要用户点头）
  pair-items --cells cells.jsonl --out items.jsonl [-n 30] [--seed S]   字对白名单抽样：每组稳定抽 n 格带前后文 → pair_whitelist items
  pair-apply --results DIR [--min-rate 1.0] [--min-judged 30]            白名单页结果 → 每组同字率＋可入白名单的组
  cp-apply   --results DIR [--who 名] [--items items.jsonl]         码位定夺页结果 → codepoints.yaml 片段＋follow_ref＋分开/未定清单
  build glyph_quality --items <分片>/items.jsonl --root <分片> ...   字块质量页；可直接吃 dataset 金标信封（--all-crops 连已标的也上）
  gq-apply   --results DIR --out F [--shard items.jsonl --why …]   字块质量结果 → 标签 jsonl；给 --shard 则按（格号, sha）回写信封
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _write_jsonl(path, rows):
    Path(path).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _docs(d):
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(Path(d).rglob("*.json"))]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["char"]:
        from .char_review import main as char_main
        return char_main(argv[1:])
    ap = argparse.ArgumentParser(prog="guji-manager review-pages", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("preselect"); p.add_argument("--cells", required=True); p.add_argument("--out", required=True)
    p.add_argument("--gate", type=float, default=0.95)
    p = sub.add_parser("build"); p.add_argument("type"); p.add_argument("--items", required=True)
    p.add_argument("--book", required=True); p.add_argument("--out", required=True)
    p.add_argument("--per-page", type=int); p.add_argument("--per-card", type=int, default=5); p.add_argument("--hint")
    p.add_argument("--mode", choices=["check"], help="gold_sample：check＝核对模式（显示机器答案，只点对/错填字/看不清）")
    p.add_argument("--exclude", nargs="*", default=[], help="已录入格号文件（json 列表/jsonl/每行一个）")
    p.add_argument("--title", help="页头标题（缺省用页型名；char_card --no-rest-ok 缺省「一字一卡（疑难格审定）」）")
    p.add_argument("--no-rest-ok", action="store_true", help="char_card：不要「本页其余都对」，没点的格不算对（难认字页）")
    p.add_argument("--root", help="glyph_quality：items 里图路径的相对根（dataset 分片目录）")
    p.add_argument("--all-crops", action="store_true", help="glyph_quality：信封里已有标签的字块也上页（复核用）")
    p.add_argument("--box", type=int, help="glyph_quality：字块放大框边长（px，缺省 120）")
    p = sub.add_parser("seg-cards"); p.add_argument("--per-page", required=True, help="seg_causes 逐页.tsv")
    p.add_argument("--per-cell", required=True, help="seg_causes 逐格.tsv"); p.add_argument("--out", required=True)
    p = sub.add_parser("expand"); p.add_argument("--cards", required=True); p.add_argument("--results", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("crop"); p.add_argument("--cells", required=True, help="格号文件（每行一个，或 jsonl 带 id）")
    p.add_argument("--shrink-dir", required=True, help="cell_shrink 目录（pNNNN.json）；多册用 {vol} 占位")
    p.add_argument("--pages-dir", required=True, help="原页图目录；文件名用 --page-name 定")
    p.add_argument("--page-name", default="{page}.png", help="页图文件名模板，可用 {vol} {page} {page4}")
    p.add_argument("--out", required=True); p.add_argument("--pad", type=int, default=0)
    p = sub.add_parser("ledger"); p.add_argument("action", choices=["add", "summary"])
    p.add_argument("--ledger"); p.add_argument("--from-results"); p.add_argument("--type"); p.add_argument("--book")
    p = sub.add_parser("cp-items"); p.add_argument("--groups", required=True); p.add_argument("--cache", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("gq-apply"); p.add_argument("--results", required=True); p.add_argument("--out", required=True)
    p.add_argument("--shard", help="dataset 金标信封 items.jsonl；给了就回写成同样格式")
    p.add_argument("--why", default="字块质量页（glyph_quality）人点")
    p = sub.add_parser("pair-items"); p.add_argument("--cells", required=True); p.add_argument("--out", required=True)
    p.add_argument("-n", type=int, default=30); p.add_argument("--seed", default="pair-whitelist")
    p.add_argument("--min-cells", type=int, default=1); p.add_argument("--pre", help="预选 json {组: 同字|不同字|不确定}")
    p = sub.add_parser("pair-apply"); p.add_argument("--results", required=True)
    p.add_argument("--min-rate", type=float, default=1.0); p.add_argument("--min-judged", type=int, default=30)
    p = sub.add_parser("cp-apply"); p.add_argument("--results", required=True); p.add_argument("--who", default="用户")
    p.add_argument("--items", help="出页时的 items.jsonl；给了就列出还没确认的组")
    p = sub.add_parser("unconfirmed"); p.add_argument("--items", required=True); p.add_argument("--results", required=True)
    p = sub.add_parser("closeout-sum"); p.add_argument("--results", required=True)
    p = sub.add_parser("pair-events"); p.add_argument("type", choices=["near_pair", "lib_audit"])
    p.add_argument("--items", required=True); p.add_argument("--results", required=True)
    p.add_argument("--book", required=True); p.add_argument("--out", required=True)
    p.add_argument("--source", default="review_pages"); p.add_argument("--apply", action="store_true")
    p.add_argument("--batch"); p.add_argument("--reviewer")
    a = ap.parse_args(argv)

    from . import build as build_mod, cards, ledger, preselect
    from .registry import PAGE_TYPES, get

    if a.cmd == "list":
        for t in PAGE_TYPES.values():
            print(f"{t.key:15} v{t.version:6} {'有模板' if t.template else '待建  '}  {t.title}｜{t.used_for}")
    elif a.cmd == "preselect":
        res = preselect.preselect(build_mod.read_items(a.cells), a.gate)
        out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
        _write_jsonl(out / "auto.jsonl", [{k: v for k, v in r.items() if k != "cell"} for r in res["auto"]])
        _write_jsonl(out / "page.jsonl", [{k: v for k, v in r.items() if k != "cell"} | {"img": r["cell"].get("img")} for r in res["page"]])
        (out / "stats.json").write_text(json.dumps(res["stats"], ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(res["stats"], ensure_ascii=False))
    elif a.cmd == "build":
        print(json.dumps(build_mod.build(a.type, build_mod.read_items(a.items), a.book, a.out,
                                         a.per_page, a.per_card, a.hint,
                                         build_mod.read_ids(a.exclude), a.mode, a.root, a.all_crops, a.box, rest_ok=not a.no_rest_ok, title=a.title),
                         ensure_ascii=False))
    elif a.cmd == "seg-cards":
        from . import seg_causes
        cs = seg_causes.build_cards(a.per_page, a.per_cell)
        Path(a.out).write_text(json.dumps(cs, ensure_ascii=False), encoding="utf-8")
        print(f"{len(cs)} 张卡 → {a.out}（img 空；按 cell_shrink 字框裁图后填进每格的 img，再 build seg_cause）")
    elif a.cmd == "crop":
        from . import crop
        ids = sorted(build_mod.read_ids([a.cells]))
        res = crop.crop_cells(ids, a.shrink_dir, a.pages_dir, a.out, a.page_name, a.pad)
        print(json.dumps({"cropped": len(res["ok"]), "missing": len(res["missing"]),
                          "missing_head": res["missing"][:10]}, ensure_ascii=False))
    elif a.cmd == "expand":
        cs = {c["char"]: c for c in json.loads(Path(a.cards).read_text(encoding="utf-8"))}
        docs = _docs(a.results)
        pages = {c["char"]: c for d in docs for c in d.get("cards", [])}
        cells: dict[str, dict] = {}                  # 卡字 → {格号: v}（逐格文档，比页文档新）
        for d in docs:
            if "id" in d and "v" in d and d.get("card") in cs:
                cells.setdefault(d["card"], {})[d["id"]] = d["v"]
        for d in docs:                               # 卡头改字文档 k_<卡字>（1.2 起每改即存）
            if "id" not in d and "pick" in d and d.get("card") in cs:
                pg = pages.setdefault(d["card"], None)
                if pg is None:
                    cells.setdefault(d["card"], {})
                    for s in cs[d["card"]]["samples"]:
                        cells[d["card"]].setdefault(s["id"], "pick:" + d["pick"])
                else:
                    pg["pick"] = d["pick"]
        rows = []
        for ch in pages.keys() | cells.keys():
            if ch in cs:
                rows += cards.expand_card_result(cs[ch], pages.get(ch), cells.get(ch))
        _write_jsonl(a.out, rows)
        from collections import Counter
        print(dict(Counter(r["status"] for r in rows)))
    elif a.cmd == "cp-items":
        from . import codepoint as cp
        its = cp.items_from_groups(json.loads(Path(a.groups).read_text(encoding="utf-8")), a.cache)
        _write_jsonl(a.out, its)
        print(f"{len(its)} 组，{sum(len(r['tiles']) for g in its for r in g['rows'].values())} 格图 → {a.out}")
    elif a.cmd == "gq-apply":
        import datetime
        from . import glyph_quality as gq
        labels = gq.labels_from_docs(_docs(a.results))
        if a.shard:
            rows = build_mod.read_items(a.shard)
            ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            rows, stat = gq.apply_to_shard(rows, labels, ts, a.why)
            Path(a.out).write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
                                   encoding="utf-8")
            print(json.dumps(dict(stat), ensure_ascii=False))
        else:
            rs = gq.label_rows(labels)
            _write_jsonl(a.out, rs)
            from collections import Counter
            print(len(rs), dict(Counter(r["label"] for r in rs)))
    elif a.cmd == "pair-items":
        from . import pair
        pre = json.loads(Path(a.pre).read_text(encoding="utf-8")) if a.pre else None
        its = pair.sample_groups(build_mod.read_items(a.cells), a.n, a.seed, pre, a.min_cells)
        _write_jsonl(a.out, its)
        print(f"{len(its)} 组，{sum(len(g['tiles']) for g in its)} 格 → {a.out}")
    elif a.cmd == "pair-apply":
        from . import pair
        rows = pair.rates(_docs(a.results))
        for r in rows:
            rt = "—" if r["rate"] is None else f"{r['rate']:.0%}"
            print(f"{r['key']}\t{r['pick']}\t同字率 {rt}\t同{r['same']} 异{r['diff']} 不清{r['unclear']}\t{r['note']}")
        wl = pair.whitelist(rows, a.min_rate, a.min_judged)
        print("# 可入白名单：" + "、".join(wl["ok"]))
        for k, why in wl["hold"]:
            print(f"# 不放：{k}（{why}）")
    elif a.cmd == "cp-apply":
        import datetime
        from . import codepoint as cp
        docs = _docs(a.results)
        print(cp.to_yaml(cp.apply(cp.decisions_from_docs(docs)), a.who, str(datetime.date.today())), end="")
        if a.items:
            from . import results
            un = results.unconfirmed([g["key"] for g in build_mod.read_items(a.items)], docs)
            print(f"# 未确认 {len(un)} 组（没点也没翻过去，不要当成全对）：" + "、".join(un[:30]) + ("…" if len(un) > 30 else ""))
    elif a.cmd == "unconfirmed":
        from . import results
        its = build_mod.read_items(a.items)
        un = results.unconfirmed([r.get("id", r.get("key")) for r in its], _docs(a.results))
        print(f"{len(un)}/{len(its)} 项未确认")
        for i in un:
            print(i)
    elif a.cmd == "closeout-sum":
        from . import results
        tot: dict = {}
        for d in results.flatten(_docs(a.results)).values():
            tot[d.get("pick")] = tot.get(d.get("pick"), 0) + (d.get("n") or 0)
        print(json.dumps(tot, ensure_ascii=False))
    elif a.cmd == "pair-events":
        from . import pair_audit
        items = json.loads(Path(a.items).read_text(encoding="utf-8"))
        docs = pair_audit.read_docs(a.results)
        fn = pair_audit.near_pair_decisions if a.type == "near_pair" else pair_audit.lib_audit_decisions
        decs = fn(items, docs)
        specs = pair_audit.to_specs(decs, a.book, f"{a.source}:{a.type}")
        _write_jsonl(a.out, specs)
        from collections import Counter
        print({"decisions": dict(Counter(r["status"] for r in decs)),
               "events": {f"{k[0]}/{k[1]}": n for k, n in Counter((s_["kind"], s_["payload"].get("v")) for s_ in specs).items()}})
        if a.apply:
            if not a.batch:
                sys.exit("--apply 需要 --batch 批名")
            from .._cv import EventLog, EventTarget, make_event
            log = EventLog()
            base = log.latest_seq(a.batch) + 1
            evs = [make_event(a.batch, base + k, s_["kind"], EventTarget(step=s_["step"], unit="cell", key=s_["key"], book=s_["book"]),
                              s_["payload"], actor="user", reviewer=a.reviewer) for k, s_ in enumerate(specs)]
            print(f"追加 {log.append(evs)} 条到批 {a.batch}（还没消费；消费 route_and_consume，推库要用户点头）")
        else:
            print(f"dry-run：说明文件 → {a.out}；--apply --batch 批名 才追加事件日志")
    elif a.cmd == "ledger":
        path = Path(a.ledger) if a.ledger else ledger.default_path()
        if a.action == "add":
            if not (a.from_results and a.type):
                sys.exit("add 需要 --from-results DIR 和 --type")
            pt = get(a.type)
            rows = ledger.from_result_docs(_docs(a.from_results), pt.key, pt.version, a.book)
            for r in rows:
                ledger.record(path, **r)
            print(f"入账 {len(rows)} 页 → {path}")
        else:
            for s in ledger.summarize(ledger.read(path)):
                print(f"{s['page_type']} v{s['tpl_version']}：{s['pages']} 页 {s['cells']} 格 "
                      f"{s['sec_per_cell']}秒/格 改判率 {s['overturn_rate']:.1%}")
                for h in s["hints"]:
                    print("  提示：" + h)


if __name__ == "__main__":
    main()
