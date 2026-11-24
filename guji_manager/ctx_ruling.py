"""`guji ctx-ruling write`：按「格号＋字」直接写终审文意裁定（group O、prompt_ver ctx-m1）。

没有待裁问（seed_admit 没记 ask）的格，人或对话看图定了字，要写成管线 5c `_vis_ruling_pass` 认的裁定：
键＝前后各 20 字窗口的哈希，窗口按 5c 当时的状态算（`final_review.pack.key_windows`：产物带 `evidence.vis_ctx`
就直接用，否则从终态回推）。原先是 ZM 的会话脚本 `write_ctx_ruling_by_cell.py`（11-20），11-21 收进 manager，
各书同一个口径写键。

输入 tsv（有表头也行，`#` 开头的行跳过）：`格号<TAB>字[<TAB>把握[<TAB>依据]]`，把握缺省 high。
管线放行还要：子类在 Z/N＋书级 `vis_ruling_ctx_subclasses` 里、裁定字＝整理本字或同属 `ruling_override_groups` 白名单字组。
本命令只写、不替管线判；字≠整理本字的行会提示「越过整理本」。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROMPT_VER = "ctx-m1"
GROUP = "O"
CONF = ("high", "mid", "low")



def check_events(evs, log) -> list[str]:
    """写前预检（cv #1837 `rulings.validate`，同 `RulingLog.append` 的拒写口径）→ 错误行；旧 cv 没有校验就返回空。"""
    from . import _cv
    try:
        validate = _cv.ruling_validate
        equiv = _cv.load_ver_equiv(Path(log.events_dir) / "ver_equiv.yaml")
    except (AttributeError, ImportError):
        return []
    return [f"{e.payload.get('cell') or e.id}: {m}" for e in evs for m in validate(e.payload or {}, equiv)[0]]


def append_or_exit(log, evs) -> int:
    """`RulingLog.append`，cv 拒写（版本 seed_admit 不认）时不抛栈，打清楚原因并以退出码 2 结束；一条都没写。"""
    from ._cv import BadRequest
    try:
        return log.append(evs)
    except BadRequest as e:
        print(f"✗ {e}\n  一条都没写。核对 --model／提示词版本；换了版本要先在 <feedback>/rulings/ver_equiv.yaml 登记（cv #1830）。",
              file=sys.stderr)
        raise SystemExit(2) from None

def read_cells(path: Path) -> list[dict]:
    rows = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        f = [x.strip() for x in line.split("\t")]
        if f[0] in ("格号", "cell", "id"):
            continue
        if len(f) < 2 or f[0].count(":") != 3 or not f[1]:
            raise SystemExit(f"第 {n} 行要「格号<TAB>字」：{line!r}")
        conf = f[2] if len(f) > 2 and f[2] else "high"
        if conf not in CONF:
            raise SystemExit(f"第 {n} 行把握 {conf!r} 不在 {CONF}")
        rows.append({"id": f[0], "char": f[1], "conf": conf, "why": f[3] if len(f) > 3 else ""})
    return rows


def build_events(rows: list[dict], win: dict, *, batch: str, subclass: str, model: str, seq0: int = 0,
                 ts: str | None = None, anchors: dict[str, dict] | None = None) -> tuple[list, list[str]]:
    """→ (事件, 提示)。取不到窗口的格不写。"""
    from ._cv import RULING_KIND, RULING_OTHER, RULING_SOURCE, EventTarget, make_event, ruling_ctx_hash
    evs, notes = [], []
    ts = ts or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for r in rows:
        w = win.get(r["id"])
        if w is None:
            notes.append(f"{r['id']} 取不到窗口（产物里没有这格／这页，或格被 excluded），不写")
            continue
        left, right, ref = w
        other = r["char"] == RULING_OTHER
        if ref and r["char"] != ref and not other:
            notes.append(f"{r['id']} 越过整理本（{ref}→{r['char']}）：管线只在两字同属 ruling_override_groups 白名单字组时放")
        payload = {"source": RULING_SOURCE, "group": GROUP, "char": None if other else r["char"], "other": other,
                   "conf": r["conf"], "why": (r.get("why") or "")[:60], "model": model, "prompt_ver": PROMPT_VER,
                   "cell": r["id"], "tok": {}, "ctx": {"left": left, "right": right, "hash": ruling_ctx_hash(left, right)},
                   "subclass": subclass, "ref": ref or "", "admit_ok": r["conf"] == "high" and not other,
                   "gate": "by_cell"}
        payload.update((anchors or {}).get(r["id"]) or {})      # 格锚点：cells_sha（写裁定这一刻的产物戳）＋ref（裁定键长期方案③）
        seq0 += 1
        evs.append(make_event(batch, seq0, RULING_KIND, EventTarget(step="seed_admit", unit="cell", key=r["id"], book=r["id"].split(":")[0]),
                              payload, actor="model", ts=ts))
    return evs, notes


