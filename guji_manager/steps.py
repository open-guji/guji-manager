"""`guji` 命令按「文本化一部书」的步骤分组：`guji <步> <命令> …`（用户 2026-11-22 定）。

五步（第五步「排版输出」由 cv 原 Step9 移来：2026-11-22 定，11-23 代码整个搬进本包 `output/`）：

    start     第一步 新书启动    元数据与资源、页面分析与参数、选页试运行
    pipeline  第二步 自动化流程  跑 CV 管线、切分检查、少见字入库与 OCR 候选、形近字处理
    text      第三步 文意与知识  AI 文意判字、标点、专名
    feedback  第四步 反馈迭代    网站人审、更新 book-text、版本迭代
    output    第五步 排版输出    导出排版文本、对勘报告

`guji start source pull …` 与 `guji source pull …` 完全等价：cv 解析参数之前经 `route` 钩子（`route()`）
核对「这条命令属于这一步」，去掉前缀再解析（`-w` 校验、`--override`、钩子都照常走）。
`pipeline` 本来就是 cv 跑管线的命令：后面跟的是本步的命令名就当前缀，否则照旧是
`guji pipeline <管线> <册>`（管线名与命令名不重）。cv 没有 `route` 时点的旧版，`start`／`text`／`feedback`／`output`
靠同名子命令兜底（`make_step_handler`），`pipeline` 前缀不可用。
不属于哪一步的公共命令（`db`、`version`、`archive`、`snap`、`central-gc`、`datastore`、`console`）不加前缀。
平的旧写法继续能用（脚本、任务单都这么调），文档一律写带前缀的。

另外把原先只能 `guji-manager <命令>`／`python -m guji_manager.<模块>` 调的几条并进 `guji`（`PASSTHROUGH`）。
"""

from __future__ import annotations

import argparse
import sys

#: 步 → (中文名, 一句话, 成员命令)。成员命令名就是 `guji` 的子命令名（cv 的或本包的）。
STEPS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "start": ("第一步 新书启动", "元数据与资源、页面分析与参数、选页试运行", (
        "source", "corpus", "code", "pagekinds", "suggest", "glyphlib",
    )),
    "pipeline": ("第二步 自动化流程", "跑 CV 管线、切分检查与优化、少见字入库与 OCR 候选、形近字处理", (
        "pipeline", "step", "status", "book", "binarize", "preclean", "split", "locate-gutter", "survey",
        "calibrate", "calibrate-font", "witness-align", "witness-align-stream", "seed-witness",
        "job", "rerun", "cache", "products", "product", "snapshot",
        "seg", "round-check", "close-check", "progress", "iterate", "exp", "perf", "pending-stats",
        "eval", "check", "gold", "events", "collate",
        "glyph-db", "recheck", "triage", "review-pages", "rare", "variants", "pua-table",
        "groups", "promote", "pair-attr", "model", "font",
    )),
    "text": ("第三步 文意与知识", "AI 文意判字、标点、专名", (
        "final-review", "rulings-hits",
    )),
    "feedback": ("第四步 反馈迭代", "出单上线、收单落票、更新 book-text、升 1.0、1.0 之后的反馈", (
        "pending", "online-lists", "swap", "land", "collect", "cellvotes", "closeout", "rekey-cells",
        "exit-check", "char-diff", "audit", "freeze", "opinions", "progress-sync",
    )),
    "output": ("第五步 排版输出", "导出排版文本（md、lines.md／pages.json、维基文库、重排段落）与对勘报告", (
        "export", "collation-report",
    )),
}

#: 命令 → 所属步（反查）
STEP_OF: dict[str, str] = {c: s for s, (_, _, cs) in STEPS.items() for c in cs}


def _main_of(dotted: str):
    def run(argv: list[str]):
        import importlib
        mod, _, fn = dotted.partition(":")
        return importlib.import_module(mod).__dict__[fn or "main"](argv)
    return run


#: 并进 `guji` 的模块入口：命令名 → (模块:函数, 说明)。参数原样交给模块自己的 argparse。
PASSTHROUGH: dict[str, tuple[str, str]] = {
    "pending-stats": ("guji_manager.pending_stats:main", "全部待审格分类统计（查中心库）"),
    "central-gc": ("guji_manager.central_gc:main", "中心库定期清理（产物包按保留规则清）"),
    "triage": ("guji_manager.review_triage.__main__:main", "参校字快审分流（skip/pass/withdraw/review）"),
    "review-pages": ("guji_manager.review_pages.__main__:main", "人审页模板库（预选、一字一卡、版本、台账）"),
    "progress-sync": ("guji_manager.progress_sync:main", "后台看板自动对账（线上单、包口径、迭代轮次）"),
    "iterate": ("guji_manager.iterate.__main__:main", "降人审迭代：轮报告、金标、抽检台账、杠杆排序、冻结日历"),
    "suggest": ("guji_manager.suggest:main", "诊断信号 → 开关建议，点头后写册 yaml"),
    "pair-attr": ("guji_manager.pair_attribution:main", "形近字对归属表（刻形／文意／暂归一）查看与校验"),
    "final-review": ("guji_manager.final_review.__main__:main", "AI 文意终审跨书流水线"),
    "online-lists": ("guji_manager.online_lists:main", "线上待审单：出单、体检（--audit）、同步"),
    "datastore": ("guji_manager.datastore.__main__:main", "中心库底层：schema、导入、核对、备份"),
}


def _raw_parser(sub, name: str, help_: str):
    # prefix_chars 设成用不到的字符：后面的 `--xx` 一律当普通参数收下，交给下一层自己解析
    p = sub.add_parser(name, help=help_, add_help=False, prefix_chars="\x01")
    p.add_argument("rest", nargs="*")
    return p


