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
    """cv、manager 版本。cv 用 cv 自己的口径（`core.cv_version.describe`：git 检出按 tag 算，同 run 记录、产物包的
    cv_version），不用 `importlib.metadata`——可编辑安装的元数据只在重装时更新，升了版本号还报旧的（CV0 11-28 实测
    dev 0.9.16+ 报成 0.9.13）。manager 用包里的 `__version__`。"""
    out = {}
    try:
        from .._cv import core_cv_version as CVV
        out["cv"], commit = CVV.describe()
    except Exception:                                      # noqa: BLE001
        out["cv"], commit = None, None
    try:
        from .. import __version__ as mv
        out["manager"] = mv
    except Exception:                                      # noqa: BLE001
        out["manager"] = None
    try:
        import importlib.util
        out["cv_git"] = R.git_head(Path(importlib.util.find_spec("open_guji_cv").origin).resolve().parents[1]) or commit
    except Exception:                                      # noqa: BLE001
        out["cv_git"] = commit
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
    rels = [r for r in ([spec.gold_rel(book, v) for v in vols] if vols else [spec.gold_rel(book)]) if r]
    if isinstance(spec.gold, dict) and isinstance(spec.gold.get(book), dict) and not vols:
        rels = list(spec.gold[book].values())             # 册一级显式表、没点名册：整本书的分片都取
    ds = R.dataset_root(a.dataset, cache=cache, rels=rels, ref=getattr(a, "dataset_ref", None))
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
    if need & {"config", "code", "raw", "products", "glyph_lib", "corpus", "models"}:   # corpus 要册配置里的钉子
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
        pv = R.pins(ws, dh, list(plan)) if plan else {}
        if pv:
            env["pins"] = pv                               # 整份钉子与来源层（同 guji job precheck），可原样复现
        if pv and spec.mode == "run":
            bad, warn = R.drift(ws, dh, pv, env.get("cv"))
            if bad:
                raise R.Missing("code", "；".join(bad), "书仓 git pull 到含该 k 的提交，或先出新 k")
            if warn:
                env["pin_warnings"] = warn
                for w in warn:
                    print(f"    ⚠ {w}", file=sys.stderr)
        if "corpus" in need:
            if not pv:
                raise R.Missing("corpus", f"{spec.id} 没给册清单（plan 或 --vol），不知道取哪版语料")
            res["corpus"], env["corpus"] = R.corpus(ws, dh, list(plan), pv)
        if "glyph_lib" in need:
            if not plan:
                raise R.Missing("glyph_lib", f"{spec.id} 没给册清单（plan 或 --vol），不知道建哪版字形库")
            env["glyph_pin"] = R.glyph_pins(ws, dh, list(plan), pv)
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
    if "bench5b" in need:
        res["bench5b"] = str(R.bench5b())
        env["bench5b"] = "train_bundle " + __import__("guji_manager.eval.bench_bundle", fromlist=["x"]).BUNDLE_SHA256[:12]
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
        with R.lock(R.cache_root(a.cache), book):         # 同机同书备资源串行（书仓、db pull、钉版库都写同一缓存）
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
        if g["status"] not in ("ok", "n/a"):
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
        print(f"  {s.id:14s} {s.owner:5s} {s.primary:14s} {_cost(s):6s} {s.title}{dep}" + (f"  〔{flag}〕" if flag else ""))
    legacy.print_list(a)


def cmd_fetch(a) -> None:
    B = _B()
    spec = B.get(a.bench)
    work = R.cache_root(a.cache) / "work" / spec.id / a.book / "fetch"
    work.mkdir(parents=True, exist_ok=True)
    try:
        with R.lock(R.cache_root(a.cache), a.book):
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


