"""cv 内部册名改名（用户 11-27 定：老书 cv 册名也按新位数改，「只改、不重跑，过期不管」）。

例：殿本 ``vol01``→``01``、脉经 ``01``→``1``、北行 ``bxgb``→``1``。一次一部书（可多册），缺省只出清单，
``--apply`` 才动手；动手前把要改的文件原样备份到 ``--backup``，``--rollback <备份目录> --apply`` 一键还原。

改什么
------
1. **产物**（``--products``，本机产物根）：``<旧>/`` → ``<新>/``；目录下每个 JSON（含 ``_prev/``、manifest）里
   格号前缀换新名（``"vol01:88:6:9"`` → ``"01:88:6:9"``，``"cols:vol01:…"`` 同理）、``"book": "vol01"`` 换新名。
   改写后文件 sha 变了：各步 ``_manifest.jsonl`` 条目自己的 ``sha256`` 换新，``upstream`` 不动；改写前后 sha 对照表
   写进 ``<新>/_renamed.json``。下游指纹按实判「上游产物变了」，cv ``status`` 读这个标记认出「只因改名」、
   算新鲜（cv ``Engine.rename_only``，#1977）；真跑 pipeline 时照常重跑（用户定：只改不重跑，过期不管）。
2. **图像缓存**（``--cache``）：``<旧>/`` → ``<新>/``，``_stamps.json`` 里的产物 sha 按对照表换。
3. **数据目录**（``--data-dir``，``guji db pull`` 拉下的本工作区数据目录）：
   - ``books/<旧>.yaml`` → ``books/<新>.yaml``：``id`` 改新名、加 ``aliases: [旧]``，yaml 里写的完整格号换新名；
   - 按册存的文件 ``feedback/{anchors,uid,notes}/<旧>.jsonl``、``feedback/lists/u_void/<旧>.jsonl``：改名并改写内容；
     u 账 ``cells_sha`` 按产物 sha 对照表换（不换就按新切分查不到 u）；
   - ``feedback/verdicts/**/*.jsonl``、``config/*.jsonl``：内容里的格号换新名（文件名不变）。
   - 按册的目录 ``feedback/anchor_patches/<旧>/`` → ``<新>/``（cv ``anchor.patch_path`` 按册名找图块）。
   - 数据目录里其余 json／jsonl（``feedback/rulings/``、``config/groups/``、``review/batches/``、``touch_label_verdicts`` 等）：
     格号换新名，内容里出现的产物 sha（如 ``cells_sha``）按改写前后对照表换（11-28 殿本演练查出这几类原先只报不改）。
   改完由执行方 ``guji db push -w <工作区> --allow-delete`` 推回中心库。

不改什么
--------
- **R2 原图登记**（``source/by-ws/<ws>/<册>.json``）：``--apply`` 末尾给新名补一份指针（指向旧名同一书同一册，旧的不删）；漏了的书用 ``--r2-only --ws <工作区> --map 旧=新 … --apply`` 补（11-28 北行漏这步，取原图 404）。
- **事件**（``feedback/events/``）：只追加，不改写；cv 读时按册 yaml 的 ``aliases`` 换名（cv #1970）。
- **字形库**（``output/glyph_store/``）与一切实例 id（``v2:vol01:…``、``bare~r2~vol01~…``）：不透明编号，不改。
- 原图目录（册 yaml ``raw_dir``）：照旧指向原处。
- book-text 章号、待审单：归 ``ops/renumber``。

- ``corpus/``（钉 sha 的语料，改写会让钉子对不上；cv 读时认 ``aliases``）、``feedback/lists/pending/``（待审单归
  ``ops/renumber`` 与网站归一）：只报不改，列在清单的 ``leftovers`` 里。

已经改过名、用旧版工具（manager ≤0.7.1）做的书，用 ``--repair <当时的备份目录> --data-dir … --apply`` 补做上面新加的几类：
按备份里的 ``rename-log.json`` 取改名表、``shamap.json`` 取产物 sha 对照表，只动数据目录，另存一份备份到 ``<备份>/repair-<时间>/``。

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
MARKER = "_renamed.json"
CONTENT_GLOBS = ("feedback/verdicts/**/*.jsonl", "config/*.jsonl")
PER_BOOK_DIRS = ("feedback/anchor_patches",)
#: 只报不改：事件只追加；字形库实例 id 不透明；corpus 钉 sha；待审单归 renumber／网站。
REPORT_ONLY = ("feedback/events/", "output/glyph_store/", "corpus/", "feedback/lists/pending/")
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
    products_json: list[str] = field(default_factory=list)   # 产物页（改名后的路径）
    manifests: list[str] = field(default_factory=list)       # 各步 _manifest.jsonl
    renamed: dict[str, str] = field(default_factory=dict)    # 产物目录 新名 → 旧名
    products_root: Path | None = None
    rewrite_json: list[str] = field(default_factory=list)    # 数据目录里改内容的 jsonl（改名后的路径）
    rewrite_yaml: list[str] = field(default_factory=list)
    stamps: list[str] = field(default_factory=list)
    uid: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    leftovers: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def summary(self) -> dict:
        return {"map": self.amap, "moves": len(self.moves), "products": len(self.products_json),
                "manifests": len(self.manifests), "rewrite_json": len(self.rewrite_json),
                "rewrite_yaml": len(self.rewrite_yaml), "stamps": len(self.stamps), "uid": len(self.uid),
                "conflicts": self.conflicts, "leftovers": self.leftovers, "counts": self.counts}


def _move(plan: Plan, src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    if dst.exists():
        plan.conflicts.append(f"{dst} 已存在（{src.name} 改不过去）")
    plan.moves.append({"from": str(src), "to": str(dst)})
    return True


def build_plan(amap: dict[str, str], data_dir: Path | None, products: Path | None, cache: Path | None,
               shamap: dict[str, str] | None = None) -> Plan:
    """`shamap`（`--repair`）：上次改名的产物 sha 对照表；内容里带这些旧 sha 的数据文件也要改写。"""
    plan = Plan(amap, products_root=products)
    clash = sorted(set(amap) & set(amap.values()))
    if clash:
        plan.conflicts.append(f"新旧名重叠 {clash}：一次改不了，先改到中间名")
    rw = Rewriter(amap)
    for old, new in amap.items():
        if products is not None and _move(plan, products / old, products / new):
            plan.products_json += [str(products / new / p.relative_to(products / old))
                                   for p in sorted((products / old).rglob("*.json")) if p.name != MARKER]
            plan.manifests += [str(products / new / p.relative_to(products / old))
                               for p in sorted((products / old).rglob("_manifest.jsonl"))]
            plan.renamed[new] = old
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
        for sub in PER_BOOK_DIRS:
            _move(plan, data_dir / sub / old, data_dir / sub / new)
    if data_dir is not None:
        for g in CONTENT_GLOBS:
            for p in sorted(data_dir.glob(g)):
                if rw.json_text(p.read_text(encoding="utf-8"))[1]:
                    plan.rewrite_json.append(str(p))
        moved = {Path(m["from"]) for m in plan.moves}
        touched = {Path(p) for p in plan.rewrite_json} | {Path(p) for p in plan.uid} | {Path(p) for p in plan.rewrite_yaml}
        old_shas = set(shamap or ())
        for p in sorted(data_dir.rglob("*")):
            if not p.is_file() or p in touched or p in moved or any(d in p.parents for d in moved):
                continue
            if p.suffix not in (".json", ".jsonl", ".yaml"):
                continue
            rel = p.relative_to(data_dir).as_posix()
            if rel.startswith(("feedback/events/", "output/glyph_store/")):
                continue
            try:
                t = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            n = rw.json_text(t)[1]
            hit = bool(old_shas) and any(h in old_shas for h in _HEX.findall(t))
            if not (n or hit):
                continue
            if rel.startswith(REPORT_ONLY) or p.suffix == ".yaml":
                if n:
                    plan.leftovers.append(f"{rel}（{n} 处）")
                continue
            plan.rewrite_json.append(str(p))
    return plan


def _backup(src: Path, backup: Path) -> None:
    dst = backup / "files" / str(src.resolve()).lstrip("/")
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def apply(plan: Plan, backup: Path, shamap: dict[str, str] | None = None) -> dict:
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

    # 产物页换名，记「改写前 sha → 改写后 sha」；manifest 只换各条目自己的 `sha256`（`upstream` 不动：
    # 下游照实判「上游产物变了」，close-check 拿改名标记里的对照表认出这是改名造成的，见 rename_only_stale）。
    for f in plan.products_json:
        edit(f, rw.json_text)
    prod_map = {**(shamap or {}), **cur}
    for f in plan.manifests:
        edit(f, lambda t: _manifest_text(t, rw, prod_map))
    for f in plan.stamps:
        edit(f, lambda t: remap_shas(t, prod_map))
    for f in plan.rewrite_json:
        edit(f, lambda t: _uid_text(t, rw, prod_map))       # 格号换名＋内容里的产物 sha（cells_sha 等）换新
    for f in plan.rewrite_yaml:
        edit(f, lambda t: _yaml_book(t, rw))
    for f in plan.uid:
        edit(f, lambda t: _uid_text(t, rw, prod_map))
    import time
    pj = set(plan.products_json)
    for new, old in plan.renamed.items():
        base = plan.products_root / new
        sub = {o: cur[o] for path, o in orig.items() if path in pj and Path(path).is_relative_to(base)}
        mk = base / MARKER
        mk.write_text(json.dumps({"from": old, "to": new, "ts": time.time(),
                                  "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "shamap": sub},
                                 ensure_ascii=False, indent=0), encoding="utf-8")
        log["files_created"] = log.get("files_created", []) + [str(mk)]
    save_log()
    (backup / "shamap.json").write_text(json.dumps(prod_map, indent=0), encoding="utf-8")
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


def _manifest_text(t: str, rw: Rewriter, shamap: dict[str, str]) -> tuple[str, int]:
    out, n = [], 0
    for line in t.splitlines(keepends=True):
        s = line.strip()
        if not s:
            out.append(line)
            continue
        line2, k = rw.json_text(line)
        d = json.loads(line2)
        if isinstance(d.get("sha256"), str) and d["sha256"] in shamap:
            d["sha256"] = shamap[d["sha256"]]
            line2 = json.dumps(d, ensure_ascii=False) + ("\n" if line.endswith("\n") else "")
            k += 1
        out.append(line2)
        n += k
    return "".join(out), n


def _uid_text(t: str, rw: Rewriter, shamap: dict[str, str]) -> tuple[str, int]:
    t, a = rw.json_text(t)
    t, b = remap_shas(t, shamap)
    return t, a + b


def rollback(backup: Path) -> None:
    log = json.loads((backup / "rename-log.json").read_text(encoding="utf-8"))
    for f in log.get("files_created", []):
        Path(f).unlink(missing_ok=True)
    for f in log["files"]:
        src = backup / "files" / str(Path(f).resolve()).lstrip("/")
        if src.exists():
            shutil.copy2(src, f)
    for m in reversed(log["moves"]):
        dst, src = Path(m["from"]), Path(m["to"])
        if dst.exists():
            raise SystemExit(f"{dst} 已存在，停下")
        src.rename(dst)


def r2_pointers(amap: dict[str, str], ws: str, *, write: bool = True, src=None) -> list[str]:
    """R2 原图登记（``source/by-ws/<ws>/<册>.json``）给新名补一份，指向旧名同一 (书 id, 册)。

    指针只增不改，旧名那份留着。11-28 北行 bxgb→1 改名漏了这一步，执行机取原图 404（任务 #18346）。
    返回每册一行结果；旧名没登记的册跳过（本来就不从 R2 取图）。"""
    from ..datastore import sources as S
    src = src or S._client()
    out = []
    for old, new in amap.items():
        try:
            book_id, vol = S.resolve(src, ws, old)
        except FileNotFoundError:
            out.append(f"{old}→{new}：旧名没有原图登记，跳过")
            continue
        if write:
            S.write_pointer(src, ws, new, book_id, vol)
        out.append(f"{old}→{new}：{'已写' if write else '要写'} {S.pointer_key(ws, new)} → {book_id}/{vol}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m guji_manager.ops.rename_volume", description=__doc__.split("\n")[0])
    ap.add_argument("--map", action="append", default=[], help="旧=新，一册一个，可重复")
    ap.add_argument("--data-dir", type=Path)
    ap.add_argument("--products", type=Path, help="本机产物根（<工作区>/products）")
    ap.add_argument("--cache", type=Path, help="本机图像缓存根")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup", type=Path, help="--apply 时的备份目录（必填）")
    ap.add_argument("--rollback", type=Path, help="按备份目录还原（配 --apply）")
    ap.add_argument("--ws", default=None, help="中心库工作区 id（R2 原图登记用）；缺省取 --data-dir 的目录名")
    ap.add_argument("--no-r2", action="store_true", help="--apply 时不补 R2 原图登记（新名指针）")
    ap.add_argument("--r2-only", action="store_true", help="只补 R2 原图登记（已改过名、当时漏了这步的书），配 --map 与 --ws；加 --apply 才写")
    ap.add_argument("--repair", type=Path, help="已用旧版工具改过名的书：按当时的备份目录补改数据目录（配 --data-dir）")
    a = ap.parse_args(argv)
    if a.repair:
        if not a.data_dir:
            ap.error("--repair 要给 --data-dir")
        log = json.loads((a.repair / "rename-log.json").read_text(encoding="utf-8"))
        sm = a.repair / "shamap.json"
        shamap = json.loads(sm.read_text(encoding="utf-8")) if sm.exists() else {}
        plan = build_plan(log["map"], a.data_dir, None, None, shamap=shamap)
        print(json.dumps(plan.summary(), ensure_ascii=False, indent=2))
        for m in plan.moves:
            print(f"mv {m['from']} → {m['to']}")
        if not a.apply:
            return 1 if plan.conflicts else 0
        import time
        apply(plan, a.repair / f"repair-{time.strftime('%Y%m%d-%H%M%S')}", shamap=shamap)
        print(json.dumps(plan.counts, ensure_ascii=False))
        return 0
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
    ws = a.ws or (a.data_dir.name if a.data_dir else None)
    if a.r2_only:
        if not ws:
            ap.error("--r2-only 要给 --ws 或 --data-dir")
        for ln in r2_pointers(amap, ws, write=a.apply):
            print(ln)
        return 0
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
    if not a.no_r2:
        if not ws:
            print("⚠ 没补 R2 原图登记（不知道工作区 id）：补跑 --r2-only --ws <工作区> --map … --apply", file=sys.stderr)
        else:
            try:
                for ln in r2_pointers(amap, ws):
                    print(ln)
            except Exception as e:  # noqa: BLE001 —— 本机改名已完成，指针补不上只提示
                print(f"⚠ R2 原图登记没补上（{type(e).__name__}: {str(e)[:200]}）：补跑 --r2-only --ws {ws} --map … --apply",
                      file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
