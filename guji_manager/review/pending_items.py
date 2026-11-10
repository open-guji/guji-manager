"""待审条目：待审单从「一册一张、整张换 rev」拆成「一格一条」（设计 doc/00-总览/设计-待审条目化.md，sheldon 11-10 定）。

## 存放

数据目录 `feedback/lists/pending/<书 id>/<章>.items.jsonl`，随 `guji db sync` 进中心库。文件**只追加**：每改一次条目
追加一行这条的完整新版本（`ver` +1，带 `op`／`by`／`at`／`why`），当前状态＝每个 `id` 的最后一行。两台机器同时改，
sync 按追加合并（`datastore.workcopy`），不会冲突。

## 条目

| 键 | 含义 |
|---|---|
| `id` | 条目 id（`pi_` + 12 位十六进制），开条目时定，之后不变 |
| `cell` | 当前格号 `页:列:格[a|b]`（重切后可变） |
| `fp` | 图块指纹：字块图（Step4 `char_patch`）的 sha1，同人裁锚的 `content_sha`；没有产物时为空 |
| `state` | `open` 待审、`withdrawn` 人工撤下、`resolved` 已有人裁（留着显示结果）、`closed` 机器不再判待审 |
| `doc` | 网站卡片要的全部字段（与 `pending.json` 的一格相同：`why`、候选、`img`、`note`、`prior`、`recheck`…） |
| `src` | 谁开的：`pack:<产物包>`／`import:<rev>`／`human:<谁>`／`script:<名>` |
| `ver`／`op`／`by`／`at`／`why` | 版本号与这次改动 |

格号与指纹**两个都记**（sheldon 11-10）：reconcile 先按指纹认，认不出再按格号认；按格号认上但指纹变了的，条目照旧、
记 `fp_prev` 并标 `fp_changed`，以后怎么处理再定。人工撤下的条目，机器下一轮仍判待审也**不放回**（只更新字段）。

整张 `pending.json` 仍照旧导出（`export_sheet`），网站与统计不用改就能读；每格多带 `id`、`ver`。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

STATES = ("open", "withdrawn", "resolved", "closed")
#: 导出时进 `cells[]` 的状态（resolved＝已人审、留在单上显示结果，`review: human`）
SHOWN = ("open", "resolved")
_CELL = re.compile(r"^-?\d+:-?\d+:-?\d+[ab]?$")
#: 单头里不归条目管的键（导出时由条目重算）
_ITEM_KEYS = ("cells", "withdrawn", "edits")


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def items_path(data: Path, text_id: str, chapter: str) -> Path:
    return Path(data) / "feedback" / "lists" / "pending" / text_id / f"{chapter}.items.jsonl"


def sheet_path(data: Path, text_id: str, chapter: str) -> Path:
    return Path(data) / "feedback" / "lists" / "proofing" / text_id / f"{chapter}.pending.json"


def norm_cell(x: str) -> str:
    """`vol02:100:4:17b` → `100:4:17b`（带册号前缀的去掉）。"""
    x = str(x).strip()
    return x.split(":", 1)[1] if x.count(":") == 3 else x


def cell_sort_key(cell: str):
    out = []
    for p in str(cell).split(":"):
        m = re.fullmatch(r"(-?\d+)([ab]?)", p)
        out.append((int(m[1]), m[2]) if m else (0, p))
    return out


def new_id(text_id: str, chapter: str, cell: str, at: str, salt: str = "") -> str:
    return "pi_" + hashlib.sha1(f"{text_id}|{chapter}|{cell}|{at}|{salt}".encode()).hexdigest()[:12]


def _canon(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False, sort_keys=True)


def _cell_doc(c: dict) -> dict:
    """单上一格 → 条目 doc：去掉条目自己的键（id、ver、撤下记录），格号另存。"""
    return {k: v for k, v in c.items() if k not in ("id", "ver", "withdrawn", "cell", "a")}


class ItemStore:
    """一章的条目：读日志、追加新版本。"""

    def __init__(self, path: Path, text_id: str = "", chapter: str = ""):
        self.path = Path(path)
        self.text_id = text_id or self.path.parent.name
        self.chapter = chapter or self.path.name.split(".", 1)[0]
        self.items: dict[str, dict] = {}
        self.pending: list[dict] = []          # 本次要追加的行
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    self.items[r["id"]] = r

    @classmethod
    def open(cls, data: Path, text_id: str, chapter: str) -> "ItemStore":
        return cls(items_path(data, text_id, chapter), text_id, chapter)

    # ---- 查 ----
    def by_state(self, *states: str) -> list[dict]:
        return sorted((r for r in self.items.values() if r["state"] in states), key=lambda r: cell_sort_key(r["cell"]))

    def find(self, ref: str) -> list[dict]:
        """条目 id 或格号 → 条目（格号可能对应已关的旧条目，先给活的）。"""
        ref = ref.strip()
        if ref in self.items:
            return [self.items[ref]]
        cell = norm_cell(ref)
        hit = [r for r in self.items.values() if r["cell"] == cell]
        live = [r for r in hit if r["state"] in ("open", "withdrawn", "resolved")]
        return live or hit

    def counts(self) -> dict[str, int]:
        out = {s: 0 for s in STATES}
        for r in self.items.values():
            out[r["state"]] = out.get(r["state"], 0) + 1
        return out

    # ---- 写 ----
    def put(self, prev: dict | None, *, op: str, by: str = "", why: str = "", at: str | None = None, **fields) -> dict:
        """追加一版：prev 的字段＋改动；prev 为 None 是开新条目（fields 要有 id、cell、state、doc）。"""
        at = at or now()
        base = dict(prev) if prev else {"ver": 0}
        for k in ("op", "by", "why", "at", "fp_changed", "fp_prev"):
            base.pop(k, None)
        rec = {**base, **fields, "ver": int(base.get("ver") or 0) + 1, "op": op, "by": by, "at": at}
        if why:
            rec["why"] = why
        assert rec.get("state") in STATES, rec.get("state")
        self.items[rec["id"]] = rec
        self.pending.append(rec)
        return rec

    def save(self) -> int:
        """把本次的新版本追加进文件。返回追加了几行。"""
        if not self.pending:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            for r in self.pending:
                f.write(_canon(r) + "\n")
        n = len(self.pending)
        self.pending = []
        return n

    # ---- 人工操作 ----
    def _one(self, ref: str) -> dict:
        hit = self.find(ref)
        if not hit:
            raise KeyError(f"找不到条目：{ref}")
        if len(hit) > 1:
            raise KeyError(f"{ref} 对应 {len(hit)} 条条目（{' '.join(r['id'] for r in hit)}），请给条目 id")
        return hit[0]

    def withdraw(self, ref: str, *, by: str, why: str = "") -> dict:
        r = self._one(ref)
        if r["state"] == "withdrawn":
            return r
        return self.put(r, op="withdraw", by=by, why=why, state="withdrawn")

    def restore(self, ref: str, *, by: str, why: str = "") -> dict:
        r = self._one(ref)
        if r["state"] != "withdrawn":
            raise ValueError(f"{r['id']}（{r['cell']}）不是撤下状态（{r['state']}）")
        return self.put(r, op="restore", by=by, why=why, state="open")

    def note(self, ref: str, text: str, *, by: str, why: str = "") -> dict:
        r = self._one(ref)
        doc = dict(r.get("doc") or {})
        if text:
            doc["note"] = text
        else:
            doc.pop("note", None)
        return self.put(r, op="note", by=by, why=why, doc=doc)

    def set_fields(self, ref: str, fields: dict, *, by: str, why: str = "", op: str = "edit") -> dict:
        """改卡片字段（候选、首选字提示等）；值为 None 的键删掉。"""
        r = self._one(ref)
        doc = dict(r.get("doc") or {})
        for k, v in fields.items():
            if v is None:
                doc.pop(k, None)
            else:
                doc[k] = v
        return self.put(r, op=op, by=by, why=why, doc=doc)

    def add(self, cell: str, doc: dict, *, by: str, src: str, why: str = "", fp: str = "", state: str = "open",
            sprites: list[dict] | None = None) -> dict:
        """加一条（人工复审格、撤库重审、点校等）。这格已有活条目就并进去（改字段、重新打开），不重复开。
        `sprites`：这条自带的字块图（按内容寻址的单图，`[{name, sha256, md5, bytes}]`，第 2 步），导出时并进单头 `sprites[]`。"""
        extra = {"sprites": sprites} if sprites else {}
        cell = norm_cell(cell)
        if not _CELL.match(cell):
            raise ValueError(f"格号不对：{cell}")
        live = [r for r in self.find(cell) if r["state"] in ("open", "withdrawn", "resolved") and r["cell"] == cell]
        doc = {"review": "pending", **_cell_doc(doc)}
        if live:
            r = live[0]
            merged = {**(r.get("doc") or {}), **doc}
            st = r["state"] if r["state"] == "withdrawn" else state
            return self.put(r, op="add", by=by, why=why, doc=merged, state=st, **({"fp": fp} if fp else {}), **extra)
        at = now()
        return self.put(None, op="open", by=by, why=why, at=at, id=new_id(self.text_id, self.chapter, cell, at, src),
                        cell=cell, fp=fp, state=state, doc=doc, src=src, **extra)

    def resolve(self, ref: str, *, by: str, event: str = "", why: str = "") -> dict:
        r = self._one(ref)
        doc = {**(r.get("doc") or {}), "review": "human"}
        return self.put(r, op="resolve", by=by, why=why, state="resolved", doc=doc, **({"event": event} if event else {}))


# ---- 机器一轮：按新单逐格比 ----

def reconcile(store: ItemStore, cells: Iterable[dict], *, src: str, fps: dict[str, str] | None = None,
              by: str = "", at: str | None = None, close_missing: bool = True) -> dict:
    """机器跑完一轮（或导入旧单）：新单上的每一格对到条目，只动有变化的。

    - 先按图块指纹认（同一块图＝同一条目，格号挪了就改 `cell`），认不出再按格号认（指纹变了记 `fp_prev`、标 `fp_changed`）；
    - 都认不出的开新条目（`src`）；
    - 字段（`doc`）、状态没变的不动，变了的 ver+1；
    - 人工撤下的保持撤下（只更新字段）；已关、已裁的条目机器又判待审就重新打开（`reopen`）；
    - `close_missing`：开着的条目在新单上没有了 → `closed`（机器放行或不再要人看）。撤下、已裁的不动。
    返回各项计数与明细。"""
    at = at or now()
    fps = fps or {}
    by_fp: dict[str, dict] = {}
    by_cell: dict[str, list[dict]] = {}
    for r in store.items.values():
        if r.get("fp"):
            by_fp.setdefault(r["fp"], r)
        by_cell.setdefault(r["cell"], []).append(r)
    rank = {"open": 0, "withdrawn": 1, "resolved": 2, "closed": 3}
    out = {"开": [], "改": [], "挪格": [], "图变": [], "重开": [], "关": [], "不变": 0, "撤下仍判待审": []}
    seen: set[str] = set()
    for c in cells:
        cell = norm_cell(c.get("cell") or c.get("a") or "")
        if not cell:
            continue
        fp = fps.get(cell) or ""
        doc = _cell_doc(c)
        want = "resolved" if doc.get("review") == "human" else "open"
        r = by_fp.get(fp) if fp else None
        if r is not None and r["id"] in seen:
            r = None
        if r is None:
            cands = [x for x in by_cell.get(cell, []) if x["id"] not in seen]
            cands.sort(key=lambda x: (rank.get(x["state"], 9), -int(x.get("ver") or 0)))
            # 按格号认：指纹都有且不同 → 还是认（两个都记，sheldon 11-10），只标图变
            r = cands[0] if cands else None
        if r is None:
            new = store.put(None, op="open", by=by, at=at, id=new_id(store.text_id, store.chapter, cell, at, src),
                            cell=cell, fp=fp, state=want, doc=doc, src=src)
            seen.add(new["id"])
            out["开"].append(cell)
            continue
        seen.add(r["id"])
        upd: dict = {}
        ops = []
        if r["cell"] != cell:
            upd["cell"] = cell
            ops.append("move")
            out["挪格"].append(f"{r['cell']}→{cell}")
        if fp and r.get("fp") and r["fp"] != fp:
            upd.update(fp=fp, fp_prev=r["fp"], fp_changed=True)
            ops.append("fp")
            out["图变"].append(cell)
        elif fp and not r.get("fp"):
            upd["fp"] = fp
        if _canon(r.get("doc") or {}) != _canon(doc):
            upd["doc"] = doc
            ops.append("doc")
        st = r["state"]
        if st == "withdrawn":
            if want == "open":
                out["撤下仍判待审"].append(cell)
            else:
                upd["state"] = want
                ops.append("state")
        elif st != want:
            upd["state"] = want
            ops.append("reopen" if want == "open" else "state")
            if want == "open":
                out["重开"].append(cell)
        if not upd:
            out["不变"] += 1
            continue
        store.put(r, op="machine:" + "+".join(ops or ["fp"]), by=by, at=at, src=r.get("src") or src,
                  why=src, **upd)
        if "doc" in upd:
            out["改"].append(cell)
    if close_missing:
        for r in list(store.items.values()):
            if r["id"] not in seen and r["state"] == "open":
                store.put(r, op="close", by=by, at=at, why=src, state="closed")
                out["关"].append(r["cell"])
    return out


def import_sheet(store: ItemStore, doc: dict, *, by: str = "", fps: dict[str, str] | None = None) -> dict:
    """从现行整张单导入（迁移第 1 步）：`cells[]` 逐格对条目，`withdrawn[]` 记成撤下。`src=import:<rev>`。
    已经导入过的再导一遍只动有变化的（可重复执行）。"""
    rev = doc.get("rev") or "?"
    src = f"import:{rev}"
    res = reconcile(store, doc.get("cells") or [], src=src, fps=fps, by=by, close_missing=False)
    for c in doc.get("withdrawn") or []:
        cell = norm_cell(c.get("cell") or "")
        live = [r for r in store.find(cell) if r["cell"] == cell and r["state"] != "closed"]
        w = c.get("withdrawn") or {}
        if live:
            if live[0]["state"] != "withdrawn":
                store.put(live[0], op="withdraw", by=w.get("by") or by, why=w.get("why") or "", state="withdrawn")
            continue
        at = w.get("at") or now()
        store.put(None, op="open", by=w.get("by") or by, at=at, id=new_id(store.text_id, store.chapter, cell, at, src),
                  cell=cell, fp=(fps or {}).get(cell, ""), state="withdrawn", doc=_cell_doc(c), src=src,
                  why=w.get("why") or "")
        res.setdefault("撤下", []).append(cell)
    return res


def rev_cell_map(store: ItemStore, rev: str) -> dict[str, str]:
    """某个旧 rev 上的格号 → 条目 id（条目化之前投在整张单上的旧票迁移用）：导入那一版（`import:<rev>`）时的格号；
    认不出的按现行格号兜底。条目化之后出的单每格都带 `id`，网站按条目投票，不用这张表。"""
    out: dict[str, str] = {}
    if not store.path.exists():
        return out
    tag = f"import:{rev}"
    for line in store.path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("src") == tag or r.get("why") == tag:
            out.setdefault(r["cell"], r["id"])
    for r in store.items.values():
        out.setdefault(r["cell"], r["id"])
    return out


def export_sheet(store: ItemStore, head: dict | None = None) -> dict:
    """条目 → 整张 `pending.json`（网站、统计照旧读）。单头（rev、cv_version、sprites、sent…）取 `head`，
    `cells[]` 由条目现算（open 与 resolved），撤下的进 `withdrawn[]`。每格带 `id`、`ver`。"""
    doc = {k: v for k, v in (head or {}).items() if k not in _ITEM_KEYS}
    cells = []
    for r in store.by_state(*SHOWN):
        c = {"cell": r["cell"], **(r.get("doc") or {}), "id": r["id"], "ver": r["ver"]}
        c.setdefault("review", "human" if r["state"] == "resolved" else "pending")
        cells.append(c)
    doc["cells"] = cells
    # 条目自带的按内容寻址字块图（第 2 步）并进单头 sprites[]，网站发布时一并传
    sp = {e["name"]: e for e in doc.get("sprites") or [] if isinstance(e, dict) and e.get("name")}
    for r in store.by_state(*SHOWN, "withdrawn"):
        for e in r.get("sprites") or []:
            sp.setdefault(e["name"], e)
    if sp:
        doc["sprites"] = sorted(sp.values(), key=lambda e: e["name"])
    gone = [{"cell": r["cell"], **(r.get("doc") or {}), "id": r["id"], "ver": r["ver"],
             "withdrawn": {"by": r.get("by", ""), "at": r.get("at", ""), "why": r.get("why", "")}}
            for r in store.by_state("withdrawn")]
    if gone:
        doc["withdrawn"] = gone
    doc["items"] = {"file": f"feedback/lists/pending/{store.text_id}/{store.chapter}.items.jsonl",
                    "n": store.counts()}
    return doc
