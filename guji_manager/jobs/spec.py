"""任务定义（spec）：规整、校验、算指纹。纯函数，不连库、不跑命令（解析 cv 引用除外，见 `resolve_cv`）。

一条任务就是一个 JSON 对象。提交时规整成全字段的标准形（缺省值补齐、cv 引用解析成 40 位提交），
再算 `spec_hash`：同一指纹 = 同一次计算，只跑一次（重复提交记成 duplicate，指向已有那条）。

    kind            rerun（重跑一册，可接对比）| ab（同 rerun，必须给 compare_to）| eval | command（一串 guji 命令）
                    | roundcheck（收轮检查，只读：见下 roundcheck 与 guji_manager/round_check.py）
                    | bench（跑一个 benchmark：见下 bench 与 doc/2-自动化流程/bench统一入口.md）
    book            册，如 vol10（eval 可空）
    cv              tag／分支／提交；提交时解析成 40 位提交（cv_ref 留原文）
    pipeline        缺省 keben_body_v2
    steps           {"from": 起步, "to": 止步}，缺省整条
    pages           缺省 all
    force           缺省 true（重跑就是要重算）；no_reuse 缺省跟 force
    book_overrides  {"corpus": N, "glyph_pin": N}：执行会话里叠在册配置上的运行覆盖（GUJI_BOOK_OVERRIDE），不改册 yaml、不推中心库
    pin_args        guji corpus pin 的参数串（追加语料钉子账）
    base            先取哪个产物包铺底：main｜包标签｜null；从中间某步起跑缺省 main
    checks          {"human_chars": N}：开跑前人裁绑定后必须正好 N 格，不对就 blocked 不跑
    env             只收 GUJI_ 开头、不像凭据的变量
    params          guji pipeline --params 的 JSON 对象
    compare_to      跑完和谁比：main｜包标签｜{"job": 任务号}
    output          {"change": 包改动名, "note": 说明, "pack": true}；永不标 main
    run             command／eval 用：[[guji 子命令, 参数…], …]，可用 {book} {ws}
    ws_glob         缺省 96mid1ogzk-*（殿本工作区）
    ws_repo         <owner>/<repo>：这部书自己一个仓（仓根即工作区）；缺省按 ws_glob 里的册 ID 查 WS_REPOS，查不到走 open-guji/guji-workspace 里 ws_glob 匹配的目录
    glyph_diff      rerun／ab：改钉字形库后只重算受影响的格——旧的钉号 N（新号写 book_overrides.glyph_pin）。
                    铺底包后先 `guji recheck <册> --glyph-diff N` 点名，再从 glyph_match 起增量跑；
                    缺省 steps.from=glyph_match、force=false（定字层增量跟进，A32 精校前移 A4，2026-10-30）

    roundcheck      kind=roundcheck 用：{"pack": 候选包标签（必给）, "main": "main"｜包标签, "ledger_book": 台账书名,
                    "ledger": 台账 TSV 全文（交单时从 ai-team main 取、只留本书行）, "ledger_src": 来源, "allow": premain 放行清单 TSV 全文,
                    "config": 分层配置覆盖 {order, cov_min, lib_min, seg_defect}（盖过执行机 workspace.yaml 的 round_check 段；
                    执行机的 workspace.yaml 是 db pull 落的中心库版本，不是书仓检出的）}。
                    执行方：取 main 包 seg check → 取候选包 seg check → seg gate → seg premain → 待审按 pending_reason 计数归四层，
                    结果写回任务结果（check: seg_gate／seg_premain；output: pending_by_reason／roundcheck）。不存包、不推库

    bench           kind=bench 用：{"id": bench id（必给）, "book": 书 id（10 位工作区 id，必给）, "vols": [册…], "params": 运行覆盖,
                    "args": {k: v}（bench 自己的参数）, "label": 产物包标签, "dataset": 测试集仓提交／分支,
                    "publish": 写中心库 bench_runs, "baseline": 配 publish 标基线, "note": 配 publish 一句话}。
                    执行方跑 `guji bench run`（资源自动备齐，见 guji_manager/bench/resources.py），把 result.json、report.md、
                    items.jsonl（截断）写回任务结果。**不存包、不推库、永不标 main**：task 的 book 留空、不收 base／compare_to／run，
                    output.pack 强制 false。状态 ok／regressed／no_gold 算成功（结论照实写在结果里），skipped（执行机缺资源）
                    记 blocked，跑崩记 failed

    db_rev          提交时中心库的 rev（整数）；`guji job submit` 自动填（连不上库就不填）。进指纹：册 yaml 等改了、spec 没变的单
                    不再被判成重复（11-05 史記 #831/#833）。不给就不出这个键：老任务的指纹不变

不进指纹：why、priority、output（换个包名也是同一次计算）、cv_ref（已解析成提交）。
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess

KINDS = ("rerun", "ab", "eval", "command", "roundcheck", "uidsync", "bench")   # bench：跑一个 benchmark（只读，结果写回任务库）   # uidsync：只把 base 包入字格身份账（自检交的单）
STATUSES = ("queued", "running", "succeeded", "failed", "blocked", "cancelled", "duplicate")
ACTIVE = ("queued", "running")
CV_REPO = "https://github.com/open-guji/open-guji-cv"
DEFAULT_PIPELINE = "keben_body_v2"
DEFAULT_WS_GLOB = "96mid1ogzk-*"
# 册 ID → 这部书自己的工作区仓（仓根即工作区）。ws_glob 的册 ID 在表里、又没显式给 ws_repo 时用它（2026-10-30 起）。
WS_REPOS = {"96mid1ogzk": "guji-workspace/96mid1ogzk-si-ku-zong-mu",
            "988g3f0wsu": "guji-workspace/988g3f0wsu-shi-ji-wen-yuan-ge",   # 史記文淵閣本（2026-10-31）
            "995ejelvk0": "guji-workspace/995ejelvk0-quan-tang-wen"}       # 全唐文（2026-11-20：roundcheck 单只给 --book-id、新执行机没克隆就备不了工作区）


def book_id(spec: dict) -> str | None:
    """这条任务属于哪部书（book-index 的 10 位 Book ID）：任务里的 `book` 只是册号（vol01），
    不同书的 vol01 是两回事，同册并跑的锁、按册过滤、板子显示都要带上它。取 ws_glob 里第一个 `-` 之前那段。"""
    g = (spec.get("ws_glob") or DEFAULT_WS_GLOB).split("-", 1)[0]
    return g if re.match(r"^[0-9a-z]{10}$", g) else None

#: command／eval 的 run 里允许的 guji 子命令。不收会推库、改中心库、标 main 的（db、promote 等）。
RUN_SUBCOMMANDS = frozenset({
    "pipeline", "step", "recheck", "status", "eval", "collate", "cache", "corpus", "glyph-db", "source",
    "products", "close-check", "gold", "report", "product", "seg",
})
#: 有些子命令只许其中几个只读的二级命令（seg pin --write 会写数据目录里的钉子，不进任务单）
RUN_SUBSUBCOMMANDS = {"seg": frozenset({"check", "ruler"})}
#: run 里不许出现的参数（推中心库、标 main）
RUN_FORBIDDEN_ARGS = frozenset({"--main", "promote", "push", "push-index", "sync", "migrate"})
_ENV_KEY = re.compile(r"^GUJI_[A-Z0-9_]+$")
_ENV_SECRETISH = re.compile(r"TOKEN|SECRET|KEY|PASS|DSN|URL|AUTH", re.I)
_STEP = re.compile(r"^[a-z][a-z0-9_]*$")
_BOOK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_OVERRIDES = {"corpus": int, "glyph_pin": int, "model": int}     # 有类型要求的几个；其余册级字段不限类型（执行方 `--override` 原样叠上去）


def _override_keys() -> set[str]:
    """能覆盖的册级字段：BookSpec 的字段，去掉身份与图源（`core/book_config.FORBIDDEN_IN_OVERRIDE`）。"""
    import dataclasses
    from .._cv import BookSpec
    from .._cv import FORBIDDEN_IN_OVERRIDE
    return {f.name for f in dataclasses.fields(BookSpec)} - FORBIDDEN_IN_OVERRIDE
_KEYS = {"kind", "book", "cv", "cv_ref", "pipeline", "steps", "pages", "force", "no_reuse", "book_overrides",
         "pin_args", "base", "checks", "env", "params", "compare_to", "output", "run", "ws_glob", "ws_repo", "why",
         "glyph_diff", "db_rev", "roundcheck", "bench", "manager_min", "manager_min_n"}
_NOT_HASHED = ("why", "output", "cv_ref", "ws_repo", "manager_min", "manager_min_n")      # ws_repo 只是去哪个仓取工作区，不改计算（册 ID 由 ws_glob 定）


class SpecError(ValueError):
    """任务定义不合规。消息直接给提交人看。"""


def normalize(raw: dict, *, resolve=None) -> dict:
    """规整成标准形并校验；`resolve(ref) -> 40 位提交` 缺省 `resolve_cv`（测试里传假的）。"""
    if not isinstance(raw, dict):
        raise SpecError("任务定义要是 JSON 对象")
    extra = set(raw) - _KEYS
    if extra:
        raise SpecError(f"不认识的字段：{', '.join(sorted(extra))}（可用：{', '.join(sorted(_KEYS))}）")
    s = copy.deepcopy(raw)
    kind = s.get("kind") or "rerun"
    if kind not in KINDS:
        raise SpecError(f"kind 只能是 {'/'.join(KINDS)}，不是 {kind!r}")
    s["kind"] = kind
    book = s.get("book")
    if kind in ("rerun", "ab", "roundcheck", "uidsync") and not book:
        raise SpecError(f"{kind} 要给 book（册，如 vol10）")
    if book is not None and not (isinstance(book, str) and _BOOK.match(book)):
        raise SpecError(f"book 不合规：{book!r}")
    s["book"] = book or None

    ref = s.get("cv_ref") or s.get("cv")
    if not ref or not isinstance(ref, str):
        raise SpecError("要给 cv（tag、分支或提交，如 v0.5.16、dev、1ed2599）：跑哪版代码必须写明")
    s["cv_ref"] = ref
    s["cv"] = ref if _HEX40.match(ref) else (resolve or resolve_cv)(ref)
    if not _HEX40.match(s["cv"] or ""):
        raise SpecError(f"cv {ref!r} 解析不出 40 位提交")

    s["pipeline"] = s.get("pipeline") or DEFAULT_PIPELINE
    gd = s.get("glyph_diff")
    if gd is not None:
        if kind not in ("rerun", "ab"):
            raise SpecError("glyph_diff 只给 rerun／ab 用")
        if isinstance(gd, bool) or not isinstance(gd, int) or gd < 0:
            raise SpecError("glyph_diff 是改钉前的字形库号（整数）")
        new_pin = (s.get("book_overrides") or {}).get("glyph_pin")
        if not isinstance(new_pin, int) or isinstance(new_pin, bool) or new_pin == gd:
            raise SpecError("glyph_diff 要配 book_overrides.glyph_pin（改钉后的新号，整数，与旧号不同）")
        s.setdefault("steps", {"from": "glyph_match", "to": None})
        s.setdefault("force", False)
        s["glyph_diff"] = gd
    else:
        s.pop("glyph_diff", None)      # 不给就不出这个键：老任务的指纹不变
    dr = s.get("db_rev")
    if dr is not None:
        if isinstance(dr, bool) or not isinstance(dr, int) or dr < 0:
            raise SpecError("db_rev 是中心库 rev（非负整数）")
    else:
        s.pop("db_rev", None)
    st = s.get("steps") or {}
    if not isinstance(st, dict) or set(st) - {"from", "to"}:
        raise SpecError('steps 写成 {"from": 起步, "to": 止步}')
    for k in ("from", "to"):
        if st.get(k) is not None and not _STEP.match(str(st[k])):
            raise SpecError(f"steps.{k} 不像步骤 id：{st[k]!r}")
    s["steps"] = {"from": st.get("from"), "to": st.get("to")}
    pages = s.get("pages", "all")
    if not isinstance(pages, str) or not re.match(r"^(all|dev_set|[0-9][0-9,\-]*)$", pages):
        raise SpecError(f"pages 只能是 all、dev_set 或 3-6,9 这样的页号：{pages!r}")
    s["pages"] = pages
    s["force"] = bool(s.get("force", True))
    s["no_reuse"] = bool(s.get("no_reuse", s["force"]))

    ov = s.get("book_overrides") or {}
    if not isinstance(ov, dict):
        raise SpecError("book_overrides 要是 JSON 对象")
    bad = set(ov) - _override_keys()
    if bad:
        raise SpecError(f"book_overrides 不收 {', '.join(sorted(bad))}（身份与图源只能改册 yaml；可覆盖的见 doc/design/册配置分层与运行覆盖.md）")
    try:
        s["book_overrides"] = {k: (_OVERRIDES[k](v) if k in _OVERRIDES else v)
                               for k, v in sorted(ov.items()) if v is not None}
    except (TypeError, ValueError):
        raise SpecError("book_overrides 里 corpus、glyph_pin 的值要是整数") from None
    pa = s.get("pin_args")
    if pa is not None and (not isinstance(pa, str) or re.search(r"[;&|`$<>\n]", pa)):
        raise SpecError("pin_args 是一串普通参数，不能带 shell 符号")
    s["pin_args"] = pa or None

    base = s.get("base", "main" if s["steps"]["from"] else None)
    if base is not None and not (isinstance(base, str) and _LABEL.match(base)):
        raise SpecError(f"base 是 main 或包标签：{base!r}")
    s["base"] = base

    ck = s.get("checks") or {}
    if not isinstance(ck, dict) or set(ck) - {"human_chars"}:
        raise SpecError("checks 目前只收 human_chars")
    if "human_chars" in ck and not isinstance(ck["human_chars"], int):
        raise SpecError("checks.human_chars 要是整数")
    s["checks"] = dict(sorted(ck.items()))

    env = s.get("env") or {}
    if not isinstance(env, dict):
        raise SpecError("env 要是对象")
    for k, v in env.items():
        if not _ENV_KEY.match(k) or _ENV_SECRETISH.search(k):
            raise SpecError(f"env 只收 GUJI_ 开头、不是凭据的变量：{k}（凭据由执行会话自己的环境给）")
        if not isinstance(v, (str, int, float, bool)):
            raise SpecError(f"env.{k} 要是字符串或数字")
    s["env"] = {k: str(v) for k, v in sorted(env.items())}

    params = s.get("params")
    if params is not None and not isinstance(params, dict):
        raise SpecError("params 要是 JSON 对象（同 guji pipeline --params）")
    s["params"] = params or None

    cmp_ = s.get("compare_to")
    if isinstance(cmp_, dict):
        if set(cmp_) != {"job"} or not isinstance(cmp_["job"], int):
            raise SpecError('compare_to 是 main、包标签，或 {"job": 任务号}')
    elif cmp_ is not None and not (isinstance(cmp_, str) and _LABEL.match(cmp_)):
        raise SpecError(f"compare_to 不合规：{cmp_!r}")
    if kind == "ab" and not cmp_:
        raise SpecError("ab 要给 compare_to（和谁比）")
    s["compare_to"] = cmp_

    out = s.get("output") or {}
    if not isinstance(out, dict) or set(out) - {"change", "note", "pack"}:
        raise SpecError("output 只收 change、note、pack")
    if out.get("change") is not None and not _LABEL.match(str(out["change"])):
        raise SpecError(f"output.change 只能用 ASCII 字母数字和 ._-：{out['change']!r}")
    s["output"] = {"change": out.get("change"), "note": out.get("note"),
                   "pack": bool(out.get("pack", kind in ("rerun", "ab")))}

    run = s.get("run")
    if kind in ("command", "eval"):
        if kind == "eval" and not run:
            run = [["eval", "run", "--json"]]
        if not run:
            raise SpecError("command 要给 run：[[guji 子命令, 参数…], …]")
        s["run"] = [_check_argv(a) for a in run]
    elif run:
        raise SpecError("run 只给 command／eval 用；rerun 用 steps／pages／params")
    else:
        s["run"] = None
    s["roundcheck"] = _check_roundcheck(s.get("roundcheck"), kind)
    if s["roundcheck"] is None:
        s.pop("roundcheck")             # 不给就不出这个键：老任务的指纹不变
    elif s["base"] or s["compare_to"] or s["output"]["pack"]:
        raise SpecError("roundcheck 自己取包、只读：不收 base、compare_to，不存包")
    s["bench"] = _check_bench(s.get("bench"), kind)
    if s["bench"] is None:
        s.pop("bench")                  # 不给就不出这个键：老任务的指纹不变
    elif s["book"] or s["base"] or s["compare_to"] or s["run"] or s["output"]["pack"]:
        raise SpecError("bench 单只读：册写在 bench.vols、书写在 bench.book；不收 book、base、compare_to、run，不存包")
    if kind == "uidsync":
        if not s["base"] or s["base"] == "main":
            raise SpecError("uidsync 要给 base＝要入账的 main 包标签（同册同标签只跑一次）")
        if s["compare_to"] or s["output"]["pack"] or s["run"]:
            raise SpecError("uidsync 只入身份账：不收 compare_to、run，不存包")
    s["ws_glob"] = s.get("ws_glob") or DEFAULT_WS_GLOB
    if not re.match(r"^[A-Za-z0-9_*.-]+$", s["ws_glob"]):
        raise SpecError(f"ws_glob 不合规：{s['ws_glob']!r}")
    s["ws_repo"] = s.get("ws_repo") or None
    if s["ws_repo"] and not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", s["ws_repo"]):
        raise SpecError(f"ws_repo 不合规（要 owner/repo）：{s['ws_repo']!r}")
    if not s["ws_repo"]:
        s["ws_repo"] = WS_REPOS.get(book_id(s) or "")
    s["why"] = s.get("why") or None
    s.pop("manager_min_n", None)              # 由 manager_min 推，不收手填
    if s.get("manager_min"):
        s["manager_min_n"] = version_n(s["manager_min"])
    else:
        s.pop("manager_min", None)            # 没给就不写进单子：旧单的标准形不变
    return s


def version_n(v: str) -> int:
    """manager 版本 `X.Y.Z` → 整数 X*1e6+Y*1e3+Z，任务库领单时按它比大小（SQL 里不好比字符串版本）。"""
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", str(v or "").strip())
    if not m:
        raise SpecError(f"manager_min 要写 X.Y.Z，不是 {v!r}")
    a, b, c = (int(x) for x in m.groups())
    if b >= 1000 or c >= 1000:
        raise SpecError(f"manager_min 每段要小于 1000：{v!r}")
    return a * 1_000_000 + b * 1000 + c


_BENCH_KEYS = {"id", "book", "vols", "params", "args", "label", "dataset", "publish", "baseline", "note"}
_BENCH_ID = re.compile(r"^@?[a-z0-9][a-z0-9_-]*$")


def _check_bench(b, kind: str) -> dict | None:
    if kind != "bench":
        if b is not None:
            raise SpecError("bench 只给 kind=bench 用")
        return None
    if not isinstance(b, dict) or set(b) - _BENCH_KEYS:
        raise SpecError(f"bench 要是对象，只收 {', '.join(sorted(_BENCH_KEYS))}")
    if not (isinstance(b.get("id"), str) and _BENCH_ID.match(b["id"])):
        raise SpecError(f"bench.id 是 bench id 或 @套名：{b.get('id')!r}")
    if not (isinstance(b.get("book"), str) and _BOOK.match(b["book"])):
        raise SpecError(f"bench.book 是书 id（工作区 id，如 988g3f0wsu）：{b.get('book')!r}")
    vols = b.get("vols") or []
    if isinstance(vols, str):
        vols = [v for v in vols.split(",") if v]
    if not isinstance(vols, list) or not all(isinstance(v, str) and _BOOK.match(v) for v in vols):
        raise SpecError(f"bench.vols 是册号列表：{vols!r}")
    params = b.get("params")
    if params is not None and not isinstance(params, dict):
        raise SpecError("bench.params 要是 JSON 对象（运行覆盖）")
    args = b.get("args") or {}
    if not isinstance(args, dict) or not all(isinstance(k, str) and re.match(r"^[a-z][a-z0-9_]*$", k) for k in args):
        raise SpecError("bench.args 是 {参数名: 值}")
    if "update" in args:
        raise SpecError("bench 不写正式数据：args 不收 update")
    for k in ("label", "dataset"):
        if b.get(k) is not None and not (isinstance(b[k], str) and _LABEL.match(b[k])):
            raise SpecError(f"bench.{k} 不合规：{b[k]!r}")
    if b.get("note") is not None and not isinstance(b["note"], str):
        raise SpecError("bench.note 要是字符串")
    out = {"id": b["id"], "book": b["book"], "vols": vols, "params": params or None,
           "args": {k: str(v) for k, v in sorted(args.items())}, "label": b.get("label") or None,
           "dataset": b.get("dataset") or None, "publish": bool(b.get("publish")),
           "baseline": bool(b.get("baseline")), "note": b.get("note") or None}
    if out["baseline"] and not out["publish"]:
        raise SpecError("bench.baseline 要配 publish")
    return out


_RC_KEYS = {"pack", "main", "ledger_book", "ledger", "ledger_src", "allow", "config"}


def _check_roundcheck(rc, kind: str) -> dict | None:
    if kind != "roundcheck":
        if rc is not None:
            raise SpecError("roundcheck 只给 kind=roundcheck 用")
        return None
    if not isinstance(rc, dict) or set(rc) - _RC_KEYS:
        raise SpecError(f"roundcheck 要是对象，只收 {', '.join(sorted(_RC_KEYS))}")
    pack, main = rc.get("pack"), rc.get("main") or "main"
    for k, v in (("pack", pack), ("main", main)):
        if not (isinstance(v, str) and _LABEL.match(v)):
            raise SpecError(f"roundcheck.{k} 是包标签（main 可写 main）：{v!r}")
    if pack == "main":
        raise SpecError("roundcheck.pack 是候选包标签，不能是 main")
    for k in ("ledger_book", "ledger", "ledger_src", "allow"):
        if rc.get(k) is not None and not isinstance(rc[k], str):
            raise SpecError(f"roundcheck.{k} 要是字符串")
    if rc.get("ledger") and not rc.get("ledger_book"):
        raise SpecError("roundcheck 带了 ledger 就要给 ledger_book（台账里的书名：殿本／史記／全唐文）")
    out = {"pack": pack, "main": main, "ledger_book": rc.get("ledger_book") or None, "ledger": rc.get("ledger") or None,
           "ledger_src": rc.get("ledger_src") or None, "allow": rc.get("allow") or None}
    if rc.get("config"):                # 分层配置覆盖（盖过执行机工作区 workspace.yaml 的 round_check 段）；不给不出键，老指纹不变
        from ..round_check import parse_config
        try:
            out["config"] = parse_config(rc["config"])
        except ValueError as e:
            raise SpecError(f"roundcheck.config：{e}") from None
    return out


def _check_argv(a) -> list[str]:
    if not isinstance(a, list) or not a or not all(isinstance(x, (str, int, float)) for x in a):
        raise SpecError(f"run 里每条是参数列表（不经 shell），如 [\"eval\", \"run\"]：{a!r}")
    a = [str(x) for x in a]
    if a[0] == "guji":
        a = a[1:]
    if not a or a[0] not in RUN_SUBCOMMANDS:
        raise SpecError(f"run 只许这些 guji 子命令：{', '.join(sorted(RUN_SUBCOMMANDS))}（不是 {a[:1]}）")
    sub2 = RUN_SUBSUBCOMMANDS.get(a[0])
    if sub2 is not None and (len(a) < 2 or a[1] not in sub2):
        raise SpecError(f"run 里 {a[0]} 只许 {'／'.join(sorted(sub2))}（不是 {a[1:2]}）")
    if a[0] == "products" and len(a) > 1 and a[1] == "pack" and (len(a) < 3 or a[2] not in ("fetch", "list")):
        raise SpecError("run 里 products pack 只许 fetch／list；存包写 output.pack")
    bad = RUN_FORBIDDEN_ARGS.intersection(a[1:])
    if bad:
        raise SpecError(f"run 里不许 {', '.join(sorted(bad))}（推中心库、标 main 要用户亲口说）")
    return a


def spec_hash(spec: dict) -> str:
    """标准形去掉不进指纹的字段后，按键排序的 JSON 的 sha256。"""
    core = {k: v for k, v in spec.items() if k not in _NOT_HASHED}
    blob = json.dumps(core, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def resolve_cv(ref: str, repo: str = CV_REPO, local: str | None = "/opt/guji-cv-seed") -> str:
    """tag／分支／短提交 → 40 位提交。先问远端（tag 取剥开后的提交），短提交再问本机仓。"""
    try:
        out = subprocess.run(["git", "ls-remote", repo, ref, f"refs/tags/{ref}^{{}}"],
                             capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    rows = [ln.split("\t") for ln in out.splitlines() if "\t" in ln]
    for want in (f"refs/tags/{ref}^{{}}", f"refs/heads/{ref}", f"refs/tags/{ref}", ref):
        for sha, name in rows:
            if name == want:
                return sha
    if re.match(r"^[0-9a-f]{7,40}$", ref) and local:
        for args in (["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],):
            try:
                r = subprocess.run(["git", "-C", local, *args], capture_output=True, text=True, timeout=60)
                if r.returncode != 0:
                    subprocess.run(["git", "-C", local, "fetch", "-q", "origin", "dev", "main"],
                                   capture_output=True, timeout=300)
                    r = subprocess.run(["git", "-C", local, *args], capture_output=True, text=True, timeout=60)
            except (OSError, subprocess.SubprocessError):
                break
            if r.returncode == 0 and _HEX40.match(r.stdout.strip()):
                return r.stdout.strip()
    raise SpecError(f"cv {ref!r} 在 {repo} 找不到（tag、分支名，或已推上去的提交）")


def summary(spec: dict) -> str:
    """一行概要，给 ls 用。"""
    if spec["kind"] in ("command", "eval"):
        body = " ; ".join(" ".join(a) for a in spec["run"] or [])
    elif spec["kind"] == "bench":
        b = spec["bench"]
        body = f"bench {b['id']} · {b['book']}" + (f"（{','.join(b['vols'])}）" if b["vols"] else "") \
            + "".join(f" {k}={v}" for k, v in b["args"].items()) + (" +params" if b["params"] else "") \
            + (" 发布" if b["publish"] else "")
    elif spec["kind"] == "roundcheck":
        rc = spec["roundcheck"]
        body = f"收轮检查 {rc['pack']} 对 {rc['main']}" + (f" 台账 {rc['ledger_book']}" if rc.get("ledger") else " 无台账") \
            + "".join(f" {k}={v}" for k, v in (rc.get("config") or {}).items())
    else:
        st = spec["steps"]
        body = f"{spec['pipeline']} {st['from'] or '头'}→{st['to'] or '尾'} {spec['pages']}"
        if spec["book_overrides"]:
            body += " " + ",".join(f"{k}={v}" for k, v in spec["book_overrides"].items())
        if spec["env"]:
            body += " " + ",".join(f"{k}={v}" for k, v in spec["env"].items())
        if spec["compare_to"]:
            c = spec["compare_to"]
            body += f" 比 {'#' + str(c['job']) if isinstance(c, dict) else c}"
    if spec.get("manager_min"):
        body += f" 需 manager≥{spec['manager_min']}"
    return f"cv {spec['cv_ref']}({spec['cv'][:7]}) {body}"
