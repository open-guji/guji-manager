"""裁定的格锚点（裁定键长期方案③，GM4／CV4 2026-11-24）：回填与新写入。

cv 的 `RulingStore.get_anchor` 在窗口键（含版本等价）都没命中时，用「格号＋写裁定时这一页的 cells_sha＋整理本对位字 ref」
三样全对的裁定做后备。裁定 payload 里要自带 `cells_sha`、`ref`：
- 新写的裁定：写入方当场带上（`anchor_fields`；cv 口径 `open_guji_cv.feedback.rulings.page_cells_sha`，读写必须同一个函数）。
- 存量：本模块 `backfill` 回填，**只回填能证明「现产物就是当时问这条裁定时的那份」的**——裁定自带的窗口哈希、提示词版本、
  整理本对位字都与现产物重算的一致；证明不了的不回填，留给网站人审。回填是追加一条同键同字的新事件（后到覆盖），不改字、不改把握。
"""
from __future__ import annotations

from .ruling_write import append_rulings
from .admit_names import RULING_STEP, final_dir, page_body

import json
import sys
from pathlib import Path


def page_sha(products: Path, book: str, page: int) -> str | None:
    """本页产物戳（cv `page_cells_sha`）；取不到（没有 Step3 切分产物）→ None。要先设工作区（读册配置）。"""
    try:
        from ._cv import page_cells_sha
    except (ImportError, AttributeError) as e:   # cv 太旧，没有 #1832
        raise SystemExit("cv 版本太旧：没有 feedback.rulings.page_cells_sha（要 open-guji-cv #1832 之后）") from e
    from ._cv import ProductStore
    return page_cells_sha(book, page, ProductStore(Path(products)))


def anchor_fields(products: Path, book: str, page: int, ref: str | None) -> dict:
    """新写裁定时并进 payload 的锚点字段；取不到 cells_sha 就什么都不加（不写半截锚点）。"""
    sha = page_sha(products, book, page)
    return {"cells_sha": sha, "ref": ref or ""} if sha else {}


def _page_no(f: Path) -> int | None:
    try:
        return int(f.stem.lstrip("p"))
    except ValueError:
        return None


def backfill(products: Path, book: str, store, batch: str, *, write: bool = False, root=None) -> list[dict]:
    """给 ``book`` 的存量裁定回填 cells_sha＋ref。→ 清单行 {cell, 组, 版本, 结果, 原因}；``write`` 才追加事件。"""
    from . import ruling_hits as RH
    from ._cv import RULING_KIND, EventTarget, RulingLog, llm_questions_of_page, make_event, ruling_ctx_hash
    by_cell = RH._rulings_by_cell_all(store)
    rows, evs = [], []
    for f in sorted(final_dir(Path(products) / book).glob("p*.json")):
        page = _page_no(f)
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        cells = {c["id"] for col in page_body(doc).get("columns") or [] for c in col.get("chars") or []}
        todo = [c for c in cells if c in by_cell and not by_cell[c].get("cells_sha")]
        if not todo or page is None:
            continue
        sha = page_sha(products, book, page)
        if not sha:
            rows += [{"cell": c, "组": by_cell[c].get("group"), "版本": by_cell[c].get("prompt_ver"), "结果": "不回填",
                      "原因": "这页取不到 Step3 切分戳"} for c in todo]
            continue
        amap: dict[str, str] = {}
        try:
            ar = json.loads((Path(products) / book / "align_ref" / f.name).read_text(encoding="utf-8")).get("align_ref", {})
            if ar.get("anchored", True) is not False:
                amap = {c["id"]: c.get("align_char") or "" for c in ar.get("chars") or [] if c.get("id")}
        except (OSError, ValueError):
            pass
        proof: dict[str, str] = {}      # 格 → 证明（窗口哈希与版本、对位字都一致）
        for q in llm_questions_of_page(doc):
            r = by_cell.get(q["cell"])
            if r and q["cell"] in todo and r.get("group") == q["group"] and r.get("prompt_ver") == q["ver"] \
                    and (r.get("ctx") or {}).get("hash") == ruling_ctx_hash(q["l"], q["r"]):
                proof[q["cell"]] = "窗口哈希与版本一致"
        try:
            win = RH._vis_window(doc, amap)
        except Exception:  # noqa: BLE001
            win = {}
        for c in todo:
            r = by_cell[c]
            w = win.get(c)
            if c not in proof and r.get("group") == "O" and w is not None \
                    and (r.get("ctx") or {}).get("hash") == ruling_ctx_hash(w[1], w[2]) \
                    and (r.get("ref") or "") == (amap.get(c) or ""):
                proof[c] = "终审窗口哈希与对位字一致"
        for c in todo:
            r = by_cell[c]
            base = {"cell": c, "组": r.get("group"), "版本": r.get("prompt_ver")}
            if c not in proof:
                rows.append({**base, "结果": "不回填", "原因": "证明不了现产物就是当时问的那份（窗口／版本／对位字不一致）"})
                continue
            ref = r.get("ref") if r.get("ref") is not None else amap.get(c, "")
            rows.append({**base, "结果": "回填" if write else "可回填", "原因": proof[c]})
            evs.append((c, {**r, "cells_sha": sha, "ref": ref or amap.get(c) or ""}, rows[-1]))
    if evs:      # 先按 cv 写前校验筛一遍（干跑也筛）：串组版本等过不了的标「不回填」，不拖垮整批
        from .ruling_write import screen
        seq = 0
        built = []
        for c, pl, row in evs:
            seq += 1
            built.append((make_event(batch, seq, RULING_KIND, EventTarget(step=RULING_STEP, unit="cell", key=c, book=book),
                                     pl, actor="model"), row))
        ok, bad = screen([e for e, _ in built])
        why = {id(e): m for e, m in bad}
        for e, row in built:
            if id(e) in why:
                row["结果"], row["原因"] = "不回填", "cv 写前校验不过：" + why[id(e)][:120]
        if write and ok:
            log = store.log if root is None and hasattr(store, "log") else (RulingLog(root) if root else RulingLog())
            seq = max((e.seq for e in log.read(batch, raw=True)), default=0)
            out = []
            for e in ok:
                seq += 1
                out.append(make_event(batch, seq, RULING_KIND, e.target, e.payload, actor="model"))
            append_rulings(log, out)
    return rows


def cmd(a) -> None:
    from ._cv import RulingStore
    store = RulingStore()
    store._batch = a.batch
    allrows = []
    for b in [x.strip() for x in a.books.split(",") if x.strip()]:
        rows = backfill(Path(a.products), b, store, a.batch, write=a.write)
        n = sum(1 for r in rows if r["结果"] != "不回填")
        print(f"{b}：待回填 {len(rows)} 条，{'已写' if a.write else '可回填'} {n}，不回填 {len(rows) - n}", file=sys.stderr)
        allrows += [{**r, "册": b} for r in rows]
    cols = ["册", "cell", "组", "版本", "结果", "原因"]
    text = "\t".join(cols) + "\n" + "".join("\t".join(str(r.get(c) or "") for c in cols) + "\n" for r in allrows)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"清单：{a.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    if a.write:
        print(f"已追加到批次 {a.batch}；guji db sync 推库", file=sys.stderr)
