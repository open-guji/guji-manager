"""导出的 cord 换到网站页图坐标（原在 cv ``scripts/zhengli/republish.py``，2026-11-27 随整张换单脚本退役搬来）。

2026-11-04 殿本四庫總目图源切到文淵閣本：网站书影和 book-text 的坐标已按新页表换算（book-text#397），
cv 还在旧页图上出产物（换源要等整册重跑）。所以导出的 cord（sprite 用它在旧页上裁图，不能动）拷进 book-text
前要换一次。逐页：图 sha 已是新页 → 不动；是 ``from_rev.sha256`` → 换；都不是 → 报错（cord 和页表对不上）。
页表里没有 ``from_rev``（不是换源出来的版）就原样不动。框取变换后外接矩形取整，``regions.rules`` 逐点换。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOOL = "guji-manager guji_manager/swap/cord_site.py"


def rebase_cord(cord: dict, table: dict | None, tool: str = TOOL) -> int:
    """就地把导出的 cord 从 cv 出产物用的旧页图换到页表 ``table`` 那版的新页图（页表 ``from_rev.H``），返回换了几页。"""
    from ..datastore import source_xform as X
    if not table:
        return 0
    xf = X.by_page(table)
    if not xf:
        return 0
    rows = {int(p["page"]): p for p in table.get("pages", [])}
    frm = X.from_rev(table)

    def ibox(x, b):
        return [int(round(v)) for v in x.xywh(*b)]

    n, bad = 0, []
    for pg in cord.get("pages", []):
        x, row = xf.get(pg.get("page")), rows.get(pg.get("page"))
        img = pg.get("image") or {}
        if row is not None and img.get("sha256") == row.get("sha256"):
            continue                                   # 已是新页坐标
        if x is None or img.get("sha256") != row["from_rev"]["sha256"] \
                or (img.get("width"), img.get("height")) != (x.old_w, x.old_h):
            bad.append(str(pg.get("page")))
            continue
        pg["image"] = {**img, "width": x.new_w, "height": x.new_h, "sha256": row["sha256"]}
        if isinstance(pg.get("canvas"), dict):
            pg["canvas"].update(width=x.new_w, height=x.new_h)
        for key in ("cells", "columns", "marks", "regions"):
            for it in pg.get(key) or []:
                if it.get("box"):
                    it["box"] = ibox(x, it["box"])
        for r in pg.get("regions") or []:
            if r.get("rules"):
                r["rules"] = [[[int(round(a)), int(round(b))] for a, b in x.points(line)] for line in r["rules"]]
        pg.setdefault("producers", {})["rebase"] = {
            "tool": tool, "from_source_rev": frm, "to_source_rev": table.get("rev"),
            "why": "图源换版，按页表 from_rev.H 从 cv 产物用的旧页图换到网站用的新页图"}
        n += 1
    if bad:
        raise ValueError(f"cord 有 {len(bad)} 页的图既不是页表 r{table.get('rev')} 的新页、也不是它的 from_rev 旧页："
                         + "、".join(bad[:20]))
    return n


def site_page_table(book_id: str, volume) -> dict | None:
    """网站书影用的页表：R2 上最新一版（含预发 staged，四庫總目文淵閣本就是 staged 版先上线的）；R2 没有页表 → None。"""
    from ..datastore import sources as S
    src = S._client()
    vol = S.norm_vol(str(volume))
    revs = S.revisions(src, book_id, vol)
    return S.read_table(src, book_id, vol, revs[-1]) if revs else None


def copy_cord_for_site(src: Path, dst: Path) -> int:
    """导出的 cord 换到网站页图坐标后写进 book-text（导出目录里的原件不动，sprite 还要用）。返回换了几页。"""
    from ..formats import guji_char_cord as cc
    cord = json.loads(Path(src).read_text(encoding="utf-8"))
    try:
        table = site_page_table(cord["book_id"], cord["volume"])
        n = rebase_cord(cord, table)
    except ValueError as e:
        sys.exit(f"✗ cord 换不到网站页图坐标，不推：{e}")
    if n:
        print(f"cord 换到网站页图坐标：{n} 页（页表 r{table['rev']:03d}）")
    Path(dst).write_text(cc.dumps(cord), encoding="utf-8", newline="\n")
    return n