def job_specs(a) -> list[dict]:
    """`--job`：每个 bench × 书一张 kind=bench 的单（字段见 jobs/spec.py 模块头）。cv 缺省＝本机 cv 的提交（有没提交的改动就拒，
    执行机拿不到）。"""
    cv = a.cv
    if not cv:
        g = _versions().get("cv_git") or ""
        if not g or g.endswith("+dirty"):
            sys.exit("--job 要 --cv（tag／分支／提交）：本机 cv " + ("有没提交的改动，执行机拿不到" if g else "读不出提交"))
        cv = g
    out = []
    for name in a.bench:
        for book in a.books:
            b = {"id": name, "book": book, "vols": _vols_arg(a),
                 "params": json.loads(a.params) if a.params else None,
                 "args": dict(x.split("=", 1) for x in (a.arg or [])), "label": a.label,
                 "dataset": getattr(a, "dataset_ref", None), "publish": bool(a.publish), "baseline": bool(a.baseline),
                 "note": a.note}
            out.append({"kind": "bench", "cv": cv, "bench": b, "why": a.why})
    return out


def submit_jobs(a) -> None:
    from .._cv import jobs_spec as SP
    from .._cv import jobs_store as S
    from ..jobs.cli import _actor
    if a.against or a.ws or a.dataset or a.cache or a.out or a.offline:
        sys.exit("--job 不收 --against、--ws、--dataset、--cache、--out、--offline（执行机自己备资源；对照用 guji bench ab 或事后比结果）")
    db = None
    for raw in job_specs(a):
        try:
            spec = SP.normalize(raw)
        except SP.SpecError as e:
            sys.exit(f"✗ {e}")
        h = SP.spec_hash(spec)
        if a.dry_run:
            print(json.dumps(spec, ensure_ascii=False, indent=1))
            print("指纹", h)
            continue
        db = db or S.DB()
        row = db(S.submit, spec, h, by=_actor(), why=spec.get("why"), priority=a.priority, again=a.again)
        if row["status"] == "duplicate":
            print(f"= #{row['id']} 与 #{row['duplicate_of']}（{row['dup_status']}）同一配置，不另跑；"
                  f"看结果：guji job show {row['duplicate_of']}（确要再跑加 --again）")
        else:
            print(f"已排队 #{row['id']}：{SP.summary(spec)}；看结果：guji job show {row['id']}")


def cmd_run(a) -> None:
    B = _B()
    if any(x.split("=", 1)[0] == "update" for x in (a.arg or [])):
        sys.exit("guji bench 不写正式数据：不收 --arg update（要改金标走各 bench 原来的建数据集工具）")
    if getattr(a, "job", False):
        return submit_jobs(a)
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


def _gold_books(spec, a) -> list[str] | None:
    """有金标的书。显式表直接读；约定式分片（gold 是字符串 `<分片>/<书id>/`）看测试集仓里该分片下有哪些书目录
    （以前返回 None，guard 不给 --book 就一本都不跑、给了 --book 跑成 skipped 也不算不过：GM2 11-28 补）。"""
    g = spec.gold_books()
    if g is not None or not isinstance(spec.gold, str):
        return g
    try:
        ds = R.dataset_root(a.dataset, cache=R.cache_root(a.cache), rels=[spec.gold.rstrip("/")])
    except R.Missing:
        return None
    d = ds / spec.gold.rstrip("/")
    return sorted(p.name for p in d.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))) if d.is_dir() else []


def _cost(spec, book=None) -> str:
    """cv ≥ 11-28 的 `cost_of(书)`（cost 可按书写）；旧 cv 只有字符串 `cost`。"""
    f = getattr(spec, "cost_of", None)
    return f(book) if f else spec.cost


def _dataset_guards(B, spec, book, a) -> list:
    """dataset guards/*.yaml 里登记给这个 bench＋书的护栏（cv 11-28 起框架统一判；旧 cv 没有这个函数就当没有）。"""
    f = getattr(B, "dataset_guards", None)
    if not f:
        return []
    try:
        ds = R.dataset_root(a.dataset, cache=R.cache_root(a.cache), rels=[])
    except R.Missing:
        return []
    return f(spec.id, book, ds)


