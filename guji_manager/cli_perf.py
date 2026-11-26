"""`guji perf`：看跑批耗时（`core/perf.py` 写的本机记录）。不跑 Step，不进任何 Step 的 `code_deps`。

    guji perf top  [--days 7] [--book 册] -w <工作区>     # 各步合计：哪一步花的机器时间最多
    guji perf show <册> [--run ID] -w <工作区>            # 一次运行（缺省最新一次）各步明细与最慢的页
    guji perf pages <册> <步> [--slowest 20] [--run ID]    # 这一步最慢的页及其分段

    guji perf spans <步> [--remote] [--days 7]           # 这一步的分段（步内各道关、缓存再生）排行

    guji perf top --remote [--by host|cv_version|book]   # 全队（任务库），先列任务阶段（prep/run/push/uid…），再按四大步列各步
    guji perf push [--book 册]                           # 补推没推上的本机记录
    guji perf job <单号>                                 # 一条任务单的各步耗时

各步按 cv 四大步（版面 layout／切字 cut／识字 read／定字 decide，取自 cv 管线骨架 `stages:`）分组，闸归它挂的那一步。
记录在产物根旁边的 `perf/<册>/<run_id>.jsonl`（`GUJI_PERF_DIR` 可改）。连得上任务库（D1 guji-jobs，见 databases.toml
``[jobs]``）时每次运行写完自动推一份汇总到 `perf_run`／`perf_step`（约 15 KB），**不推中心库**；跑测试时不推。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def _root(args) -> Path:
    if getattr(args, "workspace", None):
        os.environ["GUJI_WORKSPACE"] = str(Path(args.workspace).expanduser().resolve())
    from ._cv import perf_dir
    from ._cv import default_products_root
    return perf_dir(default_products_root())


def _fmt_s(x) -> str:
    if x is None:
        return "-"
    if x >= 3600:
        return f"{x / 3600:.1f}h"
    if x >= 120:
        return f"{x / 60:.1f}m"
    return f"{x:.1f}s" if x >= 10 else f"{x:.2f}s"


def _pick(rs: list[dict], run: str | None) -> dict:
    if not rs:
        print("✗ 没有耗时记录（跑过 guji pipeline／step 才有）", file=sys.stderr)
        sys.exit(1)
    if run:
        hit = [r for r in rs if r["run"]["run_id"].startswith(run)]
        if not hit:
            print(f"✗ 没有运行 {run}", file=sys.stderr)
            sys.exit(1)
        return hit[0]
    return rs[0]


#: 不在任何管线里的步（测试里的合成步、已退役的步）归这一组
OTHER = "其他"
#: 已从管线里拿掉、但任务库里还有记录的步（看历史时仍归对大步）
RETIRED_STAGE = {"row_segment_gate": "cut"}
STAGE_TITLE = {"layout": "1 版面", "cut": "2 切字", "read": "3 识字", "decide": "4 定字", OTHER: "其他"}


def stage_map() -> dict[str, str]:
    """步 id → cv 大步名（layout/cut/read/decide），取自 cv 各条管线的 `stages:`；闸（如 cut_gate、border_detect_gate）
    归它挂的那一步所在的大步。cv 太旧（没有 stages）或读不到管线时只剩退役步表，其余各步都归「其他」。"""
    out: dict[str, str] = dict(RETIRED_STAGE)
    try:
        from ._cv import STEPS, list_pipelines, load_pipeline
    except Exception:  # noqa: BLE001
        return out
    for pid in list_pipelines():
        try:
            pl = load_pipeline(pid)
        except Exception:  # noqa: BLE001
            continue
        for stage, ids in (getattr(pl, "stages", None) or {}).items():
            for sid in ids:
                out.setdefault(sid, stage)
                g = STEPS[sid].spec.gate if sid in STEPS else None
                if g:
                    out.setdefault(g.id, stage)
    return out


def _by_stage(rows: list[dict], key: str = "wall_s") -> list[tuple[str, float, list[dict]]]:
    """把各步行按大步分组：[(大步, 合计, [行…])]，大步按管线顺序，组内按 `key` 从大到小。"""
    smap = stage_map()
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(smap.get(r["step"], OTHER), []).append(r)
    order = [s for s in STAGE_TITLE if s in groups] + [s for s in groups if s not in STAGE_TITLE]
    return [(s, sum(float(r.get(key) or 0) for r in groups[s]),
             sorted(groups[s], key=lambda r: -float(r.get(key) or 0))) for s in order]


def regen_of(spans: dict[str, float]) -> dict[str, float]:
    """分段里的冷缓存再生：缓存图不在、由产出它的 Step 现算（`<Step类>.render`，见 `_render_hooks`）。
    只取最外层那一次（里面嵌套的上游再生已含在内）→ {Step类.render: 秒}。"""
    out: dict[str, float] = {}
    for k, v in spans.items():
        parts = k.split("/")
        idx = [i for i, x in enumerate(parts) if x.endswith(".render")]
        if idx and idx[0] == len(parts) - 1:
            out[parts[-1]] = out.get(parts[-1], 0.0) + v
    return out


def cmd_top(args) -> None:
    from ._cv import core_perf as perf
    if args.remote:
        _remote_top(args)
        return
    rs = perf.runs(_root(args), args.book, since=time.time() - args.days * 86400)
    rows = perf.top(rs)
    if args.json:
        print(json.dumps({"runs": len(rs), "steps": rows}, ensure_ascii=False, indent=1))
        return
    total = sum(r["wall_s"] for r in rows) or 1.0
    print(f"近 {args.days} 天 {len(rs)} 次运行" + (f"（{args.book}）" if args.book else "") + "，按四大步分组、组内按墙钟排：")
    print(f"{'步':<22}{'墙钟':>8}{'占比':>6}{'跑页':>7}{'跳过':>7}{'每页中位':>9}{'最慢页':>8}  主进程开销")
    for stage, sub, grp in _by_stage(rows):
        print(f"── {STAGE_TITLE.get(stage, stage)}  {_fmt_s(sub)}  {sub / total:.0%}")
        for r in grp:
            ov = "，".join(f"{k} {_fmt_s(v)}" for k, v in sorted(r["overhead"].items(), key=lambda kv: -kv[1])[:3])
            print(f"  {r['step']:<20}{_fmt_s(r['wall_s']):>8}{r['wall_s'] / total:>6.0%}{r['pages_run']:>7}"
                  f"{r['skipped']:>7}{_fmt_s(r['p50_s']):>9}{_fmt_s(r['max_s']):>8}  {ov}")
    regen: dict[str, float] = {}
    for r in rows:
        for k, v in regen_of(r["spans"]).items():
            regen[k] = regen.get(k, 0.0) + v
    if regen:
        print("冷缓存再生（计算秒，已含在上面各步里）：" + "，".join(
            f"{k.removesuffix('.render')} {_fmt_s(v)}" for k, v in sorted(regen.items(), key=lambda kv: -kv[1])))


def _remote_top(args) -> None:
    from .jobs import perf_push
    if not perf_push.enabled():
        print("✗ --remote 要设 JOBSDB_TOKEN 连得上任务库（databases.toml [jobs]）", file=sys.stderr)
        sys.exit(2)
    rows = perf_push.remote_top(args.days, args.book, args.by)
    phases = perf_push.remote_phases(args.days, args.book)
    if args.json:
        smap = stage_map()
        for r in rows:
            r["stage"] = smap.get(r["step"], OTHER)
        print(json.dumps({"phases": phases, "steps": rows}, ensure_ascii=False, indent=1, default=str))
        return
    ptotal = float(sum(p["secs"] or 0 for p in phases)) or 1.0
    print(f"任务库近 {args.days} 天" + (f"（{args.book}）" if args.book else "") + "。任务阶段（执行方记的，run＝跑 cv 管线）：")
    try:
        parts = perf_push.remote_prep_parts(args.days, args.book)
    except Exception:  # noqa: BLE001 —— 老库没有这类事件、Postgres 没 json 权限等：只是少一段明细
        parts = []
    for p in phases:
        print(f"  {p['stage']:<12}{_fmt_s(float(p['secs'] or 0)):>8}{float(p['secs'] or 0) / ptotal:>6.0%}"
              f"{p['n']:>7} 次  平均 {_fmt_s(float(p['avg_s'] or 0))}  最长 {_fmt_s(float(p['max_s'] or 0))}")
        if p["stage"] == "prep" and parts:
            print("     其中（执行方 11-25 起记的分段）：" + "，".join(
                f"{q['part']} {_fmt_s(float(q['secs'] or 0))}" for q in parts[:8]))
    total = float(sum(r["wall_s"] or 0 for r in rows)) or 1.0
    print("\nrun 里各步，按四大步分组、组内按墙钟排：")
    head = f"{'步':<22}" + (f"{args.by:<24}" if args.by else "")
    print(head + f"{'墙钟':>8}{'占比':>6}{'次数':>6}{'跑页':>8}{'每页中位':>9}{'最慢页':>8}")
    for stage, sub, grp in _by_stage(rows):
        print(f"── {STAGE_TITLE.get(stage, stage)}  {_fmt_s(sub)}  {sub / total:.0%}")
        for r in grp:
            w = float(r["wall_s"] or 0)
            print(f"  {r['step']:<20}" + (f"{r['grp_key']!s:<24}" if args.by else "")
                  + f"{_fmt_s(w):>8}{w / total:>6.0%}{r['runs']:>6}{r['pages_run']:>8}"
                  f"{_fmt_s(float(r['p50_s']) if r['p50_s'] is not None else None):>9}"
                  f"{_fmt_s(float(r['max_s']) if r['max_s'] is not None else None):>8}")


def cmd_push(args) -> None:
    from .jobs import perf_push
    ok, bad = perf_push.push_pending(_root(args), args.book)
    print(f"推了 {ok} 份" + (f"，{bad} 份坏文件跳过" if bad else "") + "（任务库 perf_run／perf_step）")


def cmd_job(args) -> None:
    from .jobs import perf_push
    if not perf_push.enabled():
        print("✗ 要设 JOBSDB_TOKEN 连得上任务库（databases.toml [jobs]）", file=sys.stderr)
        sys.exit(2)
    rows = perf_push.remote_job(args.job_id)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1, default=str))
        return
    if not rows:
        print(f"任务 #{args.job_id} 没有耗时记录（执行方要用带 perf 的 cv）")
        return
    last = None
    for r in rows:
        if r["run_id"] != last:
            last = r["run_id"]
            print(f"\n{r['run_id']}  {r['book']}  {r['host']}  cv {r['cv_version']}  墙钟 {_fmt_s(r['run_wall_s'])}")
        if r["step"]:
            print(f"   {r['step']:<22} 跑 {r['ok']} 跳 {r['skipped']} 失败 {r['failed']}  墙钟 {_fmt_s(r['wall_s'])}"
                  f"  每页中位 {_fmt_s(r['p50_s'])}  最慢 {_fmt_s(r['max_s'])}")


def cmd_show(args) -> None:
    from ._cv import core_perf as perf
    r = _pick(perf.runs(_root(args), args.book), args.run)
    if args.json:
        print(json.dumps({k: r[k] for k in ("run", "steps", "end")}, ensure_ascii=False, indent=1))
        return
    run, m = r["run"], r["run"].get("machine") or {}
    wall = (r["end"] or {}).get("wall_s")
    print(f"{run['run_id']}  {run['book']}  {run.get('pipeline')}  cv {run.get('cv_version')}  "
          f"墙钟 {_fmt_s(wall)}{'（中断）' if r['end'] is None or r['end'].get('stopped') else ''}")
    print(f"机器 {m.get('host')}（{m.get('kind')}，{m.get('cpus')} 核，{m.get('mem_gb')} GB）  --jobs {run.get('jobs')}"
          + (f"  任务库 #{run['job_id']}" if run.get("job_id") else ""))
    for s in r["steps"]:
        print(f"\n== {s['step']}：跑 {s.get('ok', 0)} 页、跳过 {s.get('skipped', 0)}、失败 {s.get('failed', 0)}；"
              f"墙钟 {_fmt_s(s['wall_s'])}，每页中位 {_fmt_s(s.get('p50_s'))} p90 {_fmt_s(s.get('p90_s'))} "
              f"最慢 {_fmt_s(s.get('max_s'))}" + (f"，并行效率 {s['parallel_eff']:.0%}" if s.get("parallel_eff") else ""))
        if s.get("overhead"):
            print("   主进程：" + "，".join(f"{k} {_fmt_s(v)}" for k, v in s["overhead"].items()))
        for k, v in sorted((s.get("spans") or {}).items(), key=lambda kv: -kv[1][1])[:8]:
            print(f"   {k:<30} {v[0]:>6} 次 {_fmt_s(v[1]):>8}")
        if s.get("counts"):
            print("   计数：" + "，".join(f"{k} {v}" for k, v in s["counts"].items()))
        if s.get("slowest"):
            print("   最慢：" + "  ".join(f"p{p} {_fmt_s(e)}" for p, e in s["slowest"][:5]))


def cmd_pages(args) -> None:
    from ._cv import core_perf as perf
    r = _pick(perf.runs(_root(args), args.book), args.run)
    rows = sorted((p for p in r["pages"] if p["step"] == args.step and p.get("elapsed") is not None),
                  key=lambda p: -p["elapsed"])[:args.slowest]
    if not rows:
        print(f"✗ 运行 {r['run']['run_id']} 里 {args.step} 没有跑过的页", file=sys.stderr)
        sys.exit(1)
    for p in rows:
        sp = "，".join(f"{k} {_fmt_s(v[1])}" for k, v in sorted((p.get("spans") or {}).items(),
                                                                 key=lambda kv: -kv[1][1])[:4])
        print(f"p{p['page']:<5} {_fmt_s(p['elapsed']):>8}  {p['status']}  {sp}")


def cmd_spans(args) -> None:
    """一步的分段排行（每页秒＝分段合计 ÷ 真跑页数），带冷缓存再生小计。"""
    from ._cv import core_perf as perf
    if args.remote:
        from .jobs import perf_push
        if not perf_push.enabled():
            print("✗ --remote 要连得上任务库（databases.toml [jobs]）", file=sys.stderr)
            sys.exit(2)
        agg = perf_push.remote_spans(args.days, args.step, args.book).get(args.step)
    else:
        agg = None
        for r in perf.runs(_root(args), args.book, since=time.time() - args.days * 86400):
            for s in r["steps"]:
                if s["step"] != args.step:
                    continue
                agg = agg or {"ok": 0, "compute_s": 0.0, "spans": {}}
                agg["ok"] += s.get("ok", 0)
                agg["compute_s"] += s.get("compute_s", 0.0)
                for k, v in (s.get("spans") or {}).items():
                    agg["spans"][k] = agg["spans"].get(k, 0.0) + v[1]
    if not agg or not agg["ok"]:
        print(f"✗ 近 {args.days} 天 {args.step} 没有带分段的记录（分段名单见 cli_perf.PERF_HOOKS）", file=sys.stderr)
        sys.exit(1)
    if args.json:
        print(json.dumps(agg, ensure_ascii=False, indent=1))
        return
    ok, comp = agg["ok"], agg["compute_s"] or 1.0
    print(f"{args.step}：近 {args.days} 天真跑 {ok} 页，计算 {_fmt_s(comp)}（每页 {comp / ok:.2f}s）。分段（每页秒、占计算）：")
    for k, v in sorted(agg["spans"].items(), key=lambda kv: -kv[1])[:args.top]:
        print(f"  {v / ok:7.2f}s {v / comp:5.0%}  {k}")
    regen = regen_of(agg["spans"])
    if regen:
        tot = sum(regen.values())
        print(f"冷缓存再生 每页 {tot / ok:.2f}s（{tot / comp:.0%}）：" + "，".join(
            f"{k.removesuffix('.render')} {v / ok:.2f}s" for k, v in sorted(regen.items(), key=lambda kv: -kv[1])))


def add_parser(sub) -> None:
    p = sub.add_parser("perf", help="看跑批耗时：哪一步慢、慢在哪（本机 perf/ 记录）")
    ps = p.add_subparsers(dest="perf_cmd", required=True)
    t = ps.add_parser("top", help="各步合计，按墙钟排")
    t.add_argument("--days", type=float, default=7)
    t.add_argument("--book", default=None)
    t.add_argument("--remote", action="store_true", help="查任务库（全队各机器），在库里聚合好再回")
    t.add_argument("--by", choices=["host", "cv_version", "book"], default=None, help="--remote 时再按它拆")
    s = ps.add_parser("show", help="一次运行的各步明细")
    s.add_argument("book")
    s.add_argument("--run", default=None, help="run_id 前缀，缺省最新一次")
    g = ps.add_parser("pages", help="某一步最慢的页")
    g.add_argument("book")
    g.add_argument("step")
    g.add_argument("--slowest", type=int, default=20)
    g.add_argument("--run", default=None)
    u = ps.add_parser("push", help="把还没推过的本机记录推到任务库（只推任务库，不推中心库）")
    u.add_argument("--book", default=None)
    j = ps.add_parser("job", help="一条任务单的各步耗时（任务库）")
    j.add_argument("job_id", type=int)
    sp = ps.add_parser("spans", help="一步的分段排行（步内各道关、冷缓存再生）")
    sp.add_argument("step")
    sp.add_argument("--days", type=float, default=7)
    sp.add_argument("--book", default=None)
    sp.add_argument("--top", type=int, default=25)
    sp.add_argument("--remote", action="store_true", help="查任务库（全队各机器）")
    for q in (t, s, g, u, j, sp):
        q.add_argument("-w", "--workspace", default=None)
        q.add_argument("--json", action="store_true")
    p.set_defaults(_perf=True)


def cmd_perf(args) -> None:
    {"top": cmd_top, "show": cmd_show, "pages": cmd_pages, "push": cmd_push, "job": cmd_job,
     "spans": cmd_spans}[args.perf_cmd](args)


# ── 步内分段计时（第三期，2026-11-04）──────────────────────────────
# 不改 Step 源码（改了要动指纹、登记代码等价），在跑批进程里把下面这些函数／方法换成计时的薄壳：
# 壳只调原函数、原样返回，产物逐字节不变（`tests/test_perf_hooks.py` 核开关两种跑法产物相同）。
# 只换「按名字在模块全局或类上查」的调用点：Step 里 `foo()` 查的是模块全局，换模块属性就生效；
# 别的模块 `from x import foo` 早拿走的引用不受影响（那些调用不计，不出错）。
# 不换拿函数身份做判断的东西（如 `GlyphMatcher._verify is verify_pair_elastic`），所以 verify 不单独计。
PERF_HOOKS: dict[str, dict] = {
    "open_guji_cv.steps.glyph_match": {
        "funcs": ("_patch", "_page_queries", "_keben_subset", "human_confirmed_counts", "borrowed_ids",
                  "demote_borrowed", "consensus_same"),
        "methods": {"GlyphMatchStep": ("_matcher",)},
    },
    "open_guji_cv.clustering.match": {
        "methods": {"GlyphMatcher": ("_match", "extract", "_same_cell_rows", "_apply_near_shape",
                                     "_apply_shape_rerank")},
    },
    # 匹配器里面（11-04 第二轮）：verify_pair_elastic 本身不换（`_match` 拿它做身份判断），换它按全局名调的几段；
    # 矩阵乘与排序＝`_match` 减去这些
    "open_guji_cv.clustering.verify": {"funcs": ("_elastic_align", "_prepare", "_elastic_miss", "verify_pair_cov")},
    "open_guji_cv.clustering.features": {"methods": {"HogFeature": ("extract",)}},
    "open_guji_cv.clustering.normalize": {"funcs": ("normalize_patch",)},
    "open_guji_cv.core.reuse": {"funcs": ("cell_reuse",)},
    "open_guji_cv.steps.seed_admit": {
        # `_run_page` 里直接调的各道关（静态扫出来的，按调用次数挑掉了逐格的小工具）
        "funcs": ("_opt", "_align", "_human_shapes", "_iron_context", "_iron_page_scale", "_occluded",
                  "_approx_index", "_approx_hit", "_book_knn_pass", "_context_guard", "_context_lib_dissent",
                  "_context_variant_tie", "_coord_refs", "_edge_pair_pass", "_follow_ref_pass", "_garble_guard",
                  "_group_flow_pass", "_header_formula_pass", "_human_unbound_pass", "_iron_confusable_witness",
                  "_iron_coord_dissent", "_iron_ctx_dissent", "_lane_witnesses", "_near_knn_pass",
                  "_pair_shape_pass", "_pick_char", "_pua_rule_pass", "_rare_ref_pass",
                  "_ref_lib_coord_pass", "_ref_topk_pass", "_review_lanes_pass", "_rr_shape_pass",
                  "_seal_blank_flip", "_shadow_veto_pass", "_solo_ctx_vetoed", "_symbol_ref_blank_pass",
                  "_symbol_review_pass", "_vis_ruling_pass", "_keben_counts", "_doubts",
                  # 第二轮：铁证闸逐格再匹配、字组流程与影子闸里面
                  "_iron_decide", "_page_patch", "_clf_ctx", "_hard_blocked", "_shadow_gate"),
    },
    # cv #1911（11-26，CV4）把 seed_admit 拆出 seed_admit_common／lanes／shapes，字块读取各处经 `_C._page_patch` 调，
    # 换 seed_admit 上那个名字不再计到；要换 seed_admit_common 上的（旧 cv 没这模块，import 失败就跳过）
    "open_guji_cv.steps.seed_admit_common": {"funcs": ("_page_patch",)},
    "open_guji_cv.groups.flow": {"funcs": ("entry", "decide", "decide_joint", "_solve", "_pick_form",
                                           "_provisional", "_vis_try")},
    "open_guji_cv.shadow.gate": {"methods": {"ShadowGate": ("judge",)}},
    # seed_admit 在函数里现 import 的（调用时才按模块属性取，换模块属性就生效）
    "open_guji_cv.clustering.exclusions": {"funcs": ("excluded_ids",)},
    "open_guji_cv.clustering.note_lexicon": {"funcs": ("load_lexicon", "match_segment")},
    "open_guji_cv.feedback.bindings": {"funcs": ("rebind_library_shapes",)},
    "open_guji_cv.feedback.lookup": {"funcs": ("human_chars",)},
    "open_guji_cv.steps.align_ref": {"funcs": ("rare_topk_map",)},
    # ── 2026-11-25 第三轮：切字、识字里的新热点（11-18～25 row_segment 13 s/页、rare_candidates 4 s/页、column_band 4 s/页，
    # 之前都没有分段）＋读缓存图。各步的 `render`（冷缓存再生）由 `_render_hooks()` 按 STEPS 现列，不写死在这里。
    "open_guji_cv.core.step": {"methods": {"RunContext": ("image", "raw_page")}},
    "open_guji_cv.impl.keben.row_boundaries": {"funcs": ("segment_column", "fit_row_boundaries", "find_content_window",
                                                         "measure_book_period")},
    "open_guji_cv.seg.cut_select": {"methods": {"UNetJudge": ("owner", "scores", "guided_seam", "assess")}},
    "open_guji_cv.steps.row_segment_pagemap": {"funcs": ("layout_for",)},
    "open_guji_cv.steps.row_segment": {"funcs": ("_apply_manual_cells",)},
    "open_guji_cv.steps.column_band": {"funcs": ("band_strip",)},
    "open_guji_cv.steps.cell_shrink": {"funcs": ("restore_trimmed_ends",), "methods": {"CellShrinkStep": ("_column_chars",)}},
    "open_guji_cv.clustering.rare_panel": {"funcs": ("rare_for_batch", "candidates_batch")},
    "open_guji_cv.clustering.cnn_candidates": {"methods": {"CnnCandidates": ("topk_batch", "emb_topk_batch",
                                                                            "emb_topk_batch_subset")}},
    "open_guji_cv.clustering.stroke_evidence": {"methods": {"StrokeEvidence": ("rerank_rows",)}},
}
_HOOKED = False


def _render_hooks() -> dict[str, dict]:
    """各 Step 自己的 `render`（缓存图不在时现算）：记作 `<Step类>.render`。冷缓存再生的花费藏在**下游**那一步里
    （11-25 查到：单跑 glyph_match／seed_admit 的新容器里，读字块现算占 glyph_match 计算的 35%、seed_admit 的 50%），
    不单独套壳就只看见下游变慢。按 STEPS 现列，新加的步自动带上。"""
    out: dict[str, dict] = {}
    try:
        from ._cv import STEPS
    except Exception:  # noqa: BLE001
        return out
    for st in STEPS.values():
        cls = type(st)
        if "render" in cls.__dict__:
            out.setdefault(cls.__module__, {"methods": {}})["methods"].setdefault(cls.__name__, ("render",))
    return out


def all_hooks() -> dict[str, dict]:
    """`PERF_HOOKS` ＋ 各步 render。同一模块两边都有时合并。"""
    out = {m: {"funcs": tuple(v.get("funcs", ())), "methods": dict(v.get("methods", {}))} for m, v in PERF_HOOKS.items()}
    for m, v in _render_hooks().items():
        e = out.setdefault(m, {"funcs": (), "methods": {}})
        for c, meths in v["methods"].items():
            e["methods"][c] = tuple(dict.fromkeys((*e["methods"].get(c, ()), *meths)))
    return out


def _wrap(label: str, fn):
    from ._cv import core_perf as perf
    w = perf.timed(label)(fn)
    for attr in ("cache_clear", "cache_info", "cache_parameters"):   # lru_cache 的接口照旧能用
        if hasattr(fn, attr):
            setattr(w, attr, getattr(fn, attr))
    w.__perf_hook__ = fn
    return w


def install_hooks(hooks: dict | None = None) -> list[str]:
    """把 `PERF_HOOKS`（＋各步 render）里的函数换成计时薄壳；关了统计（`GUJI_PERF=0`）不换。返回换上的名字。
    同一进程只换一次；找不到的名字跳过（代码改名后不报错，只是少一段）。"""
    global _HOOKED
    import importlib
    from ._cv import core_perf as perf
    if (_HOOKED and hooks is None) or not perf.enabled():
        return []
    done: list[str] = []
    for modname, spec in (hooks or all_hooks()).items():
        try:
            mod = importlib.import_module(modname)
        except Exception:  # noqa: BLE001 —— 统计是附带的
            continue
        short = modname.rsplit(".", 1)[-1]
        for name in spec.get("funcs", ()):
            fn = getattr(mod, name, None)
            if callable(fn) and not hasattr(fn, "__perf_hook__") and not isinstance(fn, type):
                setattr(mod, name, _wrap(f"{short}.{name}", fn))
                done.append(f"{short}.{name}")
        for cname, meths in spec.get("methods", {}).items():
            cls = getattr(mod, cname, None)
            if cls is None:
                continue
            for name in meths:
                fn = cls.__dict__.get(name)
                if callable(fn) and not hasattr(fn, "__perf_hook__"):
                    setattr(cls, name, _wrap(f"{cname}.{name}", fn))
                    done.append(f"{cname}.{name}")
    if hooks is None:
        _HOOKED = True
    return done


def uninstall_hooks(hooks: dict | None = None) -> None:
    """换回原函数（测试用）。"""
    global _HOOKED
    import importlib
    for modname, spec in (hooks or all_hooks()).items():
        try:
            mod = importlib.import_module(modname)
        except Exception:  # noqa: BLE001
            continue
        for name in spec.get("funcs", ()):
            fn = getattr(mod, name, None)
            if hasattr(fn, "__perf_hook__"):
                setattr(mod, name, fn.__perf_hook__)
        for cname, meths in spec.get("methods", {}).items():
            cls = getattr(mod, cname, None)
            for name in meths if cls is not None else ():
                fn = cls.__dict__.get(name)
                if hasattr(fn, "__perf_hook__"):
                    setattr(cls, name, fn.__perf_hook__)
    if hooks is None:
        _HOOKED = False


COMMANDS = {"perf": (add_parser, cmd_perf)}
