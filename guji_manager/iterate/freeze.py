"""三书冻结日历（T6）：把殿本/史記/全唐文的冻结期写进一个共享 yaml，PR 合 dev 前查有没有撞（框架 8.3）。

日历文件（建议放 ai-team `domain/CV/质检/迭代降人审框架/冻结日历.yaml`，各线只读，A31 维护）：

  freezes:
    - {book: dianben, layer: struct, from: "2026-11-05 10:00", to: "2026-11-05 22:00", steps: ["*"], note: "r5 统一重跑"}
  时间一律洛杉矶时间；layer 是 struct（结构轮：整册从 border_detect 起，冻结期内别合会改指纹的 PR）或 decision（决策轮：只冻 seed_admit 及之后）。
  steps 写受冻结的 Step 名，["*"]＝全部。

  guji-manager iterate freeze list  --file 冻结日历.yaml [--at "2026-11-05 12:00"]
  guji-manager iterate freeze add   --file … --book sj --from … --to … [--layer decision] [--steps seed_admit,glyph_pin] [--note …]
  guji-manager iterate freeze check --file … --books dianben,sj --steps seed_admit [--at …]
      # PR 描述里写「影响哪几本书、哪几步指纹」，合并前跑这条；撞了退出码 3，写明撞的是谁的冻结
cv PR 模板建议加一行：`影响的书／Step／指纹变化：`（A20 在 cv 仓加）。
"""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

import yaml

FMT = "%Y-%m-%d %H:%M"
#: 决策层的 Step（冻结 layer=decision 时只管这些及其后）；顺序取自殿本流水线
DECISION_STEPS = ("seed_admit", "glyph_pin", "group_flow", "group_flow_llm", "finalize", "ctx_ruling", "publish")


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
    if "*" not in steps and step not in steps:
        return False
    if f.get("layer") == "decision" and "*" in steps and step not in DECISION_STEPS:
        return False
    return True


def conflicts(freezes: list[dict], books: list[str], steps: list[str], at: datetime.datetime) -> list[dict]:
    steps = steps or ["*"]
    out = []
    for f in active(freezes, at):
        if f["book"] not in books:
            continue
        if any(s == "*" or _covers(f, s) for s in steps):
            out.append(f)
    return out


def cmd_list(a) -> int:
    fr = load(a.file)
    at = parse_t(a.at) if a.at else now_la()
    act = {id(f) for f in active(fr, at)}
    print(f"现在（洛杉矶）{at.strftime(FMT)}；共 {len(fr)} 条")
    for f in sorted(fr, key=lambda f: parse_t(f["from"])):
        tag = "冻结中" if id(f) in act else ("已过" if parse_t(f["to"]) < at else "待到")
        print(f"[{tag}] {f['book']} {f.get('layer', 'struct')} {f['from']} → {f['to']} steps={','.join(f.get('steps') or ['*'])} {f.get('note', '')}")
    return 0


def cmd_add(a) -> int:
    fr = load(a.file)
    parse_t(a.from_), parse_t(a.to)
    fr.append({"book": a.book, "layer": a.layer, "from": a.from_, "to": a.to,
               "steps": a.steps.split(",") if a.steps else ["*"], "note": a.note})
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
        print(f"✗ 撞冻结：{f['book']} {f.get('layer', 'struct')} {f['from']} → {f['to']} {f.get('note', '')}")
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
            p.add_argument("--layer", choices=("struct", "decision"), default="struct"); p.add_argument("--steps"); p.add_argument("--note", default="")
        if name == "check":
            p.add_argument("--books", required=True); p.add_argument("--steps", default="")
    a = ap.parse_args(argv)
    return {"list": cmd_list, "add": cmd_add, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
