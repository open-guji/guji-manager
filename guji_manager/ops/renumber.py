"""册号改位数的迁移工具（用户 11-27 定册号位数按全书册数统一：1–9 册 1 位、10–99 两位、100 起三位）。

一部书一次改完，缺省只出清单（dry-run），``--apply`` 才动手，动手时写回滚清单，``--rollback`` 一键还原。

改什么
------
1. **book-text**（``--book-text``，本仓根）：本书各版本目录里 cv 出的章（章条目带 ``char_file``）：
   - 章文件改名：``<旧>.*`` → ``<新>.*``（char、cord、norm、punct、entity、fig、pending 等，按前缀通配，不列死）；
   - ``fig/<旧>/`` 目录 → ``fig/<新>/``，``<新>.fig.json`` 里的 ``fig/<旧>/`` 路径跟着改；
   - ``index.json``：``file`` 与所有 ``*_file`` 字段（值以 ``<旧>.`` 开头的）改成新章号。
   文件内容里的册用整数 ``volume``，不含章号字符串，不用改。
2. **数据目录**（``--data-dir``，``guji db pull`` 拉下的本工作区数据目录）：
   - ``feedback/lists/**/<书 id>/<旧>.*`` → ``<新>.*``（待审单 ``proofing/…pending.json``、待审条目 ``pending/…items.jsonl`` 等）；
   - ``config/book_defaults.yaml``：``volume_width`` 改成新位数，删掉 ``chapter_width`` 行。
   改完由执行方 ``guji db push -w <工作区> --allow-delete`` 推回中心库（旧路径的行随之删除）。

不改什么
--------
- 已发出的待审单 rev（``001-r3`` 这类）是不透明的单号，网站本机已回应记录、票都挂在上面，**不改写**；之后新出的单按新章号起名。
- cv 内部册名（中心库事件、钉子账的主键）、R2 页表：不在本工具范围。
- 进度表 ``progress_volume``（D1 表）：清单里列出提醒，另行处理。

新旧同时存在（例如同一册既有 ``001`` 又有 ``01`` 的待审条目）算冲突，整书不动，清单里列出，要先人工合并。

用法::

    python -m guji_manager.ops.renumber --text 99k3i35yww --to-width 1 \\
        --book-text ~/book-text --data-dir ~/.guji-data/main/99k3i35yww            # 只出清单
    python -m guji_manager.ops.renumber … --apply --manifest renumber-99k3i35yww.json
    python -m guji_manager.ops.renumber --rollback renumber-99k3i35yww.json --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_DIGITS = re.compile(r"\d+")


def new_label(old: str, width: int) -> str:
    return str(int(old)).zfill(max(1, int(width)))


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


@dataclass
class Plan:
    moves: list[dict] = field(default_factory=list)      # {"from", "to"}（文件或目录）
    edits: list[dict] = field(default_factory=list)      # {"path", "before", "after"}（全文）
    conflicts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    chapters: dict[str, str] = field(default_factory=dict)  # 旧章号 → 新章号

    def summary(self) -> dict:
        return {"chapters": self.chapters, "moves": len(self.moves), "edits": len(self.edits),
                "conflicts": self.conflicts, "notes": self.notes}


def find_entry(book_text: Path, text_id: str) -> Path:
    for top in ("Book", "Work"):
        hits = list((book_text / top).glob(f"*/*/*/{text_id}"))
        if hits:
            return hits[0]
    raise SystemExit(f"book-text 里找不到 {text_id}")


def _plan_version(vdir: Path, width: int, plan: Plan) -> None:
    ip = vdir / "index.json"
    raw = ip.read_text(encoding="utf-8")
    idx = json.loads(raw)
    chapters = idx.get("chapters") or []
    if not any(isinstance(c, dict) and c.get("char_file") for c in chapters):
        return                                             # 不是 cv 出的版本（转录本等）不动
    renamed: dict[str, str] = {}
    for c in chapters:
        old = str(c.get("file") or "")
        if not c.get("char_file") or not _DIGITS.fullmatch(old):
            continue
        new = new_label(old, width)
        if new == old:
            continue
        renamed[old] = new
        c["file"] = new
        for k, v in list(c.items()):
            if k.endswith("_file") and isinstance(v, str) and v.startswith(old + "."):
                c[k] = new + v[len(old):]
    if not renamed:
        return
    existing = {p.name for p in vdir.iterdir()}
    moved_away = {n for n in existing if any(n.startswith(o + ".") for o in renamed)}
    for old, new in renamed.items():
        plan.chapters.setdefault(old, new)
        for p in sorted(vdir.iterdir()):
            if p.is_file() and p.name.startswith(old + "."):
                dst = vdir / (new + p.name[len(old):])
                if dst.name in existing and dst.name not in moved_away:
                    plan.conflicts.append(f"{dst} 已存在")
                plan.moves.append({"from": str(p), "to": str(dst)})
        fig = vdir / "fig" / old
        if fig.is_dir():
            if (vdir / "fig" / new).exists():
                plan.conflicts.append(f"{vdir / 'fig' / new} 已存在")
            plan.moves.append({"from": str(fig), "to": str(vdir / "fig" / new)})
            fj = vdir / f"{old}.fig.json"
            if fj.is_file():
                t = fj.read_text(encoding="utf-8")
                t2 = t.replace(f"fig/{old}/", f"fig/{new}/")
                if t2 != t:
                    # 改名之后再改内容：记新路径
                    plan.edits.append({"path": str(vdir / f"{new}.fig.json"), "before": t, "after": t2})
    after = json.dumps(idx, ensure_ascii=False, indent=2) + ("\n" if raw.endswith("\n") else "")
    plan.edits.append({"path": str(ip), "before": raw, "after": after})


def plan_book_text(book_text: Path, text_id: str, width: int, plan: Plan, versions: list[str] | None = None) -> None:
    entry = find_entry(book_text, text_id)
    for vdir in sorted(p for p in entry.iterdir() if p.is_dir() and (p / "index.json").is_file()):
        if versions and vdir.name not in versions:
            continue
        _plan_version(vdir, width, plan)


def plan_data_dir(data_dir: Path, text_id: str, width: int, plan: Plan) -> None:
    lists = data_dir / "feedback" / "lists"
    if lists.is_dir():
        for d in sorted(p for p in lists.rglob(text_id) if p.is_dir()):
            names = {p.name for p in d.iterdir()}
            for p in sorted(d.iterdir()):
                m = re.fullmatch(r"(\d+)(\..+)", p.name)
                if not p.is_file() or not m:
                    continue
                old, rest = m.group(1), m.group(2)
                new = new_label(old, width)
                if new == old:
                    continue
                plan.chapters.setdefault(old, new)
                if new + rest in names:
                    plan.conflicts.append(f"{d / (new + rest)} 与 {p.name} 同时存在，先人工合并")
                plan.moves.append({"from": str(p), "to": str(d / (new + rest))})
    cfg = data_dir / "config" / "book_defaults.yaml"
    if cfg.is_file():
        t = cfg.read_text(encoding="utf-8")
        t2 = re.sub(r"(?m)^volume_width:.*$", f"volume_width: {width}          # 全书册数定位数（用户 11-27）", t)
        if not re.search(r"(?m)^volume_width:", t):
            t2 = t2.rstrip("\n") + f"\nvolume_width: {width}\n"
        t2 = re.sub(r"(?m)^chapter_width:.*\n", "", t2)
        if t2 != t:
            plan.edits.append({"path": str(cfg), "before": t, "after": t2})
    plan.notes.append("进度表 progress_volume（D1）里本书的册行另行改号、清重复行")
    plan.notes.append("已发待审单的 rev（如 001-r3）不改写；新单按新章号起名")


def apply(plan: Plan) -> None:
    if plan.conflicts:
        raise SystemExit("有冲突，整书不动：\n  " + "\n  ".join(plan.conflicts))
    # 先校验 edit 的原文没被别人改过
    for e in plan.edits:
        src = Path(e["path"])
        # fig.json 的 edit 记的是改名后的路径，改名前在旧路径
        pre = next((Path(m["from"]) for m in plan.moves if m["to"] == e["path"]), src)
        if pre.read_text(encoding="utf-8") != e["before"]:
            raise SystemExit(f"{pre} 在出清单后被改过，重出清单再跑")
    for m in plan.moves:
        dst = Path(m["to"])
        if dst.exists():
            raise SystemExit(f"{dst} 已存在，停下（已做的改名见回滚清单）")
        Path(m["from"]).rename(dst)
    for e in plan.edits:
        Path(e["path"]).write_text(e["after"], encoding="utf-8")


def rollback_plan(manifest: dict) -> Plan:
    p = Plan()
    p.edits = [{"path": e["path"], "before": e["after"], "after": e["before"]} for e in manifest["edits"]]
    p.moves = [{"from": m["to"], "to": m["from"]} for m in reversed(manifest["moves"])]
    # 回滚时先还原内容（在新路径上）再改回名字
    return p


def apply_rollback(plan: Plan) -> None:
    for e in plan.edits:
        if Path(e["path"]).read_text(encoding="utf-8") != e["before"]:
            raise SystemExit(f"{e['path']} 迁移后又被改过，回滚会丢改动，停下")
    for e in plan.edits:
        Path(e["path"]).write_text(e["after"], encoding="utf-8")
    for m in plan.moves:
        if Path(m["to"]).exists():
            raise SystemExit(f"{m['to']} 已存在，停下")
        Path(m["from"]).rename(Path(m["to"]))


def _print(plan: Plan, out=sys.stdout) -> None:
    print(json.dumps(plan.summary(), ensure_ascii=False, indent=2), file=out)
    for m in plan.moves:
        print(f"mv   {m['from']}  →  {Path(m['to']).name}", file=out)
    for e in plan.edits:
        print(f"edit {e['path']}  {_sha(e['before'].encode())} → {_sha(e['after'].encode())}", file=out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m guji_manager.ops.renumber", description=__doc__.split("\n")[0])
    ap.add_argument("--text", help="书 id（book-text 条目 id，也是数据目录 feedback/lists/** 下的目录名）")
    ap.add_argument("--to-width", type=int, help="新位数（按全书册数：1–9 册 1、10–99 册 2、100 起 3）")
    ap.add_argument("--book-text", type=Path, help="book-text 仓根")
    ap.add_argument("--data-dir", type=Path, help="本工作区数据目录（guji db pull 后的 ~/.guji-data/main/<ws>）")
    ap.add_argument("--versions", nargs="*", help="只改这些版本目录（缺省所有 cv 出的版本）")
    ap.add_argument("--apply", action="store_true", help="动手（缺省只出清单）")
    ap.add_argument("--manifest", type=Path, help="--apply 时写回滚清单到这里（缺省 renumber-<书>.json）")
    ap.add_argument("--rollback", type=Path, help="按回滚清单还原（配 --apply 才动手）")
    a = ap.parse_args(argv)
    if a.rollback:
        plan = rollback_plan(json.loads(a.rollback.read_text(encoding="utf-8")))
        _print(plan)
        if a.apply:
            apply_rollback(plan)
            print("已还原", file=sys.stderr)
        return 0
    if not (a.text and a.to_width):
        ap.error("要 --text 与 --to-width")
    if not (a.book_text or a.data_dir):
        ap.error("--book-text、--data-dir 至少给一个")
    plan = Plan()
    if a.book_text:
        plan_book_text(a.book_text, a.text, a.to_width, plan, a.versions)
    if a.data_dir:
        plan_data_dir(a.data_dir, a.text, a.to_width, plan)
    _print(plan)
    if plan.conflicts:
        print(f"冲突 {len(plan.conflicts)} 处，不能 --apply", file=sys.stderr)
        return 1
    if a.apply:
        mf = a.manifest or Path(f"renumber-{a.text}.json")
        mf.write_text(json.dumps({"text": a.text, "to_width": a.to_width, "moves": plan.moves, "edits": plan.edits},
                                 ensure_ascii=False), encoding="utf-8")
        apply(plan)
        print(f"已改；回滚清单 {mf}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
