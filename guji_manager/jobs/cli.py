"""`guji job`：任务库命令行（也可 `python -m guji_manager.jobs …`，云端用 `guji_jobs …`）。

    guji job submit <spec.json|->            # 交一条任务（JSON，字段见 jobs/spec.py 模块头）
    guji job submit --book vol10 --cv v0.5.16 --from seed_admit --corpus 16 --change seed-c16 --why "…"
    guji job submit --kind roundcheck --book 046 --book-id 995ejelvk0 --cv v0.7.80 --rc-pack <候选包> --rc-ledger-book 全唐文
                                             # 收轮检查（只读）；结果收成一份：guji round-check --collect <号段> --out 目录
    guji job ls [--book vol10] [--status queued,running] [--all]   # 谁在跑什么、排了什么
    guji job show <号> [--json] [--log]      # 定义、每次领单、进展流水、结果（包在哪）
    guji job wait <号>                       # 等到它结束（成功退出码 0）
    guji job cancel <号> | bump <号> [--priority 10] | retry <号>
    guji job work [--once] [--idle 分钟]     # 执行方：领单跑单（只在云端执行会话里用）
    guji job init                            # 建表（幂等）

连库：美国机任务库（JOBSDB_TOKEN＋JOBSDB_PASSWORD，guji_jobs 会自动载入）。提交人名字取 GUJI_JOBS_WHO（如 A24）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from .._cv import jobs_spec as SP
from .._cv import jobs_store as S

_ICON = {"queued": "…", "running": "▶", "succeeded": "✓", "failed": "✗", "blocked": "■", "cancelled": "–",
         "duplicate": "="}


def add_parser(sub) -> argparse.ArgumentParser:
    p = sub.add_parser("job", help="任务库：交重跑／评测任务、看谁在跑什么、结果在哪（Neon jobs schema）")
    fill(p)
    return p


def fill(p: argparse.ArgumentParser) -> None:
    js = p.add_subparsers(dest="job_action", required=True)
    s = js.add_parser("submit", help="交一条任务")
    s.add_argument("file", nargs="?", help="spec JSON 文件，- 为标准输入；不给就用下面的参数拼")
    s.add_argument("--kind", default=None, choices=SP.KINDS)
    s.add_argument("--book", default=None, help="册号（vol10），不同书的册号会重名，配 --book-id")
    s.add_argument("--book-id", default=None, help="书 ID（book-index 的 10 位 Book ID）；缺省 96mid1ogzk（殿本四库总目）")
    s.add_argument("--cv", default=None, help="tag／分支／提交（必填）")
    s.add_argument("--ws-repo", default=None, help="书仓 owner/repo（仓根即工作区）；缺省按 --book-id 查 jobs/spec.py 的 WS_REPOS")
    s.add_argument("--pipeline", default=None)
    s.add_argument("--from", dest="from_step", default=None)
    s.add_argument("--to", dest="to_step", default=None)
    s.add_argument("--pages", default=None,
                   help="页集（3-6,9／all／auto）。不写时：从 context_decide／seed_admit 起的纯重放、cv 同铺底包、没改配置，"
                        "就自动只跑铺底包之后有新人裁／AI 裁定的页（auto）；其余整册")
    s.add_argument("--no-force", action="store_true", help="不加 --force（按指纹能跳就跳）")
    s.add_argument("--corpus", type=int, default=None)
    s.add_argument("--glyph-pin", type=int, default=None)
    s.add_argument("--glyph-diff", type=int, default=None,
                   help="改钉字形库后只重算受影响的格：旧钉号（新号用 --glyph-pin）；缺省从 glyph_match 起、不 force")
    s.add_argument("--base", default=None, help="铺底包：main｜标签；从中间某步起跑缺省 main")
    s.add_argument("--human-chars", type=int, default=None, help="开跑前人裁格数必须等于它")
    s.add_argument("--env", action="append", default=[], help="K=V，只收 GUJI_ 开头")
    s.add_argument("--params", default=None, help="guji pipeline --params 的 JSON")
    s.add_argument("--override", default=None, help='册配置片段 JSON（写进 book_overrides，运行时叠在册 yaml 上，不改文件不推库），如 \'{"cv_version":"0.5.21","corpus":23}\'')
    s.add_argument("--compare-to", default=None, help="main｜包标签｜job:<号>")
    s.add_argument("--change", default=None, help="存包改动名（缺省 job<号>）")
    s.add_argument("--note", default=None)
    s.add_argument("--no-pack", action="store_true", help="跑完不存包")
    s.add_argument("--run", action="append", default=[], help="command／eval：一条 guji 命令（引号括起，可多次）")
    s.add_argument("--why", default=None, help="为什么跑（谁要、要回答什么问题）")
    s.add_argument("--rc-pack", default=None, help="收轮检查（--kind roundcheck）：候选包标签")
    s.add_argument("--rc-main", default=None, help="收轮检查：对照包，main（缺省）或包标签")
    s.add_argument("--rc-ledger-book", default=None, help="收轮检查：根因台账里的书名（殿本／史記／全唐文）；给了就带台账")
    s.add_argument("--rc-ledger", default=None,
                   help="收轮检查：台账来源，缺省 auto＝交单时从 ai-team main 取最新（本机要有 ai-team 克隆或 gh）；也可给本地 TSV；none 不带")
    s.add_argument("--rc-set", action="append", default=None, metavar="KEY=VAL",
                   help="收轮检查：盖过执行机 workspace.yaml 的 round_check 段（可多次）：seg_defect=true、order=seg,group,lib、cov_min=0.9、lib_min=5")
    s.add_argument("--rc-allow", default=None, help="收轮检查：seg premain 放行清单 TSV（本地文件，随单带上）")
    s.add_argument("--priority", type=int, default=100, help="越小越先，缺省 100；插队给 10")
    s.add_argument("--after", type=int, action="append", default=[], help="等这条任务成功后再跑（可多次）")
    s.add_argument("--again", action="store_true", help="同配置已跑过也再跑一次")
    s.add_argument("--no-base-check", action="store_true", help="不核 base 包在不在（缺省交单前查 R2，查到没有就拒）")
    s.add_argument("--dry-run", action="store_true", help="只打印规整后的定义和指纹，不交")

    s = js.add_parser("ls", help="列任务")
    s.add_argument("--book", default=None)
    s.add_argument("--book-id", default=None, help="书 ID（book-index 的 10 位 Book ID，如 96mid1ogzk）")
    s.add_argument("--status", default=None, help="逗号分隔，缺省 排队+在跑+最近结束的")
    s.add_argument("--mine", action="store_true")
    s.add_argument("--all", action="store_true")
    s.add_argument("--limit", type=int, default=30)
    s.add_argument("--json", action="store_true")

    s = js.add_parser("show", help="看一条任务")
    s.add_argument("id", type=int)
    s.add_argument("--json", action="store_true")
    s.add_argument("--log", action="store_true", help="带最后一次的日志尾巴")

    s = js.add_parser("wait", help="等一条任务结束")
    s.add_argument("id", type=int)
    s.add_argument("--timeout", type=int, default=0, help="最多等几秒，0 不限")

    for name, h in (("cancel", "取消／停下"), ("retry", "失败、拦下、取消的重新排队")):
        s = js.add_parser(name, help=h)
        s.add_argument("id", type=int)
    s = js.add_parser("bump", help="改优先级（插队）")
    s.add_argument("id", type=int)
    s.add_argument("--priority", type=int, default=10)

    s = js.add_parser("work", help="执行方：领单跑单，缺省跑到队列空；常驻用 --idle")
    s.add_argument("--once", action="store_true", help="只跑一条")
    s.add_argument("--id", type=int, default=None, help="只跑这一条")
    s.add_argument("--idle", type=float, default=0, help="队列空了再等几分钟有没有新单")
    s.add_argument("--kinds", default=None, help="只接这些 kind，逗号分隔")
    s.add_argument("--dry-run", action="store_true", help="只打印要跑的命令（仍会领单、记库，测试分支上用）")

    s = js.add_parser("board", help="把任务整理成表写进后台「重跑任务」栏（progress.metric）；--dry-run 只打印")
    s.add_argument("--dry-run", action="store_true")
    s = js.add_parser("workers", help="列执行方：谁在线、空闲还是在跑哪条")
    s.add_argument("--all", action="store_true", help="连已离线的也列")

    js.add_parser("init", help="建表（幂等）")

    s = js.add_parser("precheck", help="交单前逐册核生效的 cv_version／code／glyph_pin／corpus／model（与来源层）；不连任务库")
    s.add_argument("--books", required=True, help="vol01-vol20｜001-045｜vol03,vol07｜all")
    s.add_argument("--cv", default=None, help="本轮要钉的 cv 版本（如 0.7.58）")
    s.add_argument("--code", default=None, help="本轮要钉的书级代码号（3 或 k3）")
    s.add_argument("--glyph-pin", default=None, help="本轮要钉的字形库号（24 或 g24）")
    s.add_argument("--corpus", default=None, help="本轮要钉的语料号（27 或 b27 写数字）")

    s = js.add_parser("stats", help="按轮统计一本书的时间账：排队（首领−交单）、真运行、失联次数与耗时、失败三分类")
    s.add_argument("--book-id", default=None, help="书 ID；不给统计全部")
    s.add_argument("--by", choices=["why", "change"], default="why", help="轮次取 why 里的轮号（史記、全唐文）或存包改动名（殿本）")
    s.add_argument("--last", type=int, default=0, help="只列最近几轮")
    s.add_argument("--limit", type=int, default=2000, help="最多取多少单")
    s.add_argument("--from-json", default=None, help="读 `guji_jobs ls --all --json` 的导出（不连库；没有逐次领单，退回任务级时间）")
    s.add_argument("--json", action="store_true")


def _spec_from_args(a) -> dict:
    if a.file:
        raw = json.load(sys.stdin) if a.file == "-" else json.loads(Path(a.file).read_text(encoding="utf-8"))
    else:
        raw = {}
    put = lambda k, v: raw.__setitem__(k, v) if v is not None else None  # noqa: E731
    put("kind", a.kind)
    put("book", a.book)
    if getattr(a, "book_id", None):
        put("ws_glob", f"{a.book_id}-*")
    put("cv", a.cv)
    put("ws_repo", getattr(a, "ws_repo", None))
    put("pipeline", a.pipeline)
    put("pages", a.pages)
    put("base", a.base)
    put("why", a.why)
    put("glyph_diff", getattr(a, "glyph_diff", None))
    if a.from_step or a.to_step:
        raw["steps"] = {**raw.get("steps", {}), **{k: v for k, v in (("from", a.from_step), ("to", a.to_step)) if v}}
    if a.no_force:
        raw["force"] = False
    ov = {k: v for k, v in (("corpus", a.corpus), ("glyph_pin", a.glyph_pin)) if v is not None}
    if ov:
        raw["book_overrides"] = {**raw.get("book_overrides", {}), **ov}
    if getattr(a, "override", None):
        raw["book_overrides"] = {**raw.get("book_overrides", {}), **json.loads(a.override)}
    if a.human_chars is not None:
        raw["checks"] = {**raw.get("checks", {}), "human_chars": a.human_chars}
    if a.env:
        raw["env"] = {**raw.get("env", {}), **dict(e.split("=", 1) for e in a.env)}
    if a.params:
        raw["params"] = json.loads(a.params)
    if a.compare_to:
        raw["compare_to"] = {"job": int(a.compare_to[4:])} if a.compare_to.startswith("job:") else a.compare_to
    out = dict(raw.get("output") or {})
    if a.change:
        out["change"] = a.change
    if a.note:
        out["note"] = a.note
    if a.no_pack:
        out["pack"] = False
    if out:
        raw["output"] = out
    if a.run:
        import shlex
        raw["run"] = [shlex.split(r) for r in a.run]
        raw.setdefault("kind", "command")
    rc_args = (a.rc_pack, a.rc_main, a.rc_ledger_book, a.rc_ledger, a.rc_allow, a.rc_set)
    if any(v is not None for v in rc_args) or raw.get("kind") == "roundcheck":
        raw.setdefault("kind", "roundcheck")
        raw["roundcheck"] = _roundcheck_from_args(a, dict(raw.get("roundcheck") or {}))
    return raw


def _roundcheck_from_args(a, rc: dict) -> dict:
    """收轮检查单：台账、放行清单在交单这台机器上读好，全文随单带给执行方（执行机不连 ai-team）。"""
    from ..round_check import fetch_ledger, filter_ledger
    for k, v in (("pack", a.rc_pack), ("main", a.rc_main), ("ledger_book", a.rc_ledger_book)):
        if v is not None:
            rc[k] = v
    src = a.rc_ledger or ("auto" if rc.get("ledger_book") and not rc.get("ledger") else None)
    if src == "none":
        rc.pop("ledger", None)
        rc.pop("ledger_src", None)
    elif src:
        if not rc.get("ledger_book"):
            raise SP.SpecError("带台账要给 --rc-ledger-book（台账里的书名）")
        if src == "auto":
            try:
                text, rc["ledger_src"] = fetch_ledger()
            except RuntimeError as e:
                raise SP.SpecError(str(e)) from None
        else:
            text, rc["ledger_src"] = Path(src).read_text(encoding="utf-8"), f"file:{Path(src).name}"
        rc["ledger"] = filter_ledger(text, rc["ledger_book"])
    if a.rc_allow:
        rc["allow"] = Path(a.rc_allow).read_text(encoding="utf-8")
    if a.rc_set:
        from ..round_check import parse_sets
        try:
            rc["config"] = {**(rc.get("config") or {}), **parse_sets(a.rc_set)}
        except ValueError as e:
            raise SP.SpecError(str(e)) from None
    return rc


def _fmt_time(t) -> str:
    """洛杉矶时间（团队规矩）。"""
    from zoneinfo import ZoneInfo
    return t.astimezone(ZoneInfo("America/Los_Angeles")).strftime("%m-%d %H:%M") if t else "-"


_FAILED = ("failed", "blocked", "cancelled")
_REASON_MAX = 160
_TAG = {"failed": "失败原因", "blocked": "拦下原因", "cancelled": "取消", "queued": "上次失败"}


def _reason(j: dict) -> str | None:
    """失败／拦下的一行原因（库里 error 列，执行方收尾时写的）。排队中的单是上次失败留下的原因。"""
    err = " ".join((j.get("error") or "").split())
    if not err or j["status"] not in _FAILED + ("queued",):
        return None
    return err if len(err) <= _REASON_MAX else err[:_REASON_MAX - 1] + "…"


_KEY = re.compile(r"✗|⚠|^[\w.]*(Error|Exception|Drift)[:：]|退出码|\b404\b|not found")


def _log_key_lines(tail: str, n: int = 8) -> list[str]:
    """失败单日志尾巴里的要点行（✗、⚠、报错、Drift…），去重保序取最后 n 行。
    殿本 #5834–5836 只显示「glyph_match 返回码 1」，真原因（语料 variants.tsv 漂移）埋在 --log 里（11-20 痛点 D14）。"""
    seen, out = set(), []
    for ln in tail.splitlines():
        t = ln.strip()
        if t and _KEY.search(t) and t not in seen:
            seen.add(t)
            out.append(t[:300])
    return out[-n:]


