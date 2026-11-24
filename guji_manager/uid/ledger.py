"""字格身份账：``<feedback>/uid/<册>.jsonl``，每册一本，只追加。格式见 ``doc/参考/字格身份账.md``。

一行＝一页的一份切分入账：

    {"id": "uid-vol31-p0012-1a2b3c4d5e6f", "kind": "uid_ledger", "v": 1, "ts": "…", "src": "advance",
     "book": "vol31", "page": 12, "target": {"book": "vol31"},   # target 只给中心库 events 表的 book 列用；
                                                                  # 不写 page，免得换过图源的册推库时被页表 rev 闸拦
     "cells_sha": "<page_cells_sha 口径>" | null,
     "map": {"vol31:12:3:4": 1234, …},            # 完整格号 → u，键按读序
     "boxes": {"vol31:12:3:4": [x, y, w, h], …},  # cord 空间（左上原点），下次对照用
     "chars": {"vol31:12:3:4": "欽", …},          # 可无；字序列兜底用
     "lineage": [{"u": 9, "split_from": 8}, {"u": 7, "into": 6}, {"u": 5, "gone": true}, {"u": 10, "new": true}],
     "via": {"iou": 300, "new": 1, …}}

读法：一页的现行状态＝该页**最后一行**；cv 按「本页当前 cells_sha」找行，同 (page, cells_sha) 多行取最后一行，
``cells_sha`` 为 null 的行 cv 不用。全册 ``u_max``＝发过的最大号（含作废的）；作废号＝各行 lineage 里的 into／gone。

进中心库：``feedback/uid/*.jsonl`` 归 events 表（只追加，主键 (src_path, id)，stream=uid），每行一页、不会超行长上限。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

KIND = "uid_ledger"
VERSION = 1
_CELL = re.compile(r"^(?P<book>[^:]+):(?P<page>-?\d+):(?P<col>-?\d+):(?P<slot>-?\d+)(?P<sub>[a-z]*)$")


class UidMissing(KeyError):
    """册有身份账，但这一格查不到 u（入账漏了，或格号不是现行切分的）。不回退格号。"""


def parse_cell(cell_id: str) -> tuple[str, int]:
    """完整格号 ``册:页:列:格[a|b]`` → (册, 页)。"""
    m = _CELL.match(cell_id)
    if not m:
        raise ValueError(f"不是完整格号（册:页:列:格）：{cell_id!r}")
    return m["book"], int(m["page"])


def default_root() -> Path:
    """``<feedback>/uid``。feedback 根照 cv（``GUJI_FEEDBACK_DIR`` > 工作区 > 仓内）；没装 cv 时只认 ``GUJI_FEEDBACK_DIR``，
    再没有就是当前目录下的 ``feedback/``（这时一般没有账，``cell_ref`` 照旧恒等）。"""
    try:
        from .._cv import feedback_root
        return Path(feedback_root()) / "uid"
    except ImportError:
        return Path(os.environ.get("GUJI_FEEDBACK_DIR") or "feedback") / "uid"


def ledger_path(book: str, root: Path | str | None = None) -> Path:
    return Path(root) / f"{book}.jsonl" if root else default_root() / f"{book}.jsonl"


def line_id(book: str, page: int, cells_sha: str | None, umap: dict) -> str:
    h = hashlib.sha256(json.dumps([cells_sha, umap], ensure_ascii=False, sort_keys=False).encode()).hexdigest()[:12]
    return f"uid-{book}-p{page:04d}-{h}"


def make_line(book: str, page: int, cells_sha: str | None, umap: dict[str, int], *, boxes: dict | None = None,
              chars: dict | None = None, lineage: list | None = None, via: dict | None = None, src: str = "advance",
              ts: str | None = None) -> dict:
    d = {"id": line_id(book, page, cells_sha, umap), "kind": KIND, "v": VERSION,
         "ts": ts or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "src": src, "book": book, "page": page, "target": {"book": book},
         "cells_sha": cells_sha, "map": umap}
    if boxes:
        d["boxes"] = boxes
    if chars:
        d["chars"] = chars
    d["lineage"] = lineage or []
    if via:
        d["via"] = dict(via)
    return d


@dataclass
class Ledger:
    book: str
    path: Path
    lines: list[dict] = field(default_factory=list)

    # ── 读 ──
    @classmethod
    def load(cls, book: str, root: Path | str | None = None) -> Ledger:
        p = ledger_path(book, root)
        lines = []
        if p.exists():
            for i, raw in enumerate(p.read_text(encoding="utf-8").splitlines()):
                if raw.strip():
                    try:
                        d = json.loads(raw)
                    except ValueError as e:
                        raise ValueError(f"{p}:{i + 1}: 不是 JSON：{e}") from None
                    if d.get("kind") == KIND:
                        lines.append(d)
        return cls(book, p, lines)

    @property
    def exists(self) -> bool:
        return bool(self.lines)

    def latest(self) -> dict[int, dict]:
        """页 → 该页最后一行。"""
        out: dict[int, dict] = {}
        for d in self.lines:
            out[int(d["page"])] = d
        return out

    def page(self, page: int) -> dict | None:
        return self.latest().get(int(page))

    def by_sha(self, page: int, cells_sha: str) -> dict | None:
        hit = None
        for d in self.lines:
            if int(d["page"]) == int(page) and cells_sha and d.get("cells_sha") == cells_sha:
                hit = d
        return hit

    def u_max(self) -> int:
        m = 0
        for d in self.lines:
            m = max(m, int(d.get("u_max") or 0))      # 册级记录（page=0）可显式记 u_max
            for u in d.get("map", {}).values():
                m = max(m, int(u))
            for x in d.get("lineage") or []:
                m = max(m, int(x["u"]))
        return m

    def retired(self) -> dict[int, dict]:
        """作废号：u → {u, into}／{u, gone: true}（取最后一次记的）。后来又在某页现行 map 里的不算（不该有，verify 报）。"""
        out: dict[int, dict] = {}
        for d in self.lines:
            for x in d.get("lineage") or []:
                if "into" in x:
                    out[int(x["u"])] = {"u": int(x["u"]), "into": int(x["into"])}
                elif x.get("gone"):
                    out[int(x["u"])] = {"u": int(x["u"]), "gone": True}
        return out

    def current(self) -> dict[str, int]:
        """全册现行 格号 → u（各页最后一行合起来）。"""
        out: dict[str, int] = {}
        for _, d in sorted(self.latest().items()):
            out.update({k: int(v) for k, v in d["map"].items()})
        return out

    def u_map(self, page: int | None = None, *, full: bool = False) -> dict[str, int]:
        """现行 格号 → u；``page`` 给了只取那一页。格号缺省是 book-text 的 ``a``（``页:列:格[ab]``，不带册前缀），
        ``full=True`` 带册前缀。"""
        cur = self.current() if page is None else {k: int(v) for k, v in (self.page(page) or {"map": {}})["map"].items()}
        if full:
            return cur
        n = len(self.book) + 1
        return {k[n:]: v for k, v in cur.items()}

    def page_pair(self, page: int) -> tuple[dict | None, dict | None]:
        """这一页的（上一份, 当前一份）账行；只入过一次账 → (None, 当前)；没账 → (None, None)。
        换图源／swap 出「旧切分→新切分」对照：两份的 map 按 u 对上即可（拆并见当前行的 lineage）。"""
        ds = [d for d in self.lines if int(d["page"]) == int(page)]
        if not ds:
            return None, None
        return (ds[-2] if len(ds) > 1 else None), ds[-1]

    def cell_of(self, u: int) -> str | None:
        for k, v in self.current().items():
            if v == int(u):
                return k
        return None

    def history(self, u: int) -> list[dict]:
        """u 的来历：在哪些行出现过、谱系里的事。"""
        u = int(u)
        out = []
        for d in self.lines:
            cells = [k for k, v in d["map"].items() if int(v) == u]
            ev = [x for x in d.get("lineage") or [] if int(x["u"]) == u or x.get("into") == u or x.get("split_from") == u]
            if cells or ev:
                out.append({"id": d["id"], "ts": d.get("ts"), "page": d["page"], "cells_sha": d.get("cells_sha"),
                            "cell": cells[0] if cells else None, "lineage": ev})
        return out

    # ── 写 ──
    def append(self, lines: Iterable[dict]) -> int:
        new = [d for d in lines]
        if not new:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            for d in new:
                f.write(json.dumps(d, ensure_ascii=False, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self.lines.extend(new)
        return len(new)


def verify(led: Ledger) -> list[str]:
    """账自洽：每行 map 的 u 不重；全册现行 u 不重、都 ≤ u_max、不在作废号里；每页旧行里的 u 要么还在该页现行 map、
    要么进了作废号、要么拆并谱系里有去处（不静默丢）；into 指向的 u 现行存在。返回问题清单（空＝过）。"""
    errs: list[str] = []
    umax = led.u_max()
    ret = led.retired()
    for d in led.lines:
        vals = [int(v) for v in d["map"].values()]
        if len(vals) != len(set(vals)):
            dup = sorted(v for v in set(vals) if vals.count(v) > 1)
            errs.append(f"{d['id']}：同一行里 u 重复 {dup[:5]}")
        if any(v < 1 for v in vals):
            errs.append(f"{d['id']}：有 u < 1")
        if d.get("book") != led.book:
            errs.append(f"{d['id']}：book={d.get('book')} 与账名 {led.book} 不符")
    cur = led.current()
    seen: dict[int, str] = {}
    for k, u in cur.items():
        if u in seen:
            errs.append(f"u={u} 现行同时在 {seen[u]} 与 {k}")
        seen[u] = k
        if u > umax:
            errs.append(f"u={u}（{k}）超过 u_max={umax}")
        if u in ret:
            errs.append(f"u={u}（{k}）在作废号里又出现")
    live = set(seen)
    for u, r in ret.items():
        if "into" in r and r["into"] not in live and r["into"] not in ret:
            errs.append(f"u={u} 并进的 u={r['into']} 现行不存在")
    by_page: dict[int, list[dict]] = {}
    for d in led.lines:
        by_page.setdefault(int(d["page"]), []).append(d)
    for pg, ds in by_page.items():
        for a, b in zip(ds, ds[1:]):
            keep = {int(v) for v in b["map"].values()}
            gone = {int(x["u"]) for x in b.get("lineage") or [] if "into" in x or x.get("gone")}
            lost = sorted({int(v) for v in a["map"].values()} - keep - gone)
            if lost:
                errs.append(f"第 {pg} 页 {a['id']} → {b['id']}：{len(lost)} 个 u 没有去处 {lost[:5]}")
    return errs
