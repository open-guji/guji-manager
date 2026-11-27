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
  不预选：网页只提示。形近字组组员（卡上 `grp.m`，cv #1921）也算候选：notes 里的 cands 是旧候选时，
  判出的组员字照样当倾向字。
- 候选外字 `out`：各级给出的、高／中把握、不在候选里的字（去重，高级别在前），进待审单 `dout`，
  网页当可选按钮显示、不预选（GM3 11-26：候选外的字人审可以直接选）。
- `why`≤400 字：`L1 日/曰分歧；L2 mid：…；L3 已：…`，每级一句，超长从后截断；候选外真字（如「白」）写进 why。
- `refs`：各级 evidence 的 url（仅 http/https，去重，高级别在前，最多 5 条），标题 `t`＝来源类型＋原句前 30 字，≤60 字。
"""
from __future__ import annotations

import json
from pathlib import Path

WHY_MAX = 400          # 11-26 由 200 放宽：待审单要让人直接看到 AI 分析（判为何字、理由、出处），不必再搜
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


def _out_chars(trace: list[dict], cands: list[str], picked: str) -> list[str]:
    out: list[str] = []
    for t in sorted(trace, key=_lvl, reverse=True):
        if t.get("level") == "L1":
            continue
        ch = t.get("char") or ""
        if (isinstance(ch, str) and len(ch) == 1 and ch not in cands and ch != picked and ch not in out
                and t.get("conf") in ("high", "mid") and t.get("status") != "not_found"):
            out.append(ch)
    return out


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


def _ai_block(trace: list[dict], cands: list[str], st: str | None) -> dict | None:
    """最高一级 trace → 待审单上的 `ai` 对象：{c, k, st, lv, s, d, log, refs}（GM3 11-27，网站折叠显示）。

    s＝一句话结论（≤40 字，常显）；d＝详情（≤300 字，折叠）；log＝检索记录 [{src, r, t, u?}]（折叠；浅层判为空）。"""
    best = max(trace, key=_lvl)
    ch = best.get("char") or ""
    if not ch:
        return None
    d = str(best.get("why") or "").strip()
    s = str(best.get("s") or "").strip() or (d[:38] + "…" if len(d) > 40 else d)
    out: dict = {"c": ch, "k": best.get("conf") or "", "lv": best.get("level") or "", "s": s[:40], "d": d[:300],
                 "log": [{k: str(v)[:60] for k, v in e.items() if k in ("src", "r", "t", "u") and v}
                         for e in (best.get("log") or []) if isinstance(e, dict)][:12]}
    if st:
        out["st"] = st
    if ch not in cands and cands:
        out["out_of_cands"] = True      # 倾向字不在候选里（如己已巳组漏己），网站提示
    refs = _refs(trace)
    if refs:
        out["refs"] = refs
    return out


def summarize_trace(trace: list[dict], cands: list[str] | None = None, st: str | None = None) -> dict | None:
    """trace → `{char?, why, refs?, ai?}`；trace 为空返回 None。"""
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
    extra = _out_chars(trace, cands, ch) if cands else []
    if extra:
        out["out"] = extra
    refs = _refs(trace)
    if refs:
        out["refs"] = refs
    ai = _ai_block(trace, cands, st)
    if ai:
        out["ai"] = ai
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
        if row.get("u") is not None and row.get("book"):     # 字格永久编号 u（11-25 起以 u 为准）
            idx[("u", str(row["book"]), int(row["u"]))] = row
    return idx


def find_note(idx: dict, *, cell: str | None = None, group: str | None = None, ctx_hash: str | None = None,
              book: str | None = None, u: int | None = None) -> dict | None:
    """先按（册，u）找，再按（组，ctx 哈希）（重切后仍命中），最后按格号。"""
    if book is not None and u is not None and ("u", str(book), int(u)) in idx:
        return idx[("u", str(book), int(u))]
    if group and ctx_hash and ("hash", group, ctx_hash) in idx:
        return idx[("hash", group, ctx_hash)]
    if cell:
        return idx.get(("cell", cell))
    return None


def _row_st(row: dict) -> str | None:
    """分析状态 released／pending／unsure：存在 trace 最后一轮的 `status`（与 ai_notes.st 虚拟列同一处）。"""
    tr = row.get("trace") or []
    st = (tr[-1] or {}).get("status") if tr else None
    return st if st in ("released", "pending", "unsure") else None


def dian_for(idx: dict, *, cell: str | None = None, group: str | None = None, ctx_hash: str | None = None,
             cands: list[str] | None = None, book: str | None = None, u: int | None = None,
             extra_cands: list[str] | None = None) -> dict | None:
    """出单脚本入口：找到该格的 trace 并摘要，供 `card["dian"] = dian_for(...)`。

    `extra_cands`＝卡上形近字组组员（`grp.m`），并进候选（旧产物没有就照旧）。"""
    row = find_note(idx, cell=cell, group=group, ctx_hash=ctx_hash, book=book, u=u)
    if not row:
        return None
    base = list(cands or row.get("cands") or [])
    base += [c for c in (extra_cands or ()) if c not in base]
    return summarize_trace(row.get("trace") or [], base, _row_st(row))


def released_list(idx: dict, cell_ids: set | None = None) -> list[dict]:
    """放行格的 AI 摘要：`[{u, ai}]`，写进待审单顶层 `released`（网站放行格也能看 AI 分析；GM3 11-27）。

    只取最后一轮 `status == released` 且有 u 的行；`cell_ids` 给了就跳过其中的格号（已在待审格里的不重复）。按 u 排序。"""
    seen, out = set(), []
    for key, row in idx.items():
        if key[0] != "u" or id(row) in seen:
            continue
        seen.add(id(row))
        if _row_st(row) != "released" or (cell_ids and row.get("cell") in cell_ids):
            continue
        ai = _ai_block(row.get("trace") or [], list(row.get("cands") or []), "released")
        if ai:
            out.append({"u": int(row["u"]), "ai": ai})
    return sorted(out, key=lambda x: x["u"])
