"""python -m guji_manager.review_pages <命令>（也挂在 `guji-manager review-pages`）。

  list                                      页型、版本、用途
  preselect  --cells cells.jsonl --out DIR  预选：三方一致的格归 auto（不上页），其余出 page.jsonl 与统计
  build      TYPE --items items.jsonl --book B --out page.html   出页（一字一卡同时写 page.cards.json）
  expand     --cards page.cards.json --results DIR  把卡片页结果展开成逐格决定（ok/bad/follow/audit）
  ledger     add|summary                    用时与改判台账（--from-results DIR 从结果文档入账）
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
    ap = argparse.ArgumentParser(prog="guji-manager review-pages", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("preselect"); p.add_argument("--cells", required=True); p.add_argument("--out", required=True)
    p.add_argument("--gate", type=float, default=0.95)
    p = sub.add_parser("build"); p.add_argument("type"); p.add_argument("--items", required=True)
    p.add_argument("--book", required=True); p.add_argument("--out", required=True)
    p.add_argument("--per-page", type=int); p.add_argument("--per-card", type=int, default=5); p.add_argument("--hint")
    p = sub.add_parser("expand"); p.add_argument("--cards", required=True); p.add_argument("--results", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("ledger"); p.add_argument("action", choices=["add", "summary"])
    p.add_argument("--ledger"); p.add_argument("--from-results"); p.add_argument("--type"); p.add_argument("--book")
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
                                         a.per_page, a.per_card, a.hint), ensure_ascii=False))
    elif a.cmd == "expand":
        cs = {c["char"]: c for c in json.loads(Path(a.cards).read_text(encoding="utf-8"))}
        rows = []
        for d in _docs(a.results):
            for c in d.get("cards", []):
                rows += cards.expand_card_result(cs[c["char"]], c)
        _write_jsonl(a.out, rows)
        from collections import Counter
        print(dict(Counter(r["status"] for r in rows)))
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