def _line(j: dict) -> str:
    sp = j["spec"]
    st = j["status"] + (f"→#{j['duplicate_of']}" if j.get("duplicate_of") else "")
    where = f" @{j.get('worker')}" if j["status"] == "running" and j.get("worker") else ""
    stage = f" [{j['stage']}]" if j["status"] == "running" and j.get("stage") else ""
    pri = f" p{j['priority']}" if j["status"] == "queued" and j["priority"] != 100 else ""
    if j["status"] == "queued" and j.get("run_after"):
        pri += f" 冷却到 {_fmt_time(j['run_after'])}（第 {j['attempts']} 次环境失败后）"
    head = (f"{_ICON.get(j['status'], '?')} #{j['id']:<4} {st:<10} {j['kind']:<7} {(j.get('book_id') or '-'):<10} {(j['book'] or '-'):<6} "
            f"{SP.summary(sp)}{pri}{stage}{where}  {j['submitted_by']} {_fmt_time(j['created_at'])}")
    why = _reason(j)
    return head if why is None else f"{head}\n      ↳ {_TAG[j['status']]}：{why}"


def _base_missing(spec: dict) -> str | None:
    """base 写了具体包标签的，交单前查 R2 有没有这个包；没有就拒（殿本 #5278 base 写成 c35、实为 c36，
    到执行机才 404 一直冷却重试，11-20 痛点 D13）。main／没给 base、查不了（本机没工作区、连不上）都放过，只提示。"""
    base, book = spec.get("base"), spec.get("book")
    if not base or base == "main" or not book:
        return None
    try:
        from ..datastore.packs import list_packs
        names = {r["name"].rsplit("/", 1)[-1] for r in list_packs(book)}
    except BaseException as e:  # noqa: BLE001 —— 没配工作区（SystemExit）也接住
        print(f"提示：没核 base 包 {book}/{base} 在不在（{str(e)[:120]}）", file=sys.stderr)
        return None
    if names and base not in names:
        near = sorted(n for n in names if n[:1] == base[:1])[-5:]
        return f"base 包 {book}/{base} 在 R2 里没有；这册最近的同类包：{' '.join(near) or '无'}"
    return None


