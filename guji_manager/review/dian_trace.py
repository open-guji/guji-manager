"""点校阶段各级查证备注（trace）→ 待审单 `dian={char, why, refs}`（A31，2026-11-08）。

trace 存放：`feedback/notes/<册>.jsonl`，每行 `{group, prompt_ver, ctx:{left,right,hash}, cell, cands?, trace:[…]}`
（管线不读，见 ai-team domain/文本/点校先于精校/方案-2026-11-08.md §5.3）。`trace` 按级排列，每项
`{level: L1|L2|L3, model, char, conf, why, status, evidence:[{url, quote, source_kind}], ...}`；L1 项可带
`routes:{A:[字,conf], B:[字,conf]}`。

本模块只做两件事，纯函数、不读网络：
- `summarize_trace(trace, cands)` → `dian` dict（给 `proof_fields.pending_fields` 用的 `card["dian"]`）；
- `load_notes(path)` / `find_note(index, ...)`：读旁路文件、按键找一条。

口径：
- 倾向字 `char`：取最高一级里给出**候选内**字且 conf 为 high／mid、status 不是 not_found 的那一项；
  所有级都没有（弃权、low、字在候选外）则不给 `char`，网页只显示 `dnote`（`proof_fields` 已处理）。
  不预选：网页只提示。
- `why`≤200 字：`L1 日/曰分歧；L2 mid：…；L3 已：…`，每级一句，超长从后截断；候选外真字（如「白」）写进 why。
- `refs`：各级 evidence 的 url（仅 http/https，去重，高级别在前，最多 5 条），标题 `t`＝来源类型＋原句前 30 字，≤60 字。
"""
from __future__ import annotations

import json
from pathlib import Path

WHY_MAX = 200
REFS_MAX = 5
_KIND = {"wikipedia": "维基百科", "other_book": "他书", "db": "数据库"}
_LEVEL_ORDER = {"L1": 1, "L2": 2, "L3": 3}


def _lvl(t: dict) -> int:
    return _LEVEL_ORDER.get(str(t.get("level") or ""), 0)


def _l1_text(t: dict) -> str:
    r = t.get("routes") or {}
    a, b = (r.get("A") or [None])[0], (r.get("B") or [None])[0]
    if a and b:
        return f"L1 两路{'同为' + a if a == b else '分歧(' + a + '/' + b + ')'}"
    return "L1 未定"


def _level_text(t: dict) -> str:
    lv = str(t.get("level") or "")
    if lv == "L1":
        return _l1_text(t)
    ch = t.get("char") or "—"
    conf = t.get("conf") or ""
    head = f"{lv} {ch}" + (f"({conf})" if conf else "")
    if t.get("status") == "not_found":
        head += " 未查到"
    body = str(t.get("why") or t.get("note") or "").strip()
    return head + (f"：{body}" if body else "")


def _pick_char(trace: list[dict], cands: list[str]) -> str:
    for t in sorted(trace, key=_lvl, reverse=True):
        if t.get("level") == "L1":
            continue
        ch = t.get("char") or ""
        if ch in cands and t.get("conf") in ("high", "mid") and t.get("status") not in ("not_found", "contradicts_L2"):
            return ch
    return ""


def _refs(trace: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for t in sorted(trace, key=_lvl, reverse=True):
        for e in t.get("evidence") or []:
            u = str((e or {}).get("url") or "").strip()
            if not u.startswith(("http://", "https://")) or u in seen:
                continue
            seen.add(u)
            kind = _KIND.get(str(e.get("source_kind") or ""), "")
            q = str(e.get("quote") or "").strip().replace("\n", " ")[:30]
            title = (f"{kind}：" if kind else "") + q
            out.append({"u": u, "t": (title or u)[:60]})
            if len(out) >= REFS_MAX:
                return out
    return out


def summarize_trace(trace: list[dict], cands: list[str] | None = None) -> dict | None:
    """trace → `{char?, why, refs?}`；trace 为空返回 None。"""
    if not trace:
        return None
    cands = list(cands or [])
    ordered = sorted(trace, key=_lvl)
    why = "；".join(_level_text(t) for t in ordered)
    # 候选外的真字（L3 contradicts 等）：不当倾向字，写进 why 供人审参考
    out: dict = {"why": why[:WHY_MAX]}
    ch = _pick_char(trace, cands)
    if ch:
        out["char"] = ch
    refs = _refs(trace)
    if refs:
        out["refs"] = refs
    return out


def load_notes(path: str | Path) -> dict:
    """读 `feedback/notes/<册>.jsonl`，返回索引：`{("hash", group, hash): row, ("cell", cell): row}`；后写的覆盖先写的。"""
    idx: dict = {}
    p = Path(path)
    if not p.exists():
        return idx
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        h = (row.get("ctx") or {}).get("hash")
        if h:
            idx[("hash", row.get("group"), h)] = row
        if row.get("cell"):
            idx[("cell", row["cell"])] = row
    return idx


def find_note(idx: dict, *, cell: str | None = None, group: str | None = None, ctx_hash: str | None = None) -> dict | None:
    """先按（组，ctx 哈希）找（重切后仍命中），找不到再按格号。"""
    if group and ctx_hash and ("hash", group, ctx_hash) in idx:
        return idx[("hash", group, ctx_hash)]
    if cell:
        return idx.get(("cell", cell))
    return None


def dian_for(idx: dict, *, cell: str | None = None, group: str | None = None, ctx_hash: str | None = None,
             cands: list[str] | None = None) -> dict | None:
    """出单脚本入口：找到该格的 trace 并摘要，供 `card["dian"] = dian_for(...)`。"""
    row = find_note(idx, cell=cell, group=group, ctx_hash=ctx_hash)
    if not row:
        return None
    return summarize_trace(row.get("trace") or [], cands or row.get("cands"))