def cmd(a) -> int:
    import os
    if a.workspace:
        os.environ["GUJI_WORKSPACE"] = str(Path(a.workspace).resolve())
    rows = read_cells(Path(a.cells))
    if not rows:
        print("没有要写的行", file=sys.stderr)
        return 1
    books = sorted({r["id"].split(":")[0] for r in rows})
    if a.fetch:
        from .ruling_hits import fetch_books
        fetch_books(books, Path(a.products), a.label, a.jobs)
    from .final_review import pack
    sort_fn, _, _, width = pack.default_cv()
    win = pack.key_windows(Path(a.products), [r["id"] for r in rows], sort_fn, width)
    from ._cv import RulingLog
    rd = Path(a.ruling_dir) if a.ruling_dir else None
    log = RulingLog(rd.parent if rd is not None and rd.name == "rulings" else rd) if rd else RulingLog()
    seq0 = max((e.seq for e in log.read(a.batch, raw=True)), default=0)
    anchors: dict[str, dict] = {}
    try:
        from .ruling_anchor import anchor_fields
        for r in rows:
            w = win.get(r["id"])
            parts = r["id"].split(":")
            if w is not None and len(parts) >= 3 and parts[1].isdigit():
                anchors[r["id"]] = anchor_fields(Path(a.products), parts[0], int(parts[1]), w[2])
    except BaseException as e:  # noqa: BLE001 —— 老 cv／取不到切分戳：照旧写，只是没有锚点
        print(f"（没带格锚点：{type(e).__name__}: {str(e)[:100]}）", file=sys.stderr)
        anchors = {}
    evs, notes = build_events(rows, win, batch=a.batch, subclass=a.subclass, model=a.model, seq0=seq0, anchors=anchors)
    for n in notes:
        print("  " + n, file=sys.stderr)
    bad = check_events(evs, log)
    for m in bad[:20]:
        print(f"  ✗ 拒写（seed_admit 不认）{m}", file=sys.stderr)
    if a.dry_run:
        for e in evs:
            p = e.payload
            print(f"{p['cell']}\t{p['char'] or '其他'}\t{p['conf']}\t{p['ref']}\t{p['ctx']['left']}｜{p['ctx']['right']}")
        print(f"（试跑）可写 {len(evs)}/{len(rows)} 条，批次 {a.batch}"
              + (f"；但有 {len(bad)} 条会被 cv 拒写，真写时整批不落" if bad else ""), file=sys.stderr)
        return 2 if bad else 0
    append_or_exit(log, evs)
    print(f"写 {len(evs)}/{len(rows)} 条 → {log.batch_path(a.batch)}；推库前 guji db pull、设 GUJI_ACTOR，再 guji db sync；"
          "重放 seed_admit 后用 guji rulings-hits 核命中", file=sys.stderr)
    return 0


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("ctx-ruling", help="按格号＋字写终审文意裁定（ctx-m1，键按 seed_admit 5c 窗口）")
    p.add_argument("action", choices=["write"])
    p.add_argument("--cells", required=True, help="tsv：格号<TAB>字[<TAB>把握[<TAB>依据]]，把握缺省 high")
    p.add_argument("--products", required=True, help="产物根（下有 <册>/seed_admit/、<册>/align_ref/）")
    p.add_argument("--batch", required=True, help="裁定批次名，如 llm-ctx-20261121-ZM-bycell")
    p.add_argument("--subclass", required=True, help="子类（管线只收 Z、N 与书级 vis_ruling_ctx_subclasses，如殿本 P,D、全唐文 A）")
    p.add_argument("--model", default="claude-session", help="写进裁定的模型名")
    p.add_argument("-w", "--workspace", default=None, help="工作区（定裁定库位置；缺省 GUJI_WORKSPACE）")
    p.add_argument("--ruling-dir", default=None, help="feedback 目录（下有 rulings/；给到 rulings 也行），缺省按工作区")
    p.add_argument("--fetch", action="store_true", help="先取各册产物包，只解 seed_admit、align_ref 到 --products（覆盖）")
    p.add_argument("--label", default=None, help="--fetch 取哪个包标签（缺省各册 main）")
    p.add_argument("--jobs", type=int, default=4, help="--fetch 同时取几册")
    p.add_argument("--dry-run", action="store_true", help="只列窗口与提示，不写")


def _cmd(a) -> None:
    sys.exit(cmd(a))


COMMANDS = {"ctx-ruling": (add_parser, _cmd)}