def _central_rev() -> int | None:
    """中心库当前 rev（进指纹，册配置改了的单不被判重复）；连不上返回 None 并提示（退回旧指纹，要重跑就加 --again）。"""
    try:
        from ..datastore.connect import connect
        from ..datastore.importer import current_rev
        with connect() as conn, conn.cursor() as cur:
            return int(current_rev(cur))
    except BaseException as e:  # noqa: BLE001 —— SystemExit（没配连库）也接住
        print(f"⚠ 取不到中心库 rev（{type(e).__name__}），指纹不含册配置版本；只改了册配置的单请加 --again", file=sys.stderr)
        return None


def cmd_job(a) -> None:
    act = a.job_action
    if act == "submit":
        try:
            raw = _spec_from_args(a)
            from .auto_pages import resolve as _auto_pages
            _auto_pages(raw)            # 缺省只重放受影响的页（用户 11-20 定）；--pages all 整册
            if raw.get("db_rev") is None:
                rev = _central_rev()
                if rev is not None:
                    raw["db_rev"] = rev
            spec = SP.normalize(raw)
        except SP.SpecError as e:
            sys.exit(f"✗ {e}")
        if not getattr(a, "no_base_check", False):
            bad = _base_missing(spec)
            if bad:
                sys.exit(f"✗ {bad}（确定要交加 --no-base-check）")
        h = SP.spec_hash(spec)
        if a.dry_run:
            print(json.dumps(spec, ensure_ascii=False, indent=1))
            print("指纹", h)
            return
        db = S.DB()
        row = db(S.submit, spec, h, by=S.who(), why=spec.get("why"), priority=a.priority,
                 depends_on=a.after, again=a.again)
        if row["status"] == "duplicate":
            print(f"= #{row['id']} 与 #{row['duplicate_of']}（{row['dup_status']}）同一配置，不另跑；"
                  f"看结果：guji job show {row['duplicate_of']}（确要再跑加 --again）")
        else:
            print(f"已排队 #{row['id']}：{SP.summary(spec)}；看进展：guji job show {row['id']}")
            try:        # 空闲执行方不再刷新看板，交单时补一次，新单才会出现在后台表里
                from . import board
                board.publish(db, force=True)
            except Exception:       # noqa: BLE001 —— 看板写不上不影响交单
                pass
        return
    if act == "precheck":
        from .precheck import main as _precheck
        sys.exit(_precheck(a))
    if act == "stats":
        from .stats import main as _stats
        sys.exit(_stats(a))
    db = S.DB()
    if act == "init":
        db(S.init)
        print("jobs schema 已就绪")
    elif act == "ls":
        status = a.status.split(",") if a.status else (None if a.all else None)
        rows = db(S.list_jobs, status=status, book=a.book, book_id=a.book_id, limit=a.limit, mine=S.who() if a.mine else None)
        if not a.all and not a.status:
            rows = [r for r in rows if r["status"] in SP.ACTIVE] + \
                   [r for r in rows if r["status"] not in SP.ACTIVE][:10]
        if a.json:
            print(json.dumps(rows, ensure_ascii=False, default=str, indent=1))
            return
        live = db(S.live_workers)
        ws = [w for w in db(S.workers) if w["online"]]
        idle = sum(1 for w in ws if w["state"] == "idle")
        print(f"排队 {db(S.queue_depth)} 条，在跑 {len(live)} 条" +
              (f"（{'、'.join(sorted({w['worker'] for w in live}))}）" if live else "") +
              f"；执行方在线 {len(ws)} 个（空闲 {idle}）")
        for r in rows:
            print(_line(r))
    elif act == "show":
        j = db(S.detail, a.id)
        if j is None:
            sys.exit(f"✗ 没有 #{a.id}")
        if a.json:
            print(json.dumps(j, ensure_ascii=False, default=str, indent=1))
            return
        print(_line(j))
        if j.get("why"):
            print("为什么：", j["why"])
        if j.get("progress") and j["status"] == "running":
            print("进展：", j["progress"])
        if j.get("error"):
            print("错误：", j["error"])
        if j["status"] in _FAILED and j["attempts_rows"]:
            last = j["attempts_rows"][-1]
            keys = _log_key_lines(last.get("log_tail") or "")
            if keys:
                print("日志要点：\n  " + "\n  ".join(keys))
            print(f"看日志：guji_jobs show {j['id']} --log（第 {last['n']} 次领单的尾巴，执行方 {last['worker']}；"
                  f"完整日志只在执行方机器上）")
        print("定义：", json.dumps(j["spec"], ensure_ascii=False))
        for t in j["attempts_rows"]:
            print(f"  第{t['n']}次 {t['worker']} {t.get('session') or ''} {_fmt_time(t['started_at'])}"
                  f"→{_fmt_time(t['finished_at'])} {t['outcome'] or '在跑'} 心跳 {_fmt_time(t['heartbeat_at'])}")
        for e in j["events"]:
            secs = f" {e['secs']:.0f}s" if e.get("secs") else ""
            print(f"  {_fmt_time(e['at'])} {e['level']:<5} {e['stage'] or '':<8} {e['msg']}{secs}")
        for r in j["results"]:
            d = r.get("data") or {}
            extra = d.get("report_head", "")[:600] or d.get("tail", "")[-600:] or json.dumps(d, ensure_ascii=False)
            print(f"  结果 {r['kind']} {r['name']} {r.get('location') or ''}\n    " + extra.replace("\n", "\n    "))
        if a.log and j["attempts_rows"]:
            print("── 日志尾巴 ──\n" + (j["attempts_rows"][-1].get("log_tail") or ""))
    elif act == "wait":
        t0 = time.time()
        while True:
            j = db(S.get, a.id)
            if j is None:
                sys.exit(f"✗ 没有 #{a.id}")
            if j["status"] == "duplicate":
                a.id = j["duplicate_of"]
                continue
            if j["status"] not in SP.ACTIVE:
                print(_line(j))
                sys.exit(0 if j["status"] == "succeeded" else 1)
            if a.timeout and time.time() - t0 > a.timeout:
                print(_line(j))
                sys.exit(2)
            time.sleep(60)
    elif act == "board":
        from . import board
        t = board.publish(db, force=True, dry=a.dry_run)
        if t is None:
            sys.exit("✗ 看板没写成（连库失败或中心库还没有 progress schema）")
        if a.dry_run:
            for r in t["rows"]:
                print(f"#{r['id']:<4} {r['status']:<4} {r['bookid']:<10} {r['book']:<6} {r['elapsed']:<8} {r['eta']:<14} {r['config']}")
        print(f"{'（只看，没写）' if a.dry_run else '已写入 progress.metric jobs/board'}：共 {len(t['rows'])} 行")
    elif act == "workers":
        rows = db(S.workers)
        for w in rows:
            if not (w["online"] or a.all):
                continue
            st = {"idle": "空闲", "busy": f"在跑 #{w['job_id']}", "stopped": "已停"}[w["state"]] if w["online"] or \
                w["state"] == "stopped" else "离线"
            print(f"{'●' if w['online'] else '○'} {w['name']:<14} {st:<10} 领过 {w['done']} 条  "
                  f"上线 {_fmt_time(w['started_at'])}  最近 {_fmt_time(w['seen_at'])}  runner {w.get('runner') or '?'}"
                  f"  {w.get('session') or ''}" + (f"\n    ⚠ {w['note']}" if w["online"] and w.get("note") else ""))
        if not any(w["online"] for w in rows):
            print("（没有在线的执行方）")
    elif act == "cancel":
        print(db(S.cancel, a.id, S.who()))
    elif act == "bump":
        print("已改" if db(S.bump, a.id, a.priority, S.who()) else "✗ 只有排队中的能改优先级")
    elif act == "retry":
        print("已重新排队" if db(S.retry, a.id, S.who()) else "✗ 只有失败、拦下、取消的能重排")
    elif act == "work":
        from .runner import work
        work(once=a.once, only=a.id, idle_minutes=a.idle, kinds=a.kinds.split(",") if a.kinds else None,
             dry=a.dry_run, say=lambda m: print(m, flush=True))


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="guji_jobs", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    fill(p)
    cmd_job(p.parse_args(argv))


#: 并进 `guji` 的子命令（同插件接口 `guji.commands`；cv 侧由 `cli_v2.MANAGER_CLI_MODULES` 登记，拆分 P1）
COMMANDS = {"job": (add_parser, cmd_job)}
