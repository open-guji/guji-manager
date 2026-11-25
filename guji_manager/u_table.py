"""从字格身份账出「旧切分→新切分」格级对照表（T2，设计 doc/4-反馈迭代/设计-字格u改挂.md §二.5）。

有账的册重切（含换图源）后，不再另跑框 IoU 配对：账里每页的**上一份**与**当前一份**切分都记了「格号→u」，
同一个 u 就是同一格。这里把它写成和 A31 `old_new_cells/<册>.tsv` 同格式的表
（`旧格 新格 旧字 新字 类别 IoU 说明`，类别 同格／改号／删／新增），`feedback/cell_migrate`（迁票）、
`ops/cell_rekey`（字形库等改键）、swap 都照旧读这张表，下游不用改。

- 旧格的 u 在当前账里还在（哪一页都算）：同格（格号没变）或改号；
- 旧格的 u 并掉了／删掉了（当前账行 lineage 里 `into`／`gone`）或账里已没有：删，说明写清；
- 当前格的 u 在旧切分里没有：新增（拆出来的写 `split_from`）。
- IoU：两份都有框才算（同一图源时有意义；换图源时只作参考）。
"""
from __future__ import annotations

from collections.abc import Iterable

from .uid.ledger import Ledger
from .uid.match import iou, xywh_to_box

COLS = ("旧格", "新格", "旧字", "新字", "类别", "IoU", "说明")


def table_rows(led: Ledger, pages: Iterable[int] | None = None) -> list[dict]:
    """→ [{旧格, 新格, 旧字, 新字, 类别, IoU, 说明}]；只出入过两次以上账的页（只入一次账的页没有「旧切分」）。"""
    want = None if pages is None else {int(p) for p in pages}
    pairs = []
    for pg in sorted(led.latest()):
        if want is not None and pg not in want:
            continue
        prev, cur = led.page_pair(pg)
        if prev is not None:
            pairs.append((prev, cur))
    now = {v: k for k, v in led.current().items()}                  # u → 当前格号（全册）
    now_line = {}                                                   # 当前格号 → 当前账行（取字、框）
    for d in led.latest().values():
        for k in d["map"]:
            now_line[k] = d
    old_us: set[int] = set()
    rows: list[dict] = []
    for prev, cur in pairs:
        why = {}
        for x in cur.get("lineage") or []:
            if "into" in x:
                why[int(x["u"])] = f"并入 u{int(x['into'])}"
            elif x.get("gone"):
                why[int(x["u"])] = "格没了"
        for k, u in prev["map"].items():
            u = int(u)
            old_us.add(u)
            oc = (prev.get("chars") or {}).get(k, "")
            new = now.get(u)
            if new is None:
                rows.append({"旧格": k, "新格": "", "旧字": oc, "新字": "", "类别": "删", "IoU": "",
                             "说明": f"u{u} " + (why.get(u) or "账里已没有")})
                continue
            nl = now_line[new]
            nc = (nl.get("chars") or {}).get(new, "")
            ob, nb = (prev.get("boxes") or {}).get(k), (nl.get("boxes") or {}).get(new)
            s = f"{iou(xywh_to_box(ob), xywh_to_box(nb)):.3f}" if ob and nb else ""
            rows.append({"旧格": k, "新格": new, "旧字": oc, "新字": nc, "类别": "同格" if k == new else "改号",
                         "IoU": s, "说明": f"u{u}"})
    for prev, cur in pairs:
        split = {int(x["u"]): int(x["split_from"]) for x in cur.get("lineage") or [] if "split_from" in x}
        for k, u in cur["map"].items():
            u = int(u)
            if u in old_us:
                continue
            nc = (cur.get("chars") or {}).get(k, "")
            rows.append({"旧格": "", "新格": k, "旧字": "", "新字": nc, "类别": "新增", "IoU": "",
                         "说明": f"u{u}" + (f" 拆自 u{split[u]}" if u in split else "")})
    return rows


def to_tsv(rows: list[dict]) -> str:
    out = ["\t".join(COLS)]
    for r in rows:
        out.append("\t".join(str(r[c]) for c in COLS))
    return "\n".join(out) + "\n"
