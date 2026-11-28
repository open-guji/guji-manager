"""老评测器（`eval/registry.py` 的 EVALS）经 `guji bench` 照旧能跑（LegacyEval 适配，P1 各线接成原生后删）。

老评测器不按书、不自动备资源；结果仍转成统一格式写进 `bench-results/<id>/_legacy/<时间>/`。
报表类（GM4 11-28 定不算 bench）只在 `guji bench list` 末尾列出指向原命令。
"""
from __future__ import annotations

import subprocess
import time

#: 报表（非 bench）：命令名 → 说明
REPORTS = {
    "guji check throughput": "吞吐量",
    "guji check quality": "质量判据",
    "guji check round": "收轮检查",
    "guji check rate": "人审率历史",
    "guji groups status": "字组状态",
    "guji iterate …": "降人审迭代报表（review_breakdown 等）",
}


def _evals() -> dict:
    try:
        from ..eval.registry import EVALS
        return EVALS
    except Exception:                                      # noqa: BLE001
        return {}


def is_legacy(name: str) -> bool:
    from open_guji_cv.eval import bench as B
    try:
        B.get(name)
        return False
    except KeyError:
        return name in _evals()


def print_list(a) -> None:
    from open_guji_cv.eval import bench as B
    new = {s.id for s in B.all_specs()}
    old = [s for k, s in sorted(_evals().items()) if k not in new]
    if old:
        print(f"\n老评测器（还没接成原生 bench，`guji bench run <id>` 照旧跑，不按书）：{len(old)} 个")
        for s in old:
            print(f"  {s.id:20s} {s.shard:36s} {s.title}")
    print("\n报表（非 bench，用原命令）：")
    for k, v in REPORTS.items():
        print(f"  {k:24s} {v}")


def run(name: str, a) -> bool:
    """跑一个老评测器；返回是否 regressed。"""
    from open_guji_cv.eval import bench as B
    from .._cv import run_eval
    from .cli import _results_root, _versions
    rep = run_eval(name, timeout=a.timeout)
    st = {"ok": "ok", "regressed": "regressed", "skipped": "skipped", "failed": "skipped"}[rep.status]
    metrics = {m.name: m.value for m in rep.metrics}
    r = B.BenchResult(name, "_legacy", [], metrics, rep.metrics[0].name if rep.metrics else "", n=rep.n_gold or 0,
                      status=st, reason=rep.error or rep.gate, env={**_versions(), "legacy": True, "lock": rep.lock},
                      seconds=rep.elapsed)
    r.guards = [{"metric": g.get("metric"), "dir": g.get("dir"), "limit": g.get("limit"), "value": g.get("value"),
                 "status": {"pass": "ok", "fail": "regressed"}.get(g.get("verdict"), "unverified")}
                for g in (rep.guards or [])]
    out = B.write_result(_results_root(a) / name / "_legacy" / time.strftime("%Y%m%d-%H%M%S"), r)
    print(f"{'✓⚠––'[['ok', 'regressed', 'skipped', 'no_gold'].index(st)]} {rep.summary_line()}  （老框架）\n    结果 {out}")
    return st == "regressed"


def guard(a) -> bool:
    from .resources import guji_exe
    r = subprocess.run([guji_exe(), "eval", "guard"], check=False)
    return r.returncode != 0