def cmd_guard(a) -> None:
    """发版护栏：每个有护栏的 bench × 有金标的书；heavy 的要 --heavy。有金标却没跑成（skipped／no_gold）按不过算。"""
    B = _B()
    bad = 0
    for spec in B.all_specs():
        if spec.deprecated:
            continue
        gb = _gold_books(spec, a)
        if gb is None and not a.books:
            if spec.guards:
                print(f"✗ {spec.id}：读不到测试集仓，不知道哪些书有金标——发版护栏按不过算")
                bad = True
            continue
        books = a.books or gb or []
        for book in books:
            if _cost(spec, book) == "heavy" and not a.heavy:
                continue
            if not spec.guards and not _dataset_guards(B, spec, book, a):
                continue                                 # 没登记护栏（框架里、dataset guards/ 里都没有）
            r, out = run_one(spec, book, a, against=None)
            _print(r, out)
            _maybe_publish(a, r, out)
            bad |= r.status in ("regressed", "failed")
            unv = [g["metric"] for g in r.guards if g["status"] == "unverified"]
            if unv and r.status not in ("skipped", "no_gold"):
                print(f"    ✗ 护栏没验到（指标没出数）：{'、'.join(unv)}——发版护栏按不过算")
                bad = True
            if r.status in ("skipped", "no_gold") and gb and book in gb:
                print("    ✗ 登记了金标却没跑成，发版护栏按不过算")
                bad = True
    if a.legacy:
        bad |= legacy.guard(a)
    sys.exit(1 if bad else 0)


def cmd_show(a) -> None:
    if a.central:
        from . import publish as P
        for x in P.history(a.bench, a.book, all_status=a.all_status):
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
    p.add_argument("--dataset-ref", default=None, help="钉测试集仓版本（提交／分支）；自动取的缓存检出到那一版")
    p.add_argument("--cache", default=None, help="资源缓存根（缺省 $GUJI_DATA_HOME/bench-cache）")
    p.add_argument("--out", default=None, help="结果根（缺省 ./bench-results）")
    p.add_argument("--offline", action="store_true", help="不拉中心库、不更新书仓，只用缓存")
    p.add_argument("--step", default=None, help="list：只列量这个 Step 的")
    p.add_argument("--heavy", action="store_true", help="guard：连 heavy 级一起跑")
    p.add_argument("--legacy", action="store_true", help="guard：连老框架 guards/*.yaml 一起验（P2 前发版要带）")
    p.add_argument("--history", action="store_true", help="show：列历次（本机结果目录）")
    p.add_argument("--central", action="store_true", help="show：列中心库 bench_runs 里的历次（缺省只列 ok／regressed）")
    p.add_argument("--all-status", action="store_true", help="show --central：连 skipped／no_gold 一起列")
    p.add_argument("--publish", action="store_true", help="run／ab／guard：结果写进中心库 bench_runs（不带就只在本机）")
    p.add_argument("--baseline", action="store_true", help="配 --publish：标为基线")
    p.add_argument("--note", default=None, help="配 --publish：一句说明")
    p.add_argument("--timeout", type=int, default=900, help="老评测器超时秒数")
    p.add_argument("--job", action="store_true", help="run：不在本机跑，交任务库由执行机跑（kind=bench，结果写回任务库，"
                   "`guji job show <号>` 看）；heavy 级建议这样")
    p.add_argument("--cv", default=None, help="--job：执行机用哪版 cv（tag／分支／提交；缺省本机 cv 的提交）")
    p.add_argument("--why", default=None, help="--job：交单说明")
    p.add_argument("--priority", type=int, default=100, help="--job：优先级（小的先跑）")
    p.add_argument("--again", action="store_true", help="--job：同配置已跑过也再交一张")
    p.add_argument("--dry-run", action="store_true", help="--job：只打印要交的单，不交")


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
