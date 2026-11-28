"""第四步出口检查 `decide_gate`（cv #2005，CV4 11-28）在 manager 这边的读法：按 fail 汇总，flag 只计数留证据。

cv 的 `decide_gate` 挂在 `seed_admit` 出口，**只检测、不判断**：不改格、没有步骤读它，别的步骤指纹不变。
每页一份 `products/<册>/decide_gate/pNNNN.json`（`{"decide_gate": PageDecideGate}`）：
`passed`（无 fail）、`checks[{name, level: fail|flag, unit: page|col|cell, key, reason, metrics}]`、`metrics`。

- fail（大概率有错，要人或书 Project 处理）：`step_error`、`ref_shift`、`char_not_in_evidence`、`admit_blank_cell`
- flag（可疑，攒阈值）：只计数，不告警（CV4 11-28：flag 只留证据别当告警）

`DETECT_ONLY_STEPS`：只检测、不出字的步。这类步「没跑」（cv 升级后老册还没补跑）不是产物过期，
close-check 1a、看板过期数、部署检查都不把它算进坏账；它有没有跑、查出什么由 close-check 2e 单独报。
补跑：`guji pipeline <管线> <册> --from seed_admit`（seed_admit 新鲜会跳过，只补跑 gate，几秒一页）。
"""
from __future__ import annotations

from pathlib import Path

#: 只检测、不出字、不被任何步读的步（cv 出口 gate）
DETECT_ONLY_STEPS = frozenset({"decide_gate"})

STEP = "decide_gate"
FAIL_LEVEL = "fail"


def _page_key(pg: int) -> str:
    return f"p{int(pg):04d}"


def _read(store, book: str, pg: int) -> dict | None:
    d = store.read_raw(book, STEP, _page_key(pg)) if hasattr(store, "read_raw") else None
    if d is None:
        p = Path(store.root) / book / STEP / f"{_page_key(pg)}.json"
        if not p.is_file():
            return None
        import json
        d = json.loads(p.read_text(encoding="utf-8"))
    return d.get(STEP, d) if isinstance(d, dict) else None


def summarize(book: str, pages, store, rows_max: int = 500) -> dict:
    """读这些页的 decide_gate 产物 → 汇总。

    返回 `{"pages": 页数, "checked": 有产物的页数, "missing": [没产物的页], "fail_pages": [有 fail 的页],
    "fails": {name: 条数}, "flags": {name: 条数}, "rows": [每条 fail：page, name, unit, key, reason]}`。"""
    pages = [int(p) for p in pages]
    out = {"pages": len(pages), "checked": 0, "missing": [], "fail_pages": [],
           "fails": {}, "flags": {}, "rows": []}
    for pg in pages:
        g = _read(store, book, pg)
        if g is None:
            out["missing"].append(pg)
            continue
        out["checked"] += 1
        bad = False
        for c in g.get("checks") or []:
            name = str(c.get("name") or "?")
            if c.get("level") == FAIL_LEVEL:
                bad = True
                out["fails"][name] = out["fails"].get(name, 0) + 1
                if len(out["rows"]) < rows_max:
                    out["rows"].append({"page": pg, "name": name, "unit": c.get("unit"),
                                        "key": c.get("key"), "reason": c.get("reason")})
            else:
                out["flags"][name] = out["flags"].get(name, 0) + 1
        if bad or g.get("passed") is False:
            out["fail_pages"].append(pg)
    return out


def describe(s: dict) -> str:
    """一句话：查了几页、fail 几条（按检测项）、flag 几条、几页没跑。"""
    nf = sum(s["fails"].values())
    parts = [f"查了 {s['checked']}/{s['pages']} 页"]
    parts.append(f"fail {nf} 条／{len(s['fail_pages'])} 页"
                 + ("（" + "、".join(f"{k} {v}" for k, v in sorted(s["fails"].items())) + "）" if nf else ""))
    nfl = sum(s["flags"].values())
    if nfl:
        parts.append(f"flag {nfl} 条只留证据不计（" + "、".join(f"{k} {v}" for k, v in sorted(s["flags"].items())) + "）")
    if s["missing"] and s["checked"]:
        parts.append(f"{len(s['missing'])} 页没出 decide_gate（`guji pipeline … --from seed_admit` 补跑）")
    return "；".join(parts)
