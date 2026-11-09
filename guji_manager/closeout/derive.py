"""A01–A03 按当前 book-text 现算（方案 8.9：不写清除事件，每次出单／换单／点校提交时重算，点校重挂并过检查后自然消失）。

判据：
- **A01 anchor_miss**：F-OV-02 式检查——标点／专名的锚点指向 char 里不存在的格，或校验字（标点 `pre_char`、专名 `text`）
  与该格现字不符。不存在的格写在同页最近的新格。
- **A02 add_del**：同样是上面的无效锚点，但落在**增删格所在的句子**里（格级对照表里的「新增」格，或紧邻「删」格的新格；
  句子＝相邻两个句末标点 。？！ 之间）。这一句的锚点都挂到有效格上了，就不再出。
- **A03 anchor_drift**：book-text `check_anchor_drift`（local_check --dev 的「其他标点」）仍报漂移。

纯函数，不读写文件；漂移告警要读 git，由 `drift_items` 包一层（要 book-text 检出）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from .writeback import slots_of

ENDS = set("。？！")
KEEP = ("同格", "改号")


_CELL_RE = re.compile(r"^(\d+):(\d+):(\d+)([a-z]?)$")


def _parse(a: str):
    """格号 `页:列:格[a|b]` → (页, 列, 格, 子格后缀)；认不出 → None（夹注半格带 a／b 后缀，不能直接 int）。"""
    m = _CELL_RE.match(a or "")
    return (int(m[1]), int(m[2]), int(m[3]), m[4]) if m else None


def _strip(a: str) -> str:
    return a.split(":", 1)[1] if a and a.startswith("vol") else a


def add_del_sites(rows) -> set[str]:
    """对照表（`remap_anchors.load_cells` 的行）→ 增删格所在的新格集合：新增格；删格的前后邻格（旧格号±1 经表换成新格）。"""
    m = {}
    for r in rows:
        if r.get("类别") in KEEP and r.get("旧格") and r.get("新格"):
            m[_strip(r["旧格"])] = _strip(r["新格"])
    sites = {_strip(r["新格"]) for r in rows if r.get("类别") == "新增" and r.get("新格")}
    for r in rows:
        if r.get("类别") == "删" and r.get("旧格"):
            q = _parse(_strip(r["旧格"]))
            if not q:
                continue
            p, c, i, sub = q
            for j in (i - 1, i + 1):
                for suf in dict.fromkeys((sub, "", "a", "b")):
                    n = m.get(f"{p}:{c}:{j}{suf}")
                    if n:
                        sites.add(n)
    return sites


def _nearest(slots, pos, anchor: str) -> str | None:
    """不存在的格 → 同页最近的现有格（先比列差再比格序差）；整页都没有则取页号最近的页首格。"""
    t = _parse(anchor)
    if not t:
        return None
    p, c, i, _sub = t
    best = None
    for a, _ch in slots:
        u = _parse(a)
        if not u:
            continue
        q, cc, ii, _s = u
        key = (abs(q - p), abs(cc - c), abs(ii - i))
        if best is None or key < best[0]:
            best = (key, a)
    return best[1] if best else None


def invalid_anchors(char: dict, punct: dict | None, entity: dict | None) -> list[tuple]:
    """F-OV-02 式：返回 (层, 条目, 旧锚, 落点格, 内容, "ANCHOR_MISS｜说明")。落点格＝要出标记的新格。"""
    slots = slots_of(char)
    pos = {a: i for i, (a, _c) in enumerate(slots)}
    out = []
    for i, p in enumerate((punct or {}).get("punctuations") or []):
        a = p.get("anchor")
        if not a:
            continue
        mark = repr(p.get("mark", ""))[1:-1]
        if a not in pos:
            out.append(("punct", f"#{i}", a, _nearest(slots, pos, a) or "", mark, f"ANCHOR_MISS｜锚点指向不存在的格 {a}"))
        elif "pre_char" in p and slots[pos[a]][1] != p["pre_char"]:
            out.append(("punct", f"#{i}", a, a, mark, f"ANCHOR_MISS｜校验字不符：{p['pre_char']}→{slots[pos[a]][1]}"))
    for x in (entity or {}).get("entities") or []:
        anc = x.get("anchor") or {}
        s, t = anc.get("start"), anc.get("end")
        if not s or not t:
            continue
        span = f"{s}～{t}"
        if s not in pos or t not in pos:
            miss = s if s not in pos else t
            out.append(("entity", x.get("id", ""), span, _nearest(slots, pos, miss) or "", x.get("text", ""),
                        "ANCHOR_MISS｜首尾格不存在"))
        else:
            seg = "".join(c for _a, c in slots[pos[s]:pos[t] + 1])
            if pos[t] < pos[s] or seg != x.get("text"):
                out.append(("entity", x.get("id", ""), span, s, x.get("text", ""), f"ANCHOR_MISS｜文字不符：{x.get('text')}→{seg}"))
    return out


def _windows(char: dict, punct: dict | None, sites: set[str]):
    """增删格所在句子的格集合（新格号）。句末标点按 punct 里 mark 含 。？！ 的锚点在读序中的位置切。"""
    slots = slots_of(char)
    pos = {a: i for i, (a, _c) in enumerate(slots)}
    ends = sorted(pos[p["anchor"]] for p in (punct or {}).get("punctuations") or []
                  if p.get("anchor") in pos and set(p.get("mark", "")) & ENDS)
    win: set[str] = set()
    for s in sites:
        if s not in pos:
            continue
        q = pos[s]
        lo = max([e for e in ends if e < q], default=-1) + 1
        hi = min([e for e in ends if e >= q], default=len(slots) - 1)
        win.update(a for a, _c in slots[lo:hi + 1])
    return win


def derive(char: dict, punct: dict | None, entity: dict | None, rows=None, drift=()) -> list[tuple]:
    """现算全部锚点类分流项（A01／A02／A03）。`rows` 是格级对照表（给了才有 A02），`drift` 是 `drift_items` 的结果。"""
    items = invalid_anchors(char, punct, entity)
    if rows:
        win = _windows(char, punct, add_del_sites(rows))
        items = [(l, i, o, n, t, "ADD_DEL｜" + tag.split("｜", 1)[1] if n in win else tag) for l, i, o, n, t, tag in items]
    return items + list(drift)


_DRIFT_RE = re.compile(r"^(?P<file>\S+) (?P<a>\d+:\d+:\d+)（(?P<what>[^）]*)）：(?P<why>.*?)，对齐后应在 (?P<to>\d+:\d+:\d+)$")


def parse_drift(msg: str):
    m = _DRIFT_RE.match(msg.strip())
    if not m:
        return None
    return ("punct", "", m["a"], m["a"], m["what"], f"ANCHOR_DRIFT｜{m['why']}，对齐后应在 {m['to']}")


def drift_items(repo: str | Path, char_rel: str, base: str = "origin/dev") -> list[tuple]:
    """调 book-text `scripts/check_anchor_drift.check_file`：只取「其他标点」（soft）告警。char_rel 是仓内相对路径。"""
    scripts = Path(repo) / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import check_anchor_drift as D
    mb = D.sh("git", "merge-base", "HEAD", base)
    ref = mb.stdout.strip() if mb.returncode == 0 else base
    _hard, soft = D.check_file(ref, char_rel)
    return [it for it in (parse_drift(m) for m in soft) if it]
