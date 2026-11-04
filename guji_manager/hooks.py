"""guji-manager 给 pipeline 的 `guji` 命令登记的钩子（拆分 P4，2026-11-04；cv `open_guji_cv/core/hooks.py`）。

入口点 `guji.hooks` → `register(hooks)`。原先夹在 cv `cli_v2` 里的 manager 行为都在这里：

- startup：注册去 R2 取派生缓存的取件器；跑批耗时推任务库；`step`／`pipeline` 装步内分段计时。
- prepare：开跑前把册钉的字形库快照、模型、语料备好，跑 Step5-b 时预建生僻字模板索引（`ops/prep.py`）。
- finished：整册跑完没有失败页就自动存包；提醒本机没存包的产物。
- status：收尾闸、裁放不一致、看图待审、没存包的产物四个报告项。
"""
from __future__ import annotations

import sys

from .ops import prep


def register(hooks) -> None:
    hooks.add("startup", startup)
    hooks.add("prepare", prepare)
    hooks.add("finished", finished)
    hooks.add("status", status)


def startup(command: str | None) -> None:
    prep.install_derived_fetcher()
    try:                     # 跑批耗时记录写完就推美国机任务库（只在设了 JOBSDB_TOKEN 时）。见 cv doc/性能统计.md
        from .jobs import perf_push
        if perf_push.enabled():
            from ._cv import core_perf as perf
            perf.add_sink(perf_push.sink)
    except Exception:  # noqa: BLE001 —— 统计是附带的，装不上不影响命令
        pass
    if command in ("step", "pipeline"):   # 步内分段计时（不改 Step 源码、不动指纹，见 cli_perf.PERF_HOOKS）
        try:
            from .cli_perf import install_hooks
            install_hooks()
        except Exception:  # noqa: BLE001
            pass


def prepare(book, steps: list[str], jobs: int = 1) -> None:
    prep.ensure_glyph_pin(book)
    prep.ensure_model_pin(book)
    prep.ensure_corpus_files(book)
    if "rare_candidates" in steps:
        prep.ensure_rare_index(book.id, jobs=max(1, jobs or 1))


def finished(args, eng, steps: list[str], ok: bool) -> None:
    if ok:
        from ._cv import cli_steps
        from .cli_products import book_versions
        prep.auto_pack(args, eng, steps, lambda e: cli_steps(e, None, None), book_versions)
    prep.print_unpacked(eng.book.id, eng.store)


def status(book: str, pages: list[int], store) -> list[tuple]:
    gaps, mism = _closure_gaps(book, pages, store)
    return [("closure_gaps", gaps, _print_closure_gaps),
            ("closure_mismatches", mism, _print_closure_mismatches),
            ("vision_pending", _vision_pending(book, pages, store), _print_vision_pending),
            (None, None, lambda _v: prep.print_unpacked(book, store))]


def _vision_pending(book: str, pages: list[int], store) -> list[dict] | None:
    """报告项（overview#428）：看图判错、人还没裁的格。不要求为 0；算不出来 → None。"""
    try:
        from .feedback.vision import vision_pending
        return vision_pending(book, pages, store)
    except Exception as e:  # noqa: BLE001
        print(f"  （看图待审没算出来：{type(e).__name__}: {e}）", file=sys.stderr)
        return None


def _print_vision_pending(rows: list[dict] | None) -> None:
    if not rows:
        return
    print(f"  看图判错待人审 {len(rows)} 格（报告项，不挡收尾；控制台 doubt=vision_flag 筛出来裁）：")
    for r in rows[:10]:
        print(f"      {r['id']:20s} 放行「{r['char'] or ''}」 看图「{r.get('vision') or '?'}」 {r.get('judge') or ''}")
    if len(rows) > 10:
        print(f"      …另 {len(rows) - 10} 格")


def _closure_gaps(book: str, pages: list[int], store) -> tuple[list[dict] | None, list[dict] | None]:
    """收尾不变量（overview#403 缺口 C，`verdict_view.closure_gaps`）与报告项（`closure_mismatches`）；
    算不出来 → None，不拖垮 status。"""
    from .review.verdict_view import closure_gaps, closure_mismatches
    out = []
    for name, fn in (("收尾闸", closure_gaps), ("裁放不一致", closure_mismatches)):
        try:
            out.append(fn(book, pages, store))
        except Exception as e:  # noqa: BLE001
            print(f"  （{name}没算出来：{type(e).__name__}: {e}）", file=sys.stderr)
            out.append(None)
    return out[0], out[1]


def _print_closure_mismatches(mism: list[dict] | None, show: int = 30) -> None:
    """报告项，不要求为 0：人裁的字 ≠ 现行放行的字，人扫一眼（己已巳族单列）。"""
    if mism is None:
        return
    main = [m for m in mism if m["kind"] == "main"]
    jys = [m for m in mism if m["kind"] == "jys"]
    canon = [m for m in mism if m["kind"] == "canon"]
    print(f"  报告 · 人裁字≠放行字 {len(main)} 格（不要求为 0，扫一眼：多为老裁决钉在移位格上被正确丢掉）"
          + (f"；己已巳族 {len(jys)} 格另列" if jys else "")
          + (f"；字形↔规范字等价 {len(canon)} 格另列" if canon else ""))
    for m in main[:show]:
        print(f"      {m['id']}  人裁 {m['shape']} → 放行 {m['char']}")
    if len(main) > show:
        print(f"      …另 {len(main) - show} 格（--json 看全部）")
    if jys:
        print("      己已巳：" + "  ".join(f"{m['id']} {m['shape']}→{m['char']}" for m in jys[:show])
              + (" …" if len(jys) > show else ""))


def _print_closure_gaps(gaps: list[dict] | None, show: int = 30) -> None:
    if gaps is None:
        return
    if not gaps:
        print("  收尾闸 ✓ 已定字却没出字 0 格")
        return
    print(f"  收尾闸 ✗ 已定字却没出字 {len(gaps)} 格（收尾前必须为 0；"
          "Step7 过期先重跑，仍在的去控制台审查页补确认——失效老裁决会带预勾出卡）")
    for g in gaps[:show]:
        print(f"      {g['id']}  {g['shape']}{'  [排除名单]' if g['excluded'] else ''}")
    if len(gaps) > show:
        print(f"      …另 {len(gaps) - show} 格（--json 看全部）")
