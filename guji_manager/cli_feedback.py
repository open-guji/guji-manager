# -*- coding: utf-8 -*-
"""人裁与金标命令：events（反馈事件）、gold（金标）、batch（审查批次）、label-batch（L3 补标签）。

拆分 P2（2026-11-02）从 open-guji-cv 原样搬来；cv 内部一律经 `._cv` 取。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import _cv   # 共用辅助现取（测试 monkeypatch cv 源模块 照样生效）
from ._cv import imread as cv_imread


def cmd_events(args) -> None:
    from ._cv import route_and_consume
    from ._cv import EventLog
    from ._cv import harvest_file
    from ._cv import RouteTable
    from ._cv import BatchStore
    if args.action == "import-vision":
        _import_vision(args)
        return
    if args.action == "lint":
        # 按 doc/formats/人裁事件规范.md 体检事件日志（只读）；有 E- 级问题以 1 退出
        from ._cv import lint
        rep = lint(EventLog().root)
        print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=1) if args.json else rep.render())
        sys.exit(1 if rep.n_errors else 0)
    log = EventLog()
    if args.action == "harvest":
        b = BatchStore().get(args.batch)
        step = args.step or (b.step if b else "")
        if not step:
            print("需要 --step（或先建批次）")
            sys.exit(1)
        evs = harvest_file(Path(args.file), args.batch, step, args.unit, args.kind)
        n = log.append(evs)
        print(f"解析 {len(evs)} 条，新增 {n} 条 → {log.batch_path(args.batch)}")
    elif args.action == "route":
        # 消费落 workspace 裁决表，不落 open-guji-dataset（2026-09-13 三仓边界）
        from ._cv import verdict_store
        table = RouteTable.load(log.root / "routes.yaml")
        out = route_and_consume(log, args.batch, table, verdict_store(), dry_run=args.dry_run)
        print(json.dumps(out, ensure_ascii=False, indent=1))
    elif args.action == "verdicts":
        # 读回本批已裁的字位／已拖的切线。与控制台的两条 verdicts 路由同一份装配
        from ._cv import cutline_verdicts, review_verdicts
        fn = cutline_verdicts if args.kind == "cutline" else review_verdicts
        _cv.out(fn(args.batch, log))
    elif args.action == "list":
        evs = _select_events(log, args.batch, args.book)
        for e in evs[-args.limit:]:
            print(f"  {e.id}  {e.kind:12s} {e.target.key:28s} {json.dumps(e.payload, ensure_ascii=False)}")
        print(f"  共 {len(evs)} 条")


def _select_events(log, batch: str | None, book: str | None = None) -> list:
    """`events list` 的取数：批次名可带通配（`vol03-*`，按文件名匹配后合并）；`book` 只留
    target.key 以 `<册>:` 开头的事件——通配批次里混进别册的 key 时（GUJI-77）不串册。只读。"""
    import fnmatch
    from ._cv import replay_key
    if batch and any(c in batch for c in "*?["):
        evs = sorted((e for b in log.batches() if fnmatch.fnmatch(b, batch)
                      for e in log.read(b)), key=replay_key)
    elif batch:
        evs = log.read(batch)
    else:
        evs = sorted(log.iter_all(), key=replay_key)
    if book:
        evs = [e for e in evs if e.target.key.startswith(f"{book}:")]
    return evs


def _import_vision(args) -> None:
    """`guji events import-vision <jsonl> -w <工作区> [--book 册]`：看图结论 → `feedback/vision/`
    （overview#428；格式见 `feedback/vision.py` 模块头与 runbook S8/S10）。不是人裁：不进字形库、
    不算已裁，判错的格回待审队列（doubt `vision_flag`）。"""
    from ._cv import import_vision
    if not args.workspace:
        print("✗ import-vision 要 -w <工作区>（看图结论写进工作区的 feedback/vision/）", file=sys.stderr)
        sys.exit(2)
    if not args.batch:
        print("✗ 要给 jsonl 路径：guji events import-vision reports/vol04/看图结论.jsonl -w <工作区>",
              file=sys.stderr)
        sys.exit(2)
    path = Path(args.batch)
    if not path.exists():
        print(f"✗ 文件不存在：{path}", file=sys.stderr)
        sys.exit(2)
    res = import_vision(path, batch=args.as_batch, judge=args.judge, book=args.book,
                        gold=not args.no_gold, dry_run=args.dry_run, source_rev=getattr(args, "source_rev", None))
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if res["errors"]:
        print(f"✗ {len(res['errors'])} 处格式错，整批没写", file=sys.stderr)
        sys.exit(1)
    if args.dry_run:
        print("（试算，未写入；去掉 --dry-run 才导入）")


def cmd_gold(args) -> None:
    from ._cv import verdict_store
    from ._cv import GoldStore
    # 默认看测试集仓；--verdicts 看 workspace 裁决表（同格式，同一套命令）
    store = verdict_store() if getattr(args, "verdicts", False) else GoldStore()
    if args.action == "import":
        # 裁决表 → 测试集：唯一往 dataset 写人裁数据的入口，必须人显式发起
        from ._cv import ImportFilter, import_to_dataset, parse_pages
        if not args.shard:
            print("需要分片名，如 char-segmentation/touching-cuts")
            sys.exit(1)
        ids = None
        if args.ids:
            ids = {l.strip() for l in Path(args.ids).read_text(encoding="utf-8").splitlines() if l.strip()}
        flt = ImportFilter(book=args.book, pages=parse_pages(args.pages), stratum=args.stratum,
                           ids=ids, include_uncertain=args.include_uncertain)
        res = import_to_dataset(args.shard, verdict_store(), GoldStore(), flt,
                                why=args.why or "", dry_run=args.dry_run)
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=1))
        if args.dry_run:
            print("（试算，未写入；去掉 --dry-run 才导入）")
        return
    if args.action == "export":
        # 测试集仓 → workspace 裁决表（书的事实类分片，如 page-type）
        from ._cv import export_to_workspace
        if not args.shard:
            print("需要分片名，如 page-type")
            sys.exit(1)
        res = export_to_workspace(args.shard, GoldStore(), verdict_store(),
                                  why=args.why or "", dry_run=args.dry_run)
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=1))
        return
    if args.action == "rebuild":
        # 事件日志 → 裁决表（重放）。裁决表是派生物，事件才是真源。
        from ._cv import EventLog
        from ._cv import rebuild_verdicts
        out = rebuild_verdicts(EventLog(), verdict_store(),
                               batches=[args.shard] if args.shard else None)
        if not args.shard:
            # 看图结论另放 feedback/vision/（overview#428），全量重建时一并重放，label_origin=vision
            from ._cv import rebuild_vision_gold
            out["vision"] = rebuild_vision_gold(store=verdict_store())
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    if args.action == "shards":
        for s in store.shards():
            d = store.summary(s)
            print(f"  {d['shard']:44s} {store.carrier(s):14s} {d['n']:5d} 条  {d['status']}")
    elif args.action == "show":
        print(json.dumps(store.summary(args.shard), ensure_ascii=False, indent=1))
    elif args.action == "migrate":
        shards = [args.shard] if args.shard else store.shards()
        for sh in shards:
            if store.items_path(sh).exists() and not args.shard:
                continue
            print(json.dumps(store.migrate(sh, dry_run=args.dry_run), ensure_ascii=False))
    elif args.action == "drift":
        from ._cv import check_shard, mark_drifted
        import cv2
        root = _cv.cv_repo()
        items = store.list(args.shard)

        def image_of(it):
            p = (it.input.get("input") or {}).get("column_image")
            if not p:
                return None
            f = root / p.replace("open-guji-cv ", "")
            return cv_imread(str(f), cv2.IMREAD_GRAYSCALE) if f.exists() else None

        rep = check_shard(args.shard, items, image_of)
        out = rep.to_dict()
        if args.apply:
            out["marked_stale"] = mark_drifted(store, args.shard, rep)
        if getattr(args, "json", False):
            print(json.dumps(out, ensure_ascii=False))
            return
        print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=1))
        if args.apply:
            print(f"标 stale: {out['marked_stale']} 条")


def add_parser(sub) -> None:
    p = sub.add_parser("events", help="[v2] 反馈事件：harvest | route | list | verdicts | import-vision | lint")
    p.add_argument("action", choices=["harvest", "route", "list", "verdicts", "import-vision", "lint"])
    p.add_argument("batch", nargs="?", default=None, help="批次名；import-vision 时是 jsonl 路径")
    p.add_argument("--file", default=None, help="收割源：审查页 HTML / JSONL / 日志")
    p.add_argument("--step", default=None)
    p.add_argument("--unit", default="page")
    p.add_argument("--kind", default="verdict")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=30)
    # import-vision（overview#428）：看图结论 jsonl → feedback/vision/
    p.add_argument("--book", default=None, help="list：只列 target.key 以 <册>: 开头的事件（批次名可带通配 *）；import-vision：只认这一册的格（给了就校验 books/<册>.yaml）")
    p.add_argument("--judge", default=None, help="import-vision：行里没写 judge 时用的模型名")
    p.add_argument("--as-batch", default=None, help="import-vision：批次名，缺省 vision-<文件名>")
    p.add_argument("--no-gold", action="store_true", help="import-vision：只写事件，不落裁决表")
    p.add_argument("--source-rev", type=int, default=None,
                   help="import-vision：结论是在哪一版页表的产物上判的，写进锚 anchor.source_rev；换过图源的册必给（须与册 yaml 相同）")
    p.add_argument("--json", action="store_true", help="lint：出机读结果")
    p = sub.add_parser("gold", help="[v2] 金标：shards | show | migrate | drift | import | export | rebuild")
    p.add_argument("action", choices=["shards", "show", "migrate", "drift", "import", "export", "rebuild"])
    p.add_argument("shard", nargs="?", default=None,
                   help="分片名；rebuild 时是批次名（留空=全部批次）")
    p.add_argument("--dry-run", action="store_true", help="migrate / import：只报数不写")
    p.add_argument("--apply", action="store_true", help="drift：把漂移条目标成 stale")
    p.add_argument("--json", action="store_true", help="drift：只出一个 JSON（含 marked_stale），控制台调用用")
    p.add_argument("--verdicts", action="store_true",
                   help="shards / show 看 workspace 裁决表而不是测试集仓")
    # import：裁决表 → 测试集的过滤条件（都可省；省了就是整个分片的 active 条目）
    p.add_argument("--book", default=None, help="import：只导这本书")
    p.add_argument("--pages", default=None, help="import：页号表达式，如 1-50,60")
    p.add_argument("--stratum", default=None, help="import：只导这个分层，如 flip_unique_top1")
    p.add_argument("--ids", default=None, help="import：id 清单文件（一行一个）")
    p.add_argument("--include-uncertain", action="store_true",
                   help="import：连 uncertain（idk）也导；默认只导 active")
    p.add_argument("--why", default="", help="import：写进 history 的理由")


#: 并进 `guji` 的子命令（同插件接口 `guji.commands`）
COMMANDS = {
    "events": (add_parser, cmd_events),
    "gold": (add_parser, cmd_gold),
}
