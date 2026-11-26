"""钉状态流 pin_state：删钉、过期钉、重新生效的写入口（GM4 11-26，方案第九节）。

    guji pinstate remove <册> --pin-id pin-vol31-char-3140 --events evt_a,evt_b --reason human_correction [--u 3140]
                         [--by-event evt_x] [--level human|ai] [--evidence '…'] -w <工作区>
    guji pinstate expire|reactivate …（同参数；expire 只对 AI／人钉标「算法已能做对」，不删）

落 ``<数据目录>/feedback/pins/<册>.state.jsonl``（只追加，一行一事件，事件形状，字段放 payload），
随 ``guji db sync`` 进中心库 events 表（stream=pin_state）；cv 读同一份文件（pin_removed，cv #1930）：
每个 pin_id 按 at 后到覆盖，最后一条 v=removed 的 payload.events 列的答案事件不进 human_chars。
钉状态不进指纹——写 removed 后要从 seed_admit 起 force 重放才生效。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

VS = {"remove": "removed", "expire": "expired", "reactivate": "reactivated"}
REASONS = ("human_correction", "superseded", "ai_corrected", "algo_ok", "u_void", "glyph_evict", "legacy_stale")


def state_path(data: Path | str, book: str) -> Path:
    return Path(data) / "feedback" / "pins" / f"{book}.state.jsonl"


def build(book: str, v: str, pin_id: str, *, events: list[str], reason: str, level: str, by: str,
          u=None, by_event: str | None = None, evidence=None, at: str | None = None) -> dict:
    if v not in VS.values():
        raise ValueError(f"v 应为 {sorted(VS.values())}")
    if reason not in REASONS:
        raise ValueError(f"reason 应为 {REASONS}")
    if level not in ("human", "ai"):
        raise ValueError("level 只用 human／ai；执行者写 by")
    if v != "reactivated" and not events:
        raise ValueError("removed／expired 要给 events（被删钉的答案事件 id）")
    if reason == "superseded" and not by_event:
        raise ValueError("superseded 要给 by_event")
    at = at or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {"v": v, "pin_id": pin_id, "book": book, "reason": reason, "level": level, "by": by, "at": at,
               "events": list(events)}
    for k, val in (("u", u), ("by_event", by_event), ("evidence", evidence)):
        if val is not None:
            payload[k] = val
    return {"id": f"ps_{pin_id}_{at}", "kind": "pin_state", "ts": at, "actor": by,
            "target": {"book": book}, "payload": payload}


def append(data: Path | str, book: str, rec: dict) -> Path:
    p = state_path(data, book)
    p.parent.mkdir(parents=True, exist_ok=True)
    have = set()
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            try:
                have.add(json.loads(ln).get("id"))
            except ValueError:
                pass
    if rec["id"] in have:
        return p
    with p.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    return p


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("pinstate", help="钉状态：删钉 remove／过期 expire／重新生效 reactivate（写 feedback/pins/<册>.state.jsonl）")
    p.add_argument("action", choices=sorted(VS))
    p.add_argument("book", help="册号")
    p.add_argument("--pin-id", required=True)
    p.add_argument("--events", default="", help="被删钉的答案事件 id，逗号分隔")
    p.add_argument("--reason", required=True, choices=REASONS)
    p.add_argument("--level", default="human", choices=("human", "ai"))
    p.add_argument("--u", type=int, default=None)
    p.add_argument("--by-event", default=None)
    p.add_argument("--evidence", default=None)
    p.add_argument("--by", default=None, help="执行者（缺省 GUJI_ACTOR）")
    p.add_argument("--data", default=None, help="数据目录（缺省按工作区找）")
    p.add_argument("--dry-run", action="store_true")


def cmd_pinstate(a) -> None:
    data = a.data
    if not data:
        w = getattr(a, "workspace", None) or os.environ.get("GUJI_WORKSPACE")
        if not w:
            sys.exit("✗ 要 -w <工作区> 或 --data <数据目录>")
        from ._cv import data_root
        data = data_root(Path(w).resolve()) or w
    by = a.by or os.environ.get("GUJI_ACTOR") or "manager"
    try:
        rec = build(a.book, VS[a.action], a.pin_id, events=[e for e in a.events.split(",") if e], reason=a.reason,
                    level=a.level, by=by, u=a.u, by_event=a.by_event, evidence=a.evidence)
    except ValueError as e:
        sys.exit(f"✗ {e}")
    if a.dry_run:
        print(json.dumps(rec, ensure_ascii=False, indent=1))
        return
    p = append(data, a.book, rec)
    print(f"✓ 写入 {p}；cv 要从 seed_admit 起 force 重放才生效，推库用 guji db sync")


COMMANDS = {"pinstate": (add_parser, cmd_pinstate)}
