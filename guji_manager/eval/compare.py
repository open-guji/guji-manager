"""两次评测结果对比（`guji eval run … --save-dir 新 --against 旧`，A23 2026-11-23）。

逐个评测器比指标（同名指标的差值），并比脚本 JSON 里的 `flips`（误认题／错例清单）：
新增的是这次新错的，消失的是这次改对的。钉版（lock）不同时先提示——库或代码变了，差值里混着基线漂移。
"""
from __future__ import annotations

import json
from pathlib import Path


def _load(d: Path, eval_id: str):
    rp, op = d / f"{eval_id}.report.json", d / f"{eval_id}.json"
    rep = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else None
    out = json.loads(op.read_text(encoding="utf-8")) if op.exists() else None
    return rep, out


def _flips(out) -> dict[str, set[str]]:
    f = (out or {}).get("flips") or {}
    return {k: set(v) for k, v in f.items() if isinstance(v, list)}


def compare_dirs(old_dir: Path, reports, new_dir: Path | None, show: int = 10) -> str:
    lines = [f"== 对比 {old_dir} =="]
    for r in reports:
        old_rep, old_out = _load(old_dir, r.eval_id)
        if old_rep is None:
            lines.append(f"  {r.eval_id}：旧目录里没有，跳过")
            continue
        if old_rep.get("lock") and r.lock and old_rep["lock"] != r.lock:
            diff = {k: (old_rep["lock"].get(k), v) for k, v in r.lock.items() if old_rep["lock"].get(k) != v}
            lines.append(f"  {r.eval_id}：⚠ 钉版不同 {diff}（差值里混着库／代码变化）")
        om = {m["name"]: m["value"] for m in old_rep.get("metrics", [])}
        parts = []
        for m in r.metrics:
            o = om.get(m.name)
            if isinstance(m.value, (int, float)) and isinstance(o, (int, float)) and m.value != o:
                parts.append(f"{m.name} {o}→{m.value}（{m.value - o:+.4g}）")
        lines.append(f"  {r.eval_id}：" + ("；".join(parts) if parts else "指标不变"))
        if new_dir is not None:
            _, new_out = _load(new_dir, r.eval_id)
            of, nf = _flips(old_out), _flips(new_out)
            for k in sorted(set(of) | set(nf)):
                add, gone = sorted(nf.get(k, set()) - of.get(k, set())), sorted(of.get(k, set()) - nf.get(k, set()))
                if add or gone:
                    lines.append(f"    {k}：新错 {len(add)}、改对 {len(gone)}")
                    lines += [f"      + {x}" for x in add[:show]] + [f"      - {x}" for x in gone[:show]]
    return "\n".join(lines)
