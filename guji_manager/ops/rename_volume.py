"""cv 内部册名改名（用户 11-27 定：老书 cv 册名也按新位数改，「只改、不重跑，过期不管」）。

例：殿本 ``vol01``→``01``、脉经 ``01``→``1``、北行 ``bxgb``→``1``。一次一部书（可多册），缺省只出清单，
``--apply`` 才动手；动手前把要改的文件原样备份到 ``--backup``，``--rollback <备份目录> --apply`` 一键还原。

改什么
------
1. **产物**（``--products``，本机产物根）：``<旧>/`` → ``<新>/``；目录下每个 JSON（含 ``_prev/``、manifest）里
   格号前缀换新名（``"vol01:88:6:9"`` → ``"01:88:6:9"``，``"cols:vol01:…"`` 同理）、``"book": "vol01"`` 换新名。
   改写后文件 sha 变了：manifest 等处记的旧 sha 按「改写前→改写后」对照表一并换掉；
   由上游 sha 合成的指纹没法换，下游会判过期——不重跑（用户定），close-check／exit-check 要认这种过期。
2. **图像缓存**（``--cache``）：``<旧>/`` → ``<新>/``，``_stamps.json`` 里的产物 sha 按对照表换。
3. **数据目录**（``--data-dir``，``guji db pull`` 拉下的本工作区数据目录）：
   - ``books/<旧>.yaml`` → ``books/<新>.yaml``：``id`` 改新名、加 ``aliases: [旧]``，yaml 里写的完整格号换新名；
   - 按册存的文件 ``feedback/{anchors,uid,notes}/<旧>.jsonl``、``feedback/lists/u_void/<旧>.jsonl``：改名并改写内容；
     u 账 ``cells_sha`` 按产物 sha 对照表换（不换就按新切分查不到 u）；
   - ``feedback/verdicts/**/*.jsonl``、``config/*.jsonl``：内容里的格号换新名（文件名不变）。
   改完由执行方 ``guji db push -w <工作区> --allow-delete`` 推回中心库。

不改什么
--------
- **事件**（``feedback/events/``）：只追加，不改写；cv 读时按册 yaml 的 ``aliases`` 换名（cv #1970）。
- **字形库**（``output/glyph_store/``）与一切实例 id（``v2:vol01:…``、``bare~r2~vol01~…``）：不透明编号，不改。
- 原图目录（册 yaml ``raw_dir``）：照旧指向原处。
- book-text 章号、待审单：归 ``ops/renumber``。

改完扫一遍：数据目录其他文件里还挂旧名的，清单里列出（只报不改）。

用法::

    python -m guji_manager.ops.rename_volume --map 01=1 --map 02=2 \\
        --data-dir ~/.guji-data/main/99k3i35yww --products <ws>/products --cache <ws>/cache      # 只出清单
    python -m guji_manager.ops.rename_volume … --apply --backup rename-99k3i35yww
    python -m guji_manager.ops.rename_volume --rollback rename-99k3i35yww --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

#: 字形库实例 id 的命名空间前缀：不改（同 cv core/volume_alias.INSTANCE_NS）。
INSTANCE_NS = ("v1", "v2")
BOOK_FIELDS = ("book", "vol", "book_id", "volume_id")
PER_BOOK = ("feedback/anchors", "feedback/uid", "feedback/notes", "feedback/lists/u_void")
CONTENT_GLOBS = ("feedback/verdicts/**/*.jsonl", "config/*.jsonl")
_HEX = re.compile(r"[0-9a-f]{64}")


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Rewriter:
    """把文本里的旧册名换新名：引号开头的格号（可带非实例前缀）、``book`` 一类字段的整值。"""

    def __init__(self, amap: dict[str, str]):
        self.amap = dict(amap)
        alt = "|".join(re.escape(k) for k in sorted(amap, key=len, reverse=True))
        ns = "|".join(INSTANCE_NS)
        # 带前缀（`cols:01:171`）后面一段就够；不带前缀要像格号（册:页:列:格 或 册/页:…），免得误伤 "01:30" 这类时刻
        self._cell = re.compile(r'"(?:((?!(?:' + ns + r'):)[a-z][a-z0-9_]*:)(' + alt + r')([:/]\d)'
                                r'|()(' + alt + r')((?::\d+){2}:\d|/\d))')
        self._field = re.compile(r'("(?:' + "|".join(BOOK_FIELDS) + r')"\s*:\s*)"(' + alt + r')"')
        # yaml：不带引号也认，要求后面至少还有三段（册:页:列:格），免得误伤时刻之类
        self._yaml = re.compile(r'(?<![\w:~])(' + alt + r')(?=:\d+:\d+:\d)')

    def json_text(self, t: str) -> tuple[str, int]:
        def cell(m):
            pre, old, rest = (m.group(1), m.group(2), m.group(3)) if m.group(2) else ("", m.group(5), m.group(6))
            return f'"{pre}{self.amap[old]}{rest}'
        t, a = self._cell.subn(cell, t)
        t, b = self._field.subn(lambda m: f'{m.group(1)}"{self.amap[m.group(2)]}"', t)
        return t, a + b

    def yaml_text(self, t: str) -> tuple[str, int]:
        return self._yaml.subn(lambda m: self.amap[m.group(1)], t)


def remap_shas(t: str, shamap: dict[str, str]) -> tuple[str, int]:
    n = 0

    def sub(m):
        nonlocal n
        v = shamap.get(m.group(0))
        if v is None:
            return m.group(0)
        n += 1
        return v
    return _HEX.sub(sub, t), n


@dataclass
class Plan:
    amap: dict[str, str]
    moves: list[dict] = field(default_factory=list)      # 目录或文件 {"from", "to"}
    rewrite_json: list[str] = field(default_factory=list)  # 改名后的路径
    rewrite_yaml: list[str] = field(default_factory=list)
    stamps: list[str] = field(default_factory=list)
    uid: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    leftovers: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def summary(self) -> dict:
        return {"map": self.amap, "moves": len(self.moves), "rewrite_json": len(self.rewrite_json),
                "rewrite_yaml": len(self.rewrite_yaml), "stamps": len(self.stamps), "uid": len(self.uid),
                "conflicts": self.conflicts, "leftovers": self.leftovers, "counts": self.counts}


def _move(plan: Plan, src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    if dst.exists():
        plan.conflicts.append(f"{dst} 已存在（{src.name} 改不过去）")
    plan.moves.append({"from": str(src), "to": str(dst)})
    return True


def build_plan(amap: dict[str, str], data_dir: Path | None, products: Path | None, cache: Path | None) -> Plan:
    plan = Plan(amap)
    clash = sorted(set(amap) & set(amap.values()))
    if clash:
        plan.conflicts.append(f"新旧名重叠 {clash}：一次改不了，先改到中间名")
    rw = Rewriter(amap)
    for old, new in amap.items():
        if products is not None and _move(plan, products / old, products / new):
            plan.rewrite_json += [str(products / new / p.relative_to(products / old))
                                  for p in sorted((products / old).rglob("*.json"))]
        if cache is not None and _move(plan, cache / old, cache / new):
            plan.stamps += [str(cache / new / p.relative_to(cache / old))
                            for p in sorted((cache / old).rglob("_stamps.json"))]
        if data_dir is None:
            continue
        if _move(plan, data_dir / "books" / f"{old}.yaml", data_dir / "books" / f"{new}.yaml"):
            plan.rewrite_yaml.append(str(data_dir / "books" / f"{new}.yaml"))
        for sub in PER_BOOK:
            dst = data_dir / sub / f"{new}.jsonl"
            if _move(plan, data_dir / sub / f"{old}.jsonl", dst):
                (plan.uid if sub == "feedback/uid" else plan.rewrite_json).append(str(dst))
    if data_dir is not None:
        for g in CONTENT_GLOBS:
            for p in sorted(data_dir.glob(g)):
                if rw.json_text(p.read_text(encoding="utf-8"))[1]:
                    plan.rewrite_json.append(str(p))
        touched = {Path(m["from"]) for m in plan.moves} | {Path(p) for p in plan.rewrite_json}
        for p in sorted(data_dir.rglob("*")):
            if not p.is_file() or p in touched or p.suffix not in (".json", ".jsonl", ".yaml"):
                continue
            rel = p.relative_to(data_dir).as_posix()
            if rel.startswith(("feedback/events/", "output/glyph_store/")):
                continue
            try:
                n = rw.json_text(p.read_text(encoding="utf-8"))[1]
            except UnicodeDecodeError:
                continue
            if n:
                plan.leftovers.append(f"{rel}（{n} 处）")
    return plan


def _backup(src: Path, backup: Path) -> None:
    dst = backup / "files" / str(src.resolve()).lstrip("/")
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def apply(plan: Plan, backup: Path) -> dict:
    if plan.conflicts:
        raise SystemExit("有冲突，整书不动：\n  " + "\n  ".join(plan.conflicts))
    backup.mkdir(parents=True, exist_ok=True)
    rw = Rewriter(plan.amap)
    log = {"map": plan.amap, "moves": [], "files": []}

    def save_log():
        (backup / "rename-log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")

    for m in plan.moves:
        src, dst = Path(m["from"]), Path(m["to"])
        if dst.exists():
            save_log()
            raise SystemExit(f"{dst} 已存在，停下（已做的见 {backup}/rename-log.json）")
        src.rename(dst)
        log["moves"].append(m)
        save_log()

    orig: dict[str, str] = {}      # 路径 → 改写前 sha
    cur: dict[str, str] = {}       # 改写前 sha → 现 sha（跟着多遍改写走到最后）

    def edit(path: str, fn) -> None:
        p = Path(path)
        t = p.read_text(encoding="utf-8")
        t2, n = fn(t)
        if t2 == t:
            return
        _backup(p, backup)
        o = orig.setdefault(path, _sha(p))
        p.write_text(t2, encoding="utf-8")
        cur[o] = _sha(p)
        if path not in log["files"]:
            log["files"].append(path)
        plan.counts[p.suffix] = plan.counts.get(p.suffix, 0) + n

    # 第一遍换名（出 sha 对照表），第二遍把 manifest 等处记的旧 sha 换成新的；第二遍改动的文件 sha 再变，
    # cur 记的是走到最后的 sha。缓存戳与 u 账用最终对照表。
    for f in plan.rewrite_json:
        edit(f, rw.json_text)
    first = dict(cur)
    for f in plan.rewrite_json:
        edit(f, lambda t: remap_shas(t, first))
    for f in plan.stamps:
        edit(f, lambda t: remap_shas(t, cur))
    for f in plan.rewrite_yaml:
        edit(f, lambda t: _yaml_book(t, rw))
    final = dict(cur)
    for f in plan.uid:
        edit(f, lambda t: _uid_text(t, rw, final))
    shamap = final
    save_log()
    (backup / "shamap.json").write_text(json.dumps(shamap, indent=0), encoding="utf-8")
    return log


def _yaml_book(t: str, rw: Rewriter) -> tuple[str, int]:
    n = 0
    m = re.search(r'(?m)^id:\s*"?([^"\s#]+)"?', t)
    old = m.group(1) if m else None
    if old in rw.amap:
        new = rw.amap[old]
        t = t[:m.start()] + f'id: "{new}"\naliases: ["{old}"]          # 11-27 册号位数统一改名，旧名读时换新名' + t[m.end():]
        n += 1
    t, k = rw.yaml_text(t)
    return t, n + k


def _uid_text(t: str, rw: Rewriter, shamap: dict[str, str]) -> tuple[str, int]:
    t, a = rw.json_text(t)
    t, b = remap_shas(t, shamap)
    return t, a + b


def rollback(backup: Path) -> None:
    log = json.loads((backup / "rename-log.json").read_text(encoding="utf-8"))
    for f in log["files"]:
        src = backup / "files" / str(Path(f).resolve()).lstrip("/")
        if src.exists():
            shutil.copy2(src, f)
    for m in reversed(log["moves"]):
        dst, src = Path(m["from"]), Path(m["to"])
        if dst.exists():
            raise SystemExit(f"{dst} 已存在，停下")
        src.rename(dst)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m guji_manager.ops.rename_volume", description=__doc__.split("\n")[0])
    ap.add_argument("--map", action="append", default=[], help="旧=新，一册一个，可重复")
    ap.add_argument("--data-dir", type=Path)
    ap.add_argument("--products", type=Path, help="本机产物根（<工作区>/products）")
    ap.add_argument("--cache", type=Path, help="本机图像缓存根")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup", type=Path, help="--apply 时的备份目录（必填）")
    ap.add_argument("--rollback", type=Path, help="按备份目录还原（配 --apply）")
    a = ap.parse_args(argv)
    if a.rollback:
        if not a.apply:
            print(f"会按 {a.rollback}/rename-log.json 还原；加 --apply 动手")
            return 0
        rollback(a.rollback)
        print("已还原")
        return 0
    amap = dict(x.split("=", 1) for x in a.map)
    if not amap:
        ap.error("至少一个 --map 旧=新")
    plan = build_plan(amap, a.data_dir, a.products, a.cache)
    print(json.dumps(plan.summary(), ensure_ascii=False, indent=2))
    for m in plan.moves:
        print(f"mv {m['from']} → {m['to']}")
    if not a.apply:
        return 1 if plan.conflicts else 0
    if not a.backup:
        ap.error("--apply 要给 --backup")
    apply(plan, a.backup)
    print(json.dumps(plan.counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
