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
  ref-check-items --cells c.jsonl --shrink-dir D --pages-dir D --out items.jsonl   整理本真错复核页 items（疑整理本错排最前，带邻格条）
  ref-check-apply --results DIR --out 改字.tsv   复核页结果 → 改字的格（格号、旧字、新字、备注）
  pair-items --cells cells.jsonl --out items.jsonl [-n 30] [--seed S]   字对白名单抽样：每组稳定抽 n 格带前后文 → pair_whitelist items
  pair-apply --results DIR [--min-rate 1.0] [--min-judged 30]            白名单页结果 → 每组同字率＋可入白名单的组
  cp-apply   --results DIR [--who 名] [--items items.jsonl]         码位定夺页结果 → codepoints.yaml 片段＋follow_ref＋分开/未定清单
  build glyph_quality --items <分片>/items.jsonl --root <分片> ...   字块质量页；可直接吃 dataset 金标信封（--all-crops 连已标的也上）
  build seg_cut --items 人裁切线候选.jsonl --root <放列图的目录> ...   人裁切线页（小字并成一格，点图画切线）
  segcut-apply --results DIR --out F                               人裁切线结果 → jsonl（格号、结论、列图/页图切线坐标）
  cold-items --cells 待审.tsv --pack-dir '<包>/{vol}' --crops-dir '<图>/{cell}.png' --out-dir D   冷启动快审：按 5b 领先/cov/库例数分高、低把握 items（见 cold_start.py）
  cold-pages --out-dir D --book B                                  出高/低把握两张页（高：带「本页其余都对」；低：一格一卡、没点不算对）
  hard-items --items items.jsonl --shrink-dir D --pages-dir D --out items2.jsonl [--pack-dir '<包>/{vol}']   难认字/低把握页：给每格加整列图（本格红框）、左右邻列图、同列 ±8 格上下文（char_card 1.6 渲染）
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
    p.add_argument("--per-page", type=int)
    p.add_argument("--font", action="append", help="（char_card）子集化内嵌的字体文件，可重复，按顺序补字")
    p.add_argument("--font-dir", help="（char_card）cv 的 fonts/ 目录：自动用 I.Ming、Jigmo 三档补字")
    p.add_argument("--per-card", type=int, default=5); p.add_argument("--hint")
    p.add_argument("--mode", choices=["check"], help="gold_sample：check＝核对模式（显示机器答案，只点对/错填字/看不清）")
    p.add_argument("--exclude", nargs="*", default=[], help="已录入格号文件（json 列表/jsonl/每行一个）")
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
    p = sub.add_parser("segcut-apply"); p.add_argument("--results", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("ref-check-items"); p.add_argument("--cells", required=True)
    p.add_argument("--shrink-dir", required=True); p.add_argument("--pages-dir", required=True)
    p.add_argument("--page-name", default="{page}.png"); p.add_argument("--out", required=True)
    p.add_argument("--img-dir"); p.add_argument("--strip", type=int, default=2); p.add_argument("--vol")
    p = sub.add_parser("ref-check-apply"); p.add_argument("--results", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("pair-items"); p.add_argument("--cells", required=True); p.add_argument("--out", required=True)
    p.add_argument("-n", type=int, default=30); p.add_argument("--seed", default="pair-whitelist")
    p.add_argument("--min-cells", type=int, default=1); p.add_argument("--pre", help="预选 json {组: 同字|不同字|不确定}")
    p = sub.add_parser("pair-apply"); p.add_argument("--results", required=True)
    p.add_argument("--min-rate", type=float, default=1.0); p.add_argument("--min-judged", type=int, default=30)
    p = sub.add_parser("cp-apply"); p.add_argument("--results", required=True); p.add_argument("--who", default="用户")
    p.add_argument("--items", help="出页时的 items.jsonl；给了就列出还没确认的组")
    p = sub.add_parser("unconfirmed"); p.add_argument("--items", required=True); p.add_argument("--results", required=True)
    p = sub.add_parser("ctx2-export"); p.add_argument("--packs", required=True, help="<目录>/<册>/seed_admit/p*.json")
    p.add_argument("--groups", default="日曰,己已巳"); p.add_argument("--out", required=True)
    p.add_argument("--half", action="store_true", help="只取半格（小注）"); p.add_argument("--include-admitted", action="store_true")
    p = sub.add_parser("ctx2-import"); p.add_argument("--cells", required=True); p.add_argument("--a", required=True)
    p.add_argument("--b", required=True); p.add_argument("--out", required=True); p.add_argument("--round", default="")
    p.add_argument("--a2", help="第二轮甲（独立会话）；给了 --a2/--b2 就要求每轮都一致 high 才定字"); p.add_argument("--b2")
    p = sub.add_parser("closeout-sum"); p.add_argument("--results", required=True)
    p = sub.add_parser("cold-items"); p.add_argument("--cells", required=True)
    p.add_argument("--pack-dir", required=True, help="包目录，含 rare_candidates/；多册用 {vol}")
    p.add_argument("--crops-dir", required=True, help="裁图路径模板，含 {cell}（格号冒号换下划线），如 /x/crops/{cell}.png")
    p.add_argument("--out-dir", required=True); p.add_argument("--skip", nargs="*", default=[], help="已点过的格号文件")
    p.add_argument("--skip-chars", default="", help="不上页的字（如 木入八己已巳）")
    p.add_argument("--where", action="append", default=[], help="只取某列以某前缀开头的行，如 层=2（可重复）")
    p = sub.add_parser("hard-items"); p.add_argument("--items", required=True)
    p.add_argument("--shrink-dir", required=True); p.add_argument("--pages-dir", required=True)
    p.add_argument("--page-name", default="{page}.png"); p.add_argument("--out", required=True)
    p.add_argument("--pack-dir"); p.add_argument("--ctx-n", type=int, default=8); p.add_argument("--img-dir")
    p = sub.add_parser("cold-pages"); p.add_argument("--out-dir", required=True); p.add_argument("--book", required=True)
    p.add_argument("--tag", default="")
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
                                         build_mod.read_ids(a.exclude), a.mode, a.root, a.all_crops, a.box, rest_ok=not a.no_rest_ok,
                                         fonts=((list(a.font or []) + (build_mod.default_fonts(a.font_dir) if a.font_dir else [])) or None)),
                         ensure_ascii=False))
    elif a.cmd == "cold-items":
        from . import cold_start
        rows = cold_start._read_rows(a.cells)
        for w in a.where:
            k, _, v = w.partition("=")
            rows = [r for r in rows if str(r.get(k, "")).startswith(v)]
        hi, lo, st = cold_start.classify(rows, a.pack_dir, a.crops_dir, build_mod.read_ids(a.skip), a.skip_chars)
        out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
        _write_jsonl(out / "hi.jsonl", hi); _write_jsonl(out / "lo.jsonl", lo)
        print(json.dumps(st, ensure_ascii=False))
    elif a.cmd == "hard-items":
        from . import crop
        its = build_mod.read_items(a.items)
        img_dir = a.img_dir or str(Path(a.out).with_suffix("")) + "_col"
        extra = crop.column_images([r["id"] for r in its], a.shrink_dir, a.pages_dir, img_dir, a.page_name,
                                   ctx_n=a.ctx_n, pack_dir=a.pack_dir)
        rows = []
        for r in its:
            e = extra.get(r["id"], {})
            r = dict(r, **{k: v for k, v in e.items() if k != "ctx"})
            if e.get("ctx") and not r.get("ctx"):
                r["ctx"] = e["ctx"]
            rows.append(r)
        _write_jsonl(a.out, rows)
        print(f"{len(rows)} 格，{len(extra)} 格有整列图 → {a.out}（图在 {img_dir}）")
    elif a.cmd == "cold-pages":
        from . import cold_start
        print(json.dumps(cold_start.write_pages(a.out_dir, a.book, a.tag), ensure_ascii=False))
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
        nl = {d["id"] for d in docs if d.get("no_glyph_lib") and "id" in d}   # 1.6「不入库」勾选
        for r in rows:
            if r["id"] in nl:
                r["no_glyph_lib"] = True
        _write_jsonl(a.out, rows)
        from collections import Counter
        print(dict(Counter(r["status"] for r in rows)), f"不入库 {sum(1 for r in rows if r.get('no_glyph_lib'))} 格" if nl else "")
    elif a.cmd == "cp-items":
        from . import codepoint as cp
        its = cp.items_from_groups(json.loads(Path(a.groups).read_text(encoding="utf-8")), a.cache)
        _write_jsonl(a.out, its)
        print(f"{len(its)} 组，{sum(len(r['tiles']) for g in its for r in g['rows'].values())} 格图 → {a.out}")
    elif a.cmd == "segcut-apply":
        from . import seg_cut as sc
        rows = sc.label_rows(sc.labels_from_docs(_docs(a.results)))
        _write_jsonl(a.out, rows)
        print(f"{len(rows)} 格 → {a.out}")
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
    elif a.cmd == "ref-check-items":
        from . import ref_check
        its, miss = ref_check.build_items(build_mod.read_items(a.cells), a.shrink_dir, a.pages_dir,
                                          a.img_dir or str(Path(a.out).with_suffix("")) + "_img", a.page_name, a.strip,
                                          default_vol=a.vol)
        _write_jsonl(a.out, its)
        print(f"{len(its)} 格 → {a.out}；缺图 {len(miss)}" + (f"：{', '.join(miss[:10])}" if miss else ""))
    elif a.cmd == "ref-check-apply":
        from . import ref_check
        rows = ref_check.apply_results(_docs(a.results))
        Path(a.out).write_text("cell\told\tnew\tnote\n" + "".join(f"{r['cell']}\t{r['old']}\t{r['new']}\t{r['note']}\n" for r in rows), encoding="utf-8")
        print(f"{len(rows)} 格改字 → {a.out}")
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
    elif a.cmd == "ctx2-export":
        from . import ctx2
        gs = tuple(x for x in a.groups.split(",") if x)
        cells = ctx2.collect(a.packs, gs, a.include_admitted, a.half)
        o = Path(a.out); o.mkdir(parents=True, exist_ok=True)
        (o / "cells.json").write_text(json.dumps(cells, ensure_ascii=False), encoding="utf-8")
        (o / "prompt_A.txt").write_text(ctx2.prompts(cells, False), encoding="utf-8")
        (o / "prompt_B.txt").write_text(ctx2.prompts(cells, True), encoding="utf-8")
        print(f"{len(cells)} 格 → {o}（cells.json、prompt_A.txt、prompt_B.txt；两个干净会话各读一个，回 JSON 存 A.json/B.json）")
    elif a.cmd == "ctx2-import":
        from . import ctx2
        cells = json.loads(Path(a.cells).read_text(encoding="utf-8"))
        rounds = [(ctx2._load(a.a), ctx2._load(a.b))]
        if a.a2 and a.b2:
            rounds.append((ctx2._load(a.a2), ctx2._load(a.b2)))
        rows = ctx2.decide_rounds(cells, rounds)
        print(json.dumps(ctx2.write(rows, a.out, a.round), ensure_ascii=False))
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