def land_argv(rest: list[str]) -> list[str]:
    """``<管线> <册> -w <ws> --text-id <id> --land [cv 参数…]`` → ``land <册> -w <ws> --text-id <id> --apply --run <管线> <册> [cv 参数…]``。
    ``--text-id`` 只给 land 用，不转给 cv。"""
    args = [x for x in rest if x != "--land"]
    ws = tid = None
    cv_args: list[str] = []
    i = 0
    while i < len(args):
        x = args[i]
        if x in ("-w", "--workspace") and i + 1 < len(args):
            ws = args[i + 1]
            cv_args += args[i:i + 2]
            i += 2
        elif x == "--text-id" and i + 1 < len(args):
            tid = args[i + 1]
            i += 2
        else:
            cv_args.append(x)
            i += 1
    if len(args) < 2 or not ws or not tid:
        print("✗ guji pipeline <管线> <册> -w <工作区> --text-id <书 ID> --land：缺册、-w 或 --text-id", file=sys.stderr)
        raise SystemExit(2)
    return ["land", args[1], "-w", ws, "--text-id", tid, "--run", *cv_args]


def route(argv: list[str]) -> list[str] | None:
    """cv `route` 钩子：`guji <步> <命令> …` → `guji <命令> …`；`guji <步>`／`-h`／`commands` 列本步命令。"""
    if not argv or argv[0] not in STEPS:
        return None
    step, rest = argv[0], argv[1:]
    helpish = ("-h", "--help", "help", "commands")
    if step == "pipeline" and (not rest or (rest[0] not in STEP_OF and rest[0] not in ("help", "commands"))):
        if "--land" in rest:             # 先调 cv 跑管线，再由 manager 收尾（待审条目对账；sheldon 11-23 定：对外交互都归 manager）
            return land_argv(rest)
        return None                      # 真的跑管线：guji pipeline <管线> <册> …（-h 也给 cv 的帮助）
    if not rest or rest[0] in helpish:
        print_step_help(step)
        raise SystemExit(0)
    _check_member(step, rest[0])
    return rest


def _check_member(step: str, name: str) -> None:
    if STEP_OF.get(name) != step:
        where = f"它在 `guji {STEP_OF[name]} {name}`" if name in STEP_OF else f"它不属于哪一步，直接 `guji {name}`"
        print(f"✗ `{name}` 不是{STEPS[step][0]}的命令；{where}。本步命令见 `guji {step} commands`", file=sys.stderr)
        raise SystemExit(2)


def add_parser(sub) -> None:
    for name, (title, desc, _) in STEPS.items():
        if name in sub.choices:          # pipeline：cv 自己的命令，前缀只经 route 钩子
            continue
        _raw_parser(sub, name, f"{title}：{desc}（guji {name} -h 列出本步命令）")
    for name, (_, help_) in PASSTHROUGH.items():
        if name not in sub.choices:
            _raw_parser(sub, name, help_)


def _guji_cli():
    """`guji` 命令的入口函数（cv 装的 console_scripts）。走公开的命令行入口，不碰 cv 内部模块。"""
    from importlib.metadata import entry_points
    eps = [e for e in entry_points(group="console_scripts") if e.name == "guji"]
    return eps[0].load() if eps else None


def _guji_main(argv: list[str]) -> None:
    main = _guji_cli()
    if main is None:               # 没装 cv（只测本包）：本包自己的命令照样能跑
        from .commands import run as main
    main(argv)


def _known_commands() -> dict[str, str]:
    """当前 `guji` 认得的命令 → 一句话说明（列分组帮助用）。"""
    ap = argparse.ArgumentParser(prog="guji")
    sub = ap.add_subparsers(dest="command")
    main = _guji_cli()
    register = getattr(sys.modules.get(main.__module__), "register_subcommands", None) if main else None
    if register is not None:
        register(sub)
    else:
        from .commands import COMMANDS
        seen = set()
        for ap_, _ in COMMANDS.values():
            if ap_ not in seen:
                ap_(sub)
                seen.add(ap_)
    return {a.dest: (a.help or "") for a in sub._choices_actions}


def print_step_help(step: str, out=None) -> None:
    out = out or sys.stdout
    title, desc, members = STEPS[step]
    known = _known_commands()
    print(f"guji {step} <命令> …　　{title}：{desc}\n", file=out)
    for c in members:
        if c in known:
            print(f"  {c:<22}{known[c].removeprefix('[v2] ')}", file=out)
    missing = [c for c in members if c not in known]
    if missing:
        print(f"\n  （本机没装，不可用：{'、'.join(missing)}）", file=out)
    tail = "（`guji pipeline <管线> <册>` 仍是跑管线）" if step == "pipeline" else ""
    print(f"\n`guji {step} <命令> -h` 看某条命令的参数；与不带 `{step}` 的写法等价{tail}。", file=out)


def make_step_handler(step: str):
    def handler(args) -> None:
        rest = list(args.rest)
        if not rest or rest[0] in ("-h", "--help", "help", "commands"):
            print_step_help(step)
            return
        _check_member(step, rest[0])
        _guji_main(rest)
    return handler


def make_passthrough_handler(name: str):
    run = _main_of(PASSTHROUGH[name][0])

    def handler(args) -> None:
        rc = run(list(args.rest))
        if isinstance(rc, int) and rc:
            raise SystemExit(rc)
    return handler


COMMANDS: dict = {
    **{s: (add_parser, make_step_handler(s)) for s in STEPS if s != "pipeline"},
    **{n: (add_parser, make_passthrough_handler(n)) for n in PASSTHROUGH},
}
