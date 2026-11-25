"""字格身份账人裁自检的定时报告（11-25 主导线程定）：各书跑 ``guji uid check-u``，非 0 就通知 CV0 和该书项目。

只报、不改人裁（作废／转待审要看清单，人来定）。执行方空闲时跑（``GUJI_UID_CHECKU_S`` 秒一次，缺省 0＝不跑，
只在一台机器上开，免得每台都发一遍）。本机找得到哪些工作区（``<根>/*/workspace.yaml``，按中心库标记认 ws）就查哪些，
查前先 ``db pull --only`` 拉 check-u 要读的几个目录。同一书的结果没变不重复通知（状态记在 ``GUJI_UID_CHECKU_STATE``）。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

#: check-u 要读的目录（人裁事件、补锚档、身份账、作废记档）
PATHS = ("feedback/events/", "feedback/anchors/", "feedback/uid/", "feedback/lists/u_void/")
#: 工作区 → 该书项目（花名册名字）；GUJI_UID_CHECKU_PROJECTS（JSON）可覆盖／补充
PROJECTS = {"siku-zongmu": "ZM", "988g3f0wsu": "SJ", "995ejelvk0": "QTW"}
_TOTAL = re.compile(r"^合计 (\d+)")
_ROW = re.compile(r"^(\S+)\t(\d+)(?:\t缺补锚档 (\d+))?(?:\t无框无档 (\d+))?$")


def find_workspaces(roots) -> dict[str, Path]:
    """各根下一层目录里有 workspace.yaml、且是中心库工作区的：ws → 目录（同一 ws 多处取第一个）。"""
    from .._cv import central_marker
    out: dict[str, Path] = {}
    for r in roots:
        for y in sorted(Path(r).glob("*/workspace.yaml")):
            try:
                ws = (central_marker(y.parent) or {}).get("ws")
            except Exception:  # noqa: BLE001
                ws = None
            if ws and ws not in out:
                out[str(ws)] = y.parent
    return out


def parse(text: str) -> dict:
    """check-u 输出 → {total, books: {册: {"no_u": n, "anchor": n, "boxless": n}}}；没有「合计」行 → total None。"""
    total, books = None, {}
    for line in text.splitlines():
        m = _TOTAL.match(line)
        if m:
            total = int(m[1])
            continue
        m = _ROW.match(line)
        if m:
            books[m[1]] = {"no_u": int(m[2]), "anchor": int(m[3] or 0), "boxless": int(m[4] or 0)}
    return {"total": total, "books": books}


def check_ws(ws_dir: Path, guji: str = "guji", env=None, run=subprocess.run) -> dict:
    only = [x for p in PATHS for x in ("--only", p)]
    pr = run([guji, "db", "pull", "-w", str(ws_dir), *only], capture_output=True, text=True, timeout=1800, env=env)
    r = run([guji, "uid", "check-u", "-w", str(ws_dir)], capture_output=True, text=True, timeout=1800, env=env)
    out = parse(r.stdout)
    out["pull_ok"] = pr.returncode == 0
    if out["total"] is None:
        out["error"] = (r.stderr or r.stdout).strip().splitlines()[-1:] or [f"退出码 {r.returncode}"]
    return out


def message(ws: str, res: dict) -> str:
    bs = res["books"]
    parts = [f"{b}：" + "、".join(f"{k} {v}" for k, v in (("没u没记档", c["no_u"]), ("缺补锚档", c["anchor"]),
                                                          ("无框无档", c["boxless"])) if v)
             for b, c in sorted(bs.items()) if any(c.values())]
    return (f"【字格身份账自检】工作区 {ws}：人裁 check-u 合计 {res['total']}（应为 0）。" + "；".join(parts[:12])
            + ("…" if len(parts) > 12 else "")
            + "。没u没记档＝每格最新人裁没 u、也没记作废／转待审：跑 guji uid migrate-plan <册> --close 收口；"
              "缺补锚档／无框无档：guji uid anchor-fill --write。本消息只报不改。")


def recipients(ws: str) -> list[str]:
    to = [x.strip() for x in os.environ.get("GUJI_UID_CHECKU_TO", "CV0").split(",") if x.strip()]
    proj = dict(PROJECTS)
    try:
        proj.update(json.loads(os.environ.get("GUJI_UID_CHECKU_PROJECTS") or "{}"))
    except ValueError:
        pass
    p = proj.get(ws)
    return to + ([p] if p and p not in to else [])


def run(roots, *, notify: bool = False, state: Path | None = None, guji: str = "guji", env=None,
        send=None, say=print) -> dict:
    """查本机找得到的各工作区；``notify`` 时非 0 且和上次结果不同才发。→ {ws: 结果}。"""
    state = Path(state or os.environ.get("GUJI_UID_CHECKU_STATE") or Path.home() / ".guji-jobs" / "uid_checku.json")
    try:
        last = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        last = {}
    if send is None:
        from ..jobs.notify import _send as send
    res = {}
    for ws, d in sorted(find_workspaces(roots).items()):
        r = check_ws(d, guji=guji, env=env)
        res[ws] = r
        say(f"check-u {ws}：{r['total'] if r['total'] is not None else '没跑成 ' + str(r.get('error'))}")
        if r["total"] is None:
            continue
        sig = json.dumps(r["books"], sort_keys=True) if r["total"] else "0"
        if notify and r["total"] and last.get(ws) != sig:
            text = message(ws, r)
            for to in recipients(ws):
                say(f"  通知 {to}：{send(to, text)}")
        last[ws] = sig
    if notify:
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps(last, ensure_ascii=False, indent=1), encoding="utf-8")
    return res
