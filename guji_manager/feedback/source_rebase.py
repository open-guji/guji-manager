"""换图源（页号格号都不变）后的人裁事件换算：锚里的框按页表 `from_rev.H` 换到新页，`source_rev` 改成新页表 rev。

场景：殿本四庫總目 2026-11-04 图源再换一次（Commons 景印文淵閣本，按版框重切摆正，设计稿 Claude Doc「四庫總目图源切到
Commons 文淵閣本与国内外分线计划」）。和 10 月 siku-qiefen-v2 那次不同，这次**页序、页号、列、格号全不变**，
只有像素变——所以不用格级对照表（`cell_migrate`），按页乘一个 3×3 矩阵就行。

为什么要迁：事件读口有页表 rev 闸（cv `core/event_files.RevGate`）：册 yaml 的 `source_rev` 改成新 rev 以后，
锚里 `source_rev` 还是旧 rev 的事件一律不采信。所以册 yaml 一改钉，旧人裁就全部「消失」。迁移就是给每条原本被采信的
事件写一份锚换算过的新事件。

做什么（**只出提案，不写库**，同 `cell_migrate`）：对每条事件
- 锚里没有 `source_rev`：旧闸本来就不采信，不迁（报告里数）；
- 种类在 `GATE_EXEMPT_KINDS`（glyph_audit、ctx_ruling，不按页锚）：闸不管它，不迁；
- `source_rev` 已是新 rev：不迁；
- 否则要求旧 rev 那版页表这一页的图 sha ＝ 新页表这一页 `from_rev.sha256`（证明矩阵就是从这版图换算来的；
  殿本 vol51 等 13 册钉 rev 2、新页表 from_rev 是 3，两版页图 sha 逐页相同，所以也过），对不上不迁、进待办；
- 锚的 `bbox`（`[x0,y0,x1,y1]`）、`quad`（四个点）按该页矩阵换算。坐标系是 `raw_page_px@top-right`（右上原点），
  换算时按 `origin="top-right"` 处理；别的坐标系不迁、进待办；
- 其余锚键（`content_sha`、`evidence`、`ctx`、`cells_sha`、`product_key`…）原样带，**不替人改账**。注意 `content_sha`、
  `evidence.fp` 是旧图字块的凭证，换图后重跑的字块与它们的相似度会变，绑定（`bindings.py`）按位置、再按图像判「还挂得上吗」，
  量大时要在新 main 出来后抽看一遍，所以报告里单数一行有这类凭证的条数。

新事件：`id`、`batch` 各加 `~r`（`ts`、`seq` 不变，「后到覆盖」的次序保持），`target` 的键、页、列、格不变，
`target.anchor` 换算过并加 `migrated_from: {id, source_rev}`；`payload` 原样，只有 `payload.overrides` 指向的旧事件 id 换成新 id
（那条旧事件没迁就去掉）。旧事件不删，写入时按册 yaml 的新 `source_rev` 过闸，旧的自然被挡。

核对：`输入 = 迁出 + 没迁` 每份报告都算一遍，对不上就是工具的 bug，直接抛错。
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

SUFFIX = "~r"
SPACE = "raw_page_px@top-right"
#: 不按页号锚、不受页表 rev 闸管的事件种类；与 cv `core/event_files.GATE_EXEMPT_KINDS` 保持一致。
GATE_EXEMPT_KINDS = frozenset({"glyph_audit", "ctx_ruling"})

_KEY = re.compile(r"^(?:v2:)?(?P<book>[^:]+):(?P<page>\d+)")


def book_page(target: dict) -> tuple[str | None, int | None]:
    """事件目标所在的册与页（同 cv `RevGate` 的取法：先看字段，再从 key 里拆）。"""
    book, page = target.get("book"), target.get("page")
    if book and page is not None:
        return book, int(page)
    m = _KEY.match(str(target.get("key") or ""))
    if m:
        return book or m["book"], int(m["page"])
    return book, page


@dataclass
class Pending:
    reason: str
    key: str
    detail: str = ""


@dataclass
class Result:
    book: str
    new_rev: int
    events: list[dict] = field(default_factory=list)          # 新事件（事件 dict）
    id_map: dict[str, str] = field(default_factory=dict)      # 旧事件 id → 新事件 id
    skipped: Counter = field(default_factory=Counter)         # 本来就不迁的：理由 → 条数
    pending: list[Pending] = field(default_factory=list)      # 该迁而没迁成的，要人看
    n_in: int = 0
    n_with_evidence: int = 0                                  # 迁出的里带 content_sha／evidence 凭证的条数
    n_no_box: int = 0                                         # 迁出的里锚没有框、只改了 source_rev 的条数
    by_kind: Counter = field(default_factory=Counter)

    def check(self) -> None:
        out = len(self.events) + sum(self.skipped.values()) + len(self.pending)
        if self.n_in != out:
            raise AssertionError(f"事件数对不上：输入 {self.n_in} ≠ 迁出 {len(self.events)} + 不迁 "
                                 f"{sum(self.skipped.values())} + 待办 {len(self.pending)}")


def _round(v: float) -> float:
    return round(float(v), 1)


def _rebase_anchor(anchor: dict, xf) -> dict:
    """锚里的框和四角换到新页；其余键原样。`xf`：这一页的 `PageXform`。"""
    from ..datastore.source_xform import TR
    a = dict(anchor)
    bb = a.get("bbox")
    if bb:
        x0, y0, x1, y1 = xf.box(*[float(v) for v in bb], origin=TR)
        a["bbox"] = [_round(x0), _round(y0), _round(x1), _round(y1)]
    q = a.get("quad")
    if q:
        a["quad"] = [[_round(x), _round(y)] for x, y in xf.points(q, TR).tolist()]
    return a


def rebase_events(events: Iterable[dict], book: str, new_rev: int,
                  get_table: Callable[[int], dict | None]) -> Result:
    """`events`：这一册的事件 dict（要**没过页表 rev 闸**的，即读旧页号时用的 raw 读法）；
    `get_table(rev)`：取这一册某一版页表（dict），没有这一版返回 None。"""
    from ..datastore import source_xform as X
    res = Result(book, int(new_rev))
    new_table = get_table(int(new_rev))
    if not new_table:
        raise ValueError(f"取不到 {book} 的新页表 r{int(new_rev):03d}")
    xf_by_page = X.by_page(new_table)
    new_rows = {int(p["page"]): p for p in new_table.get("pages", [])}
    old_tables: dict[int, dict | None] = {}

    def old_sha(rev: int, page: int) -> str | None:
        if rev not in old_tables:
            old_tables[rev] = get_table(rev)
        t = old_tables[rev]
        if not t:
            return None
        for p in t.get("pages", []):
            if int(p["page"]) == page:
                return p.get("sha256")
        return None

    evs = [e for e in events if (book_page(e.get("target") or {})[0] == book)]
    res.n_in = len(evs)
    for e in sorted(evs, key=lambda e: (e.get("ts", ""), e.get("batch", ""), e.get("seq", 0))):
        t = e.get("target") or {}
        key = str(t.get("key") or "")
        if e.get("kind") in GATE_EXEMPT_KINDS:
            res.skipped["不按页锚的种类（闸不管）"] += 1
            continue
        _, page = book_page(t)
        anchor = t.get("anchor") or {}
        sr = anchor.get("source_rev")
        if sr is None:
            res.skipped["没有锚或锚里没有 source_rev（旧闸本来就不采信）"] += 1
            continue
        try:
            sr = int(sr)
        except (TypeError, ValueError):
            res.pending.append(Pending("source_rev 不是整数", key, f"{e.get('id')}：{anchor.get('source_rev')!r}"))
            continue
        if sr == int(new_rev):
            res.skipped["source_rev 已是新页表 rev"] += 1
            continue
        xf, row = xf_by_page.get(page), new_rows.get(page)
        if xf is None or row is None or not row.get("from_rev"):
            res.pending.append(Pending("新页表没有这一页的换算", key, f"{e.get('id')}（第 {page} 页）"))
            continue
        want = row["from_rev"].get("sha256")
        got = old_sha(sr, page)
        if got is None:
            res.pending.append(Pending("取不到旧页表这一页", key, f"{e.get('id')}（r{sr:03d} 第 {page} 页）"))
            continue
        if got != want:
            res.pending.append(Pending("旧页图和新页表 from_rev 对不上", key,
                                       f"{e.get('id')}（r{sr:03d} 第 {page} 页 {got[:8]} ≠ {str(want)[:8]}）"))
            continue
        if anchor.get("space") not in (None, SPACE):
            res.pending.append(Pending("锚的坐标系不是右上原点", key, f"{e.get('id')}：{anchor.get('space')}"))
            continue
        d = json.loads(json.dumps(e))
        na = _rebase_anchor(anchor, xf)
        na["source_rev"] = str(new_rev) if isinstance(anchor.get("source_rev"), str) else int(new_rev)
        na["migrated_from"] = {"id": e["id"], "source_rev": anchor.get("source_rev")}
        d["target"]["anchor"] = na
        d["id"] = e["id"] + SUFFIX
        d["batch"] = e["batch"] + SUFFIX
        res.id_map[e["id"]] = d["id"]
        res.events.append(d)
        res.by_kind[e.get("kind")] += 1
        if not (anchor.get("bbox") or anchor.get("quad")):
            res.n_no_box += 1
        if anchor.get("content_sha") or anchor.get("evidence"):
            res.n_with_evidence += 1
    for d in res.events:                  # overrides 指向的旧事件迁了就换新 id，没迁就去掉
        o = (d.get("payload") or {}).get("overrides")
        if o:
            if o in res.id_map:
                d["payload"]["overrides"] = res.id_map[o]
            else:
                del d["payload"]["overrides"]
    res.check()
    return res


def write_report(res: Result, out: Path, *, extra: dict | None = None) -> None:
    res.check()
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "events.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for d in res.events:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    with open(out / "id_map.tsv", "w", encoding="utf-8", newline="\n") as f:
        f.write("旧事件id\t新事件id\n")
        for a, b in sorted(res.id_map.items()):
            f.write(f"{a}\t{b}\n")
    with open(out / "pending.tsv", "w", encoding="utf-8", newline="\n") as f:
        f.write("理由\t格键\t说明\n")
        for p in res.pending:
            f.write(f"{p.reason}\t{p.key}\t{p.detail}\n")
    L = [f"# {res.book} 换图源人裁事件换算提案（只读，没有写库）", "",
         f"- 新页表 rev：{res.new_rev}", "",
         f"- 输入 {res.n_in} = 迁出 {len(res.events)} + 不迁 {sum(res.skipped.values())} + 待办 {len(res.pending)}（核对通过）"]
    L += [f"- 不迁：{k} {n}" for k, n in sorted(res.skipped.items())]
    L += [f"- 待办：{k} {n}" for k, n in sorted(Counter(p.reason for p in res.pending).items())]
    L += ["", "## 迁出的", ""]
    L += [f"- {k} {n}" for k, n in sorted(res.by_kind.items(), key=lambda kv: -kv[1])]
    L += ["", f"- 锚里没有框、只改了 source_rev：{res.n_no_box} 条",
          f"- 带旧图凭证（content_sha／evidence）的：{res.n_with_evidence} 条——换图后字块变了，新 main 出来后抽看绑定状态"]
    for k, v in (extra or {}).items():
        L += ["", f"{k}：{v}"]
    (out / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
