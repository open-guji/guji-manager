"""三书冻结日历（T6）：只冻结 S 轮（结构层）。D 轮期间各线照常合决策层改动（框架 14.3，A22/用户 11-05）。

日历文件（放 ai-team `domain/CV/质检/迭代降人审框架/冻结日历.yaml`，A31 维护，各线只读；时间洛杉矶）：

  freezes:
    - {book: dianben, from: "2026-11-05 10:00", to: "2026-11-05 22:00", steps: ["*"], note: "S 轮 r5", notify: [A22, A23, A30, A20]}
  冻结期内**不合会改切分指纹的 PR**（border_detect、cell_shrink、row_segment、页型、图源、语料、库快照等）；`steps` 缺省＝这些结构步，
  也可列具体 Step 名。格号变化通知名单缺省 A22 A23 A30 A20（用户 11-05：A33 不在粗校流程里）。

  guji-manager iterate freeze list  --file 冻结日历.yaml [--at "2026-11-05 12:00"]
  guji-manager iterate freeze add   --file … --book sj --from … --to … [--steps border_detect,row_segment] [--note …]
  guji-manager iterate freeze check --file … --books dianben,sj --steps border_detect [--at …]
      # PR 描述写「影响哪几本书、哪几步指纹」，合并前跑；撞了退出码 3，并打印要通知的人
cv PR 模板建议加一行：`影响的书／Step／指纹变化：`（A20 在 cv 仓加）。
"""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

import yaml

FMT = "%Y-%m-%d %H:%M"
#: 结构层 Step（改它们会改切分指纹/格号）；S 轮冻结的缺省范围
STRUCT_STEPS = ("border_detect", "border_detect_gate", "cell_shrink", "row_segment", "page_kinds", "source", "corpus", "glyph_snapshot")
NOTIFY = ["A22", "A23", "A30", "A20"]


def now_la() -> datetime.datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("America/Los_Angeles")).replace(tzinfo=None)
    except Exception:   # noqa: BLE001
        return datetime.datetime.utcnow() - datetime.timedelta(hours=8)


def parse_t(s) -> datetime.datetime:
    if isinstance(s, datetime.datetime):
        return s
    return datetime.datetime.strptime(str(s).strip()[:16], FMT)


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("freezes") or []


def active(freezes: list[dict], at: datetime.datetime) -> list[dict]:
    return [f for f in freezes if parse_t(f["from"]) <= at <= parse_t(f["to"])]


def _covers(f: dict, step: str) -> bool:
    steps = f.get("steps") or ["*"]
    return step in (STRUCT_STEPS if "*" in steps else steps)


def conflicts(freezes: list[dict], books: list[str], steps: list[str], at: datetime.datetime) -> list[dict]:
    steps = steps or list(STRUCT_STEPS)
    out = []
    for f in active(freezes, at):
        if f["book"] not in books:
            continue
        if any(_covers(f, s) for s in steps):
            out.append(f)
    return out


def cmd_list(a) -> int:
    fr = load(a.file)
    at = parse_t(a.at) if a.at else now_la()
    act = {id(f) for f in active(fr, at)}
    print(f"现在（洛杉矶）{at.strftime(FMT)}；共 {len(fr)} 条")
    for f in sorted(fr, key=lambda f: parse_t(f["from"])):
        tag = "冻结中" if id(f) in act else ("已过" if parse_t(f["to"]) < at else "待到")
        print(f"[{tag}] {f['book']} {f['from']} → {f['to']} steps={','.join(f.get('steps') or ['*'])} {f.get('note', '')}")
    return 0


def cmd_add(a) -> int:
    fr = load(a.file)
    parse_t(a.from_), parse_t(a.to)
    fr.append({"book": a.book, "from": a.from_, "to": a.to,
               "steps": a.steps.split(",") if a.steps else ["*"], "note": a.note, "notify": a.notify.split(",") if a.notify else NOTIFY})
    a.file.parent.mkdir(parents=True, exist_ok=True)
    a.file.write_text("# 三书冻结日历（洛杉矶时间；A31 维护，各线只读）。用法见 guji-manager iterate freeze。\n"
                      + yaml.safe_dump({"freezes": fr}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"已记：{a.book} {a.from_} → {a.to}")
    return 0


def cmd_check(a) -> int:
    at = parse_t(a.at) if a.at else now_la()
    cs = conflicts(load(a.file), a.books.split(","), a.steps.split(",") if a.steps else [], at)
    if not cs:
        print("✓ 没有撞冻结")
        return 0
    for f in cs:
        print(f"✗ 撞冻结（S 轮）：{f['book']} {f['from']} → {f['to']} {f.get('note', '')}；改格号/切分指纹的 PR 请等解冻，并通知 {' '.join(f.get('notify') or NOTIFY)}")
    return 3


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="iterate freeze", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("list", "add", "check"):
        p = sub.add_parser(name)
        p.add_argument("--file", type=Path, required=True)
        p.add_argument("--at")
        if name == "add":
            p.add_argument("--book", required=True); p.add_argument("--from", dest="from_", required=True); p.add_argument("--to", required=True)
            p.add_argument("--steps"); p.add_argument("--note", default=""); p.add_argument("--notify")
        if name == "check":
            p.add_argument("--books", required=True); p.add_argument("--steps", default="")
    a = ap.parse_args(argv)
    return {"list": cmd_list, "add": cmd_add, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
