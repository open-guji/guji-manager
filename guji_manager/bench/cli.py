"""`guji bench list|fetch|run|ab|guard|show`（CV0 2026-11-28）。"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

from . import legacy
from . import resources as R

STATUS_MARK = {"ok": "✓", "regressed": "⚠", "skipped": "–", "no_gold": "∅", "failed": "✗"}


def _B():
    from .._cv import bench_mod
    return bench_mod


def _versions() -> dict:
    import importlib.metadata as md
    out = {}
    for dist, key in (("open-guji-cv", "cv"), ("guji-manager", "manager")):
        try:
            out[key] = md.version(dist)
        except Exception:                                  # noqa: BLE001
            out[key] = None
    try:
        import importlib.util
        out["cv_git"] = R.git_head(Path(importlib.util.find_spec("open_guji_cv").origin).resolve().parents[1])
    except Exception:                                      # noqa: BLE001
        pass
    return out


def _vols_arg(a) -> list[str]:
    return [v for x in (a.vol or []) for v in str(x).split(",") if v]


def _results_root(a) -> Path:
    return Path(a.out).expanduser() if a.out else Path.cwd() / "bench-results"


# ------------------------------------------------------------------ 备资源
def prepare(spec, book: str, a, work: Path, params: str | None = None):
    """按 spec.needs 备齐资源。返回 BenchCtx；没金标返回 ("no_gold", 理由)；缺资源抛 R.Missing。"""
    B = _B()
    vols = _vols_arg(a)
    cache = R.cache_root(a.cache)
    res, env = {}, {**_versions(), "book": book}
    miss = R.check_env(spec.needs)
    if miss:
        raise miss[0]
    ds = R.dataset_root(a.dataset)
    res["dataset"] = str(ds)
    env["dataset"] = R.git_head(ds)
    gold = R.gold_dir(spec, book, vols, ds)
    if gold is None:
        if not spec.nogold:
            return ("no_gold", f"{spec.id} 在 {book} 上没有金标（{spec.gold_rel(book) or '登记表没这本书'}）")
    else:
        res["gold"] = str(gold)
    plan = spec.plan(gold, book, vols) if (spec.plan and gold is not None) else {v: None for v in vols}
    if gold is not None and spec.plan and not plan:
        return ("no_gold", f"{spec.id} 在 {book} 的金标里没有册 {vols}")
    need = set(spec.needs)
    if need & {"config", "code", "raw", "products", "glyph_lib", "corpus", "models"}:
        ws = R.book_ws(book, cache, a.ws, update=not a.offline)
        dh = R.data_home_for(ws, cache, a.ws)
        res["ws"], res["data_home"] = str(ws), str(dh)
        env["book_repo"] = R.git_head(ws)
        if not a.offline:
            res["data"] = str(R.central(ws, dh, glyph="glyph_lib" in need))
        else:
            from .._cv import central_marker
            m = central_marker(ws)
            res["data"] = str(dh / str((m or {}).get("branch") or "main") / str(m["ws"])) if m else str(ws)
        env["central"] = R.central_rev(dh, ws, Path(res["data"]))
        if "glyph_lib" in need:
            if not plan:
                raise R.Missing("glyph_lib", f"{spec.id} 没给册清单（plan 或 --vol），不知道建哪版字形库")
            env["glyph_pin"] = R.glyph_pins(ws, dh, list(plan))
        if "raw" in need:
            n = 0
            if not plan:
                raise R.Missing("raw", f"{spec.id} 没给册清单（plan 或 --vol），不知道取哪册原图")
            for v, pages in plan.items():
                n += R.raw(ws, dh, v, pages)              # pages 为 None＝整册
            env["raw_pulled"] = n
        if "products" in need:
            link = cache / "products" / book / f"_run-{work.name}"
            link.mkdir(parents=True, exist_ok=True)
            labels = {}
            for v in plan:
                root, lab = R.products(ws, book, v, cache, label=(a.label or None))
                (link / v).unlink(missing_ok=True) if (link / v).is_symlink() else None
                (link / v).symlink_to(root / v, target_is_directory=True)
                labels[v] = lab
            res["products"] = str(link)
            env["products"] = labels
    args = dict(x.split("=", 1) for x in (a.arg or []))
    if params:
        env["params"] = params
    return B.BenchCtx(book, list(plan) if plan else vols, work, res, pages=None,
                      params=json.loads(params) if params else None, args=args, env={**env, "args": args})


def run_one(spec, book: str, a, params: str | None = None, against: Path | None = None, tag: str = ""):
    """跑一个 bench 在一本书上，写结果目录并返回（结果, 目录）。`params`＝运行覆盖 JSON（ab 的 B 组），None＝现行。"""
    B = _B()
    stamp = time.strftime("%Y%m%d-%H%M%S") + (f"-{tag}" if tag else "")
    out = _results_root(a) / spec.id / book / stamp
    work = R.cache_root(a.cache) / "work" / spec.id / book / stamp
    work.mkdir(parents=True, exist_ok=True)
    try:
        ctx = prepare(spec, book, a, work, params=params)
    except R.Missing as e:
        ctx0 = B.BenchCtx(book, _vols_arg(a), work, {}, env=_versions())
        r = B.skipped(spec, ctx0, str(e))
        return r, B.write_result(out, r)
    if isinstance(ctx, tuple):
        r = B.skipped(spec, B.BenchCtx(book, _vols_arg(a), work, {}, env=_versions()), ctx[1], status=ctx[0])
        return r, B.write_result(out, r)
    with R.env(GUJI_DATA_HOME=ctx.res.get("data_home", ""), GUJI_WORKSPACE=ctx.res.get("ws", "")) \
            if ctx.res.get("ws") else R.env():
        try:
            r = B.execute(spec, ctx, against=against)
        except LookupError as e:
            if str(e) != "no_gold":
                raise
            r = B.skipped(spec, ctx, f"{spec.id} 在 {book} 的金标里没有点名的册", status="no_gold")
        except Exception as e:                             # noqa: BLE001  跑崩：记 failed，护栏按不过算
            import traceback
            (work / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            r = B.skipped(spec, ctx, f"{type(e).__name__}: {str(e)[-400:]}", status="failed")
    out = B.write_result(out, r)
    (out / "ctx.json").write_text(json.dumps({"res": ctx.res, "args": ctx.args, "params": ctx.params, "work": str(work)},
                                             ensure_ascii=False, indent=1), encoding="utf-8")
    return r, out


def _print(r, out: Path) -> None:
    mark = STATUS_MARK.get(r.status, "?")
    pv = r.metrics.get(r.primary)
    print(f"{mark} {r.bench} · {r.book}（{'、'.join(r.vols) or '—'}）{r.status}"
          f"{('：' + r.reason) if r.reason else ''}  {r.primary}={pv}  n={r.n}  {r.seconds:.0f}s")
    for g in r.guards:
        if g["status"] != "ok":
            print(f"    护栏 {g['metric']} {g['dir']} {g['limit']}：{g['value']} → {g['status']}")
    if r.against:
        print(f"    对照：好转 {r.against['better']}、变坏 {r.against['worse']}、其他 {r.against['other']}")
    print(f"    结果 {out}")


def _maybe_publish(a, r, out: Path) -> None:
    if not getattr(a, "publish", False) or r.status in ("failed",):
        return
    from . import publish as P
    try:
        rid = P.publish(out, baseline=a.baseline, note=a.note or "")
        print(f"    已写中心库 bench_runs：{rid}")
    except Exception as e:                                 # noqa: BLE001  结果已在本机，发布失败不算跑失败
        print(f"    ✗ 写中心库失败（{type(e).__name__}: {e}）；结果仍在本机，可再 guji bench show … 后重发")


# ------------------------------------------------------------------ 命令
def cmd_list(a) -> None:
    B = _B()
    specs = B.all_specs()
    if a.step:
        specs = [s for s in specs if a.step in s.steps]
    ds = None
    try:
        ds = R.dataset_root(a.dataset)
    except R.Missing:
        pass
    print(f"{'bench':16s} {'负责':5s} {'主指标':14s} {'代价':6s} 说明")
    for s in specs:
        flag = ""
        if a.books:
            has = ds is not None and R.gold_dir(s, a.books[0], [], ds) is not None
            miss = [m.kind for m in R.check_env(s.needs)]
            flag = ("有金标" if has else "无金标") + (f"，缺 {','.join(miss)}" if miss else "")
        dep = f" [deprecated：{s.deprecated}]" if s.deprecated else ""
        print(f"  {s.id:14s} {s.owner:5s} {s.primary:14s} {s.cost:6s} {s.title}{dep}" + (f"  〔{flag}〕" if flag else ""))
    legacy.print_list(a)


def cmd_fetch(a) -> None:
    B = _B()
    spec = B.get(a.bench)
    work = R.cache_root(a.cache) / "work" / spec.id / a.book / "fetch"
    work.mkdir(parents=True, exist_ok=True)
    try:
        ctx = prepare(spec, a.book, a, work)
    except R.Missing as e:
        print(f"– {e}")
        sys.exit(2)
    if isinstance(ctx, tuple):
        print(f"∅ {ctx[1]}")
        sys.exit(2)
    print(f"✓ {spec.id} · {a.book}：册 {'、'.join(ctx.vols) or '—'}")
    for k, v in ctx.res.items():
        print(f"    {k:10s} {v}")
    for k, v in ctx.env.items():
        print(f"    env.{k:6s} {v}")


def cmd_run(a) -> None:
    B = _B()
    if any(x.split("=", 1)[0] == "update" for x in (a.arg or [])):
        sys.exit("guji bench 不写正式数据：不收 --arg update（要改金标走各 bench 原来的建数据集工具）")
    bad = 0
    for name in a.bench:
        if legacy.is_legacy(name):
            bad |= legacy.run(name, a)
            continue
        for spec in B.expand([name]):
            for book in a.books:
                r, out = run_one(spec, book, a, params=a.params, against=Path(a.against) if a.against else None)
                _print(r, out)
                _maybe_publish(a, r, out)
                bad |= r.status in ("regressed", "failed")
    sys.exit(1 if bad else 0)


def cmd_ab(a) -> None:
    B = _B()
    spec = B.get(a.bench)
    if not a.params:
        sys.exit("guji bench ab 要 --params（B 组的运行覆盖）")
    ra, oa = run_one(spec, a.book, a, params=None, tag="A")
    _print(ra, oa)
    if ra.status not in ("ok", "regressed"):
        sys.exit(2)
    rb, ob = run_one(spec, a.book, a, params=a.params, against=oa, tag="B")
    _print(rb, ob)
    _maybe_publish(a, rb, ob)
    sys.exit(1 if (rb.against or {}).get("worse") else 0)


def cmd_guard(a) -> None:
    """发版护栏：每个有护栏的 bench × 登记了金标的书；heavy 的要 --heavy。"""
    B = _B()
    bad = 0
    for spec in B.all_specs():
        if not spec.guards or spec.deprecated or (spec.cost == "heavy" and not a.heavy):
            continue
        books = a.books or spec.gold_books() or []
        for book in books:
            r, out = run_one(spec, book, a, against=None)
            _print(r, out)
            _maybe_publish(a, r, out)
            bad |= r.status in ("regressed", "failed")
    if a.legacy:
        bad |= legacy.guard(a)
    sys.exit(1 if bad else 0)


def cmd_show(a) -> None:
    if a.central:
        from . import publish as P
        for x in P.history(a.bench, a.book):
            print(f"  {x['ran_at']}  {x['status']:9s} {x['primary_name']}={x['primary_value']}  n={x['n']}  "
                  f"cv={x['cv']}{'  [基线]' if x['baseline'] else ''}  {x['by'] or ''}")
        return
    root = _results_root(a) / a.bench / a.book
    runs = sorted(p for p in root.glob("*") if (p / "result.json").exists()) if root.exists() else []
    if not runs:
        sys.exit(f"没有 {a.bench} · {a.book} 的结果（{root}）")
    if a.history:
        for p in runs:
            d = json.loads((p / "result.json").read_text(encoding="utf-8"))
            print(f"  {p.name}  {d['status']:9s} {d['primary']['name']}={d['primary']['value']}  n={d['n']}  "
                  f"cv={d['env'].get('cv')}")
        return
    print((runs[-1] / "report.md").read_text(encoding="utf-8"))


def cmd_bench(a) -> None:
    {"list": cmd_list, "fetch": cmd_fetch, "run": cmd_run, "ab": cmd_ab, "guard": cmd_guard, "show": cmd_show}[a.action](a)


def add_parser(sub) -> None:
    p = sub.add_parser("bench", help="benchmark 统一入口：list | fetch | run | ab | guard | show（按书自动备资源）")
    p.add_argument("action", choices=["list", "fetch", "run", "ab", "guard", "show"])
    p.add_argument("bench", nargs="*", help="bench id 或 @套名（list、guard 不用）")
    p.add_argument("--book", dest="books", action="append", default=None, help="书 id（工作区 id），可多给")
    p.add_argument("--vol", action="append", default=None, help="只跑这几册（逗号分隔或多给）")
    p.add_argument("--params", default=None, help="运行覆盖 JSON（ab：B 组参数）")
    p.add_argument("--arg", action="append", default=None, metavar="k=v", help="bench 自己的参数，如 set=large")
    p.add_argument("--against", default=None, help="对照的上次结果目录（出好转／变坏清单）")
    p.add_argument("--label", default=None, help="产物包标签（缺省各册 main 指针）")
    p.add_argument("--ws", default=None, help="用本机现成的书仓／工作区，不克隆（不改它）")
    p.add_argument("--dataset", default=None, help="测试集仓（缺省 GUJI_DATASET_DIR 或 cv 旁边的 open-guji-dataset）")
    p.add_argument("--cache", default=None, help="资源缓存根（缺省 $GUJI_DATA_HOME/bench-cache）")
    p.add_argument("--out", default=None, help="结果根（缺省 ./bench-results）")
    p.add_argument("--offline", action="store_true", help="不拉中心库、不更新书仓，只用缓存")
    p.add_argument("--step", default=None, help="list：只列量这个 Step 的")
    p.add_argument("--heavy", action="store_true", help="guard：连 heavy 级一起跑")
    p.add_argument("--legacy", action="store_true", help="guard：连老框架 guards/*.yaml 一起验（P2 前发版要带）")
    p.add_argument("--history", action="store_true", help="show：列历次（本机结果目录）")
    p.add_argument("--central", action="store_true", help="show：列中心库 bench_runs 里的历次")
    p.add_argument("--publish", action="store_true", help="run／ab／guard：结果写进中心库 bench_runs（不带就只在本机）")
    p.add_argument("--baseline", action="store_true", help="配 --publish：标为基线")
    p.add_argument("--note", default=None, help="配 --publish：一句说明")
    p.add_argument("--timeout", type=int, default=900, help="老评测器超时秒数")


def _fix(a):
    if a.action in ("fetch", "show", "ab") and len(a.bench) != 1:
        sys.exit(f"guji bench {a.action} 要且只要一个 bench")
    if a.action in ("fetch", "show", "ab", "run") and not a.books and not (a.action == "run" and all(legacy.is_legacy(b) for b in a.bench)):
        sys.exit(f"guji bench {a.action} 要 --book")
    if a.action in ("fetch", "show", "ab"):
        a.bench = a.bench[0]
        a.book = a.books[0]
    return a


def main(a) -> None:
    cmd_bench(_fix(a))


COMMANDS = {"bench": (add_parser, main)}
