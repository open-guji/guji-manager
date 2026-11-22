"""库文一致：字形库每个刻例的字，对它那一格文本里的字，不一样的找出来并处理（2026-11-18，Sheldon 定）。

## 为什么

字形库和文本是同一格的两份记录：库里记「这块图是什么字」，文本（`seed_admit` 产物，换包后进 book-text）记
「这一格显示什么字」。两边各改各的：体检撤库、改标只动库（`glyph_audit`），人裁、重跑只动文本。库改了以后文本要等
那一册下次重跑第 7 步、换包才跟着变，中间没有任何一步核对两边。全唐文 11-17 夜改标 138 例后实测：b2 产物 001–045 册
3.6 万刻例里 158 格两边不一样，其中 83 格是早就不一致、一直没人发现的。

## 比什么

一册一册比：库里 `v2:<册>:…` 的每个刻例，对 `seed_admit` 产物里同一格。两边的字先按书级码位归一
（`BookSpec.canonical_char`，陝／陜、寛／寬 这类不算不一致）再比。不一样的分八类，各有去处：

| 类 | 判据 | 处理（`--apply`） |
|---|---|---|
| `text_stale` 文本过期 | 库例入库时刻晚于这一页产物的写出时刻 | 这一页 `seed_admit` 标失效，`guji rerun --stale` 重算后文本跟上 |
| `shifted` 库图错位 | 库标正是同一列上下邻格的字 | 库图是旧切分的字块、格号整体挪过：机器来路的撤库例（文本不动），人裁来路的只报 |
| `follow_human` 文本是人裁 | 文本通道是人裁，库例是机器来路或更早的人裁 | 库图过字体模板：认成文本的字 → 库例改成文本的字（`glyph_audit relabel`）；不是 → 库例多半挂着旧格号，机器来路的撤、人裁来路的只报 |
| `machine` 两边都是机器 | 文本机器放行，库例机器来路 | 库图过字体模板重新识别：认成文本的字 → 库例改标（仍是机器来路）；认成库标 → 文本可疑，这一格加进待审单复审；都不是 → 也进待审单复审，库例不撤（史記 11-18：这类 13 格库图其实都对，撤了丢好刻例） |
| `human_unapplied` 库是人裁、文本没采信 | 库例人裁来路，文本机器放行了别的字 | 多半是切分变过、人裁落在了别的格上：这一格加进待审单复审，库不动 |
| `orphan` 格没了 | 库例的格在产物里不存在 | 机器来路的撤库例；人裁来路的只报 |
| `pending` 格在待审 | 文本这一格没放行 | 不处理（人裁定了自然一致） |
| `ok` | 归一后同字 | — |

「文本可疑」不直接改文本：改字要么靠人裁、要么靠重跑，这里只把它送到人眼前。

## 怎么触发

- 手动：`guji glyph-db text-check --books 001,002 [--apply] [--report x.json]`（不加 `--apply` 只报告）。
- 自动：`guji pipeline` 整册跑完（`hooks.finished`，在放行格回库之后）对这一册跑一遍。缺省只报告；
  `workspace.yaml` 写 `glyph_lib.text_check: apply` 才动库，写 `false` 关掉；`GUJI_LIB_TEXT_CHECK=0` 临时关。

用法、数字与边界见 `wiki/自动化流程/库文一致.md`。
"""
from __future__ import annotations

import collections
import datetime
import json
import sqlite3
from pathlib import Path

CATS = ("ok", "pending", "text_stale", "shifted", "follow_human", "machine", "human_unapplied", "orphan")
HUMAN = ("human",)
SAME_GROUP = frozenset("己已巳")     # 同 cv `utils/ji_yi_si.FAMILY`
MARGIN_MIN = 0.03     # 字体模板首位领先次位不到这么多，不凭它改库标（史記 11-18：黄 被认成 簧）


def config(ws_dir: Path | str | None) -> str | None:
    """`workspace.yaml` 的 `glyph_lib.text_check`：`false` → None（关）；`report` → "report"（只报告）；
    没写或 `apply`/`true` → "apply"（缺省，Sheldon 2026-11-18 定：能确定的自动处理，其余进待审）。"""
    import yaml
    y = Path(ws_dir or ".") / "workspace.yaml"
    cfg = (yaml.safe_load(y.read_text(encoding="utf-8")) or {}) if y.exists() else {}
    v = (cfg.get("glyph_lib") or {}).get("text_check", "apply")
    if v is False:
        return None
    if v == "report":
        return "report"
    if v in (None, True, "apply"):
        return "apply"
    raise SystemExit(f"glyph_lib.text_check 只认 false／report／apply，不认 {v!r}")


def lib_rows(db_path: Path | str, book: str) -> dict[str, dict]:
    """库里这一册的刻例：格键（不带 `v2:`）→ {label, provenance, at, via}。"""
    out: dict[str, dict] = {}
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as c:
        q = ("SELECT i.instance_id, i.label, a.provenance, a.evidence, a.admitted_at FROM instances i "
             "LEFT JOIN admissions a ON a.instance_id = i.instance_id WHERE i.instance_id LIKE ?")
        for iid, label, prov, ev, at in c.execute(q, (f"v2:{book}:%",)):
            try:
                e = json.loads(ev) if ev else {}
            except ValueError:
                e = {}
            out[iid[3:]] = {"label": label or "", "provenance": prov or "", "at": at or "",
                            "via": str(e.get("via") or e.get("channel") or e.get("batch") or "")}
    return out


def _is_human(cell: dict) -> bool:
    return cell.get("channel") == "human" or cell.get("provenance") == "human"


def classify(lib: dict[str, dict], cells: dict[str, dict], canon=None,
             page_at: dict[int, str] | None = None) -> list[dict]:
    """逐例分类。纯函数。`cells`：格键 → `seed_admit` 格记录；`page_at`：页 → 这一页产物写出时刻（UTC ISO）。"""
    canon = canon or (lambda c: c)
    page_at = page_at or {}
    rows = []
    for k, r in sorted(lib.items()):
        cell = cells.get(k)
        row = {"key": k, "lib": r["label"], "lib_prov": r["provenance"], "lib_at": r["at"], "lib_via": r["via"]}
        if cell is None:
            row["cat"] = "orphan"
            rows.append(row)
            continue
        ch = cell.get("char") or ""
        row.update(text=ch, channel=cell.get("channel") or "", admit=bool(cell.get("admit")))
        try:
            page = int(k.split(":")[1])
        except (IndexError, ValueError):
            page = -1
        if ch and (canon(ch) == canon(r["label"]) or (ch in SAME_GROUP and r["label"] in SAME_GROUP)):
            row["cat"] = "ok"           # 己／已／巳 字形本就不分，库记刻形、文本记读法，不算不一致
        elif r["at"] and page_at.get(page) and r["at"][:19] > page_at[page][:19]:
            row["cat"] = "text_stale"
        elif not cell.get("admit"):
            row["cat"] = "pending"
        elif any(canon((cells.get(n) or {}).get("char") or "") == canon(r["label"]) for n in _neighbors(k)):
            row["cat"] = "shifted"      # 库标正是上下邻格的字：库图是旧切分的字块，格号整体挪过
        elif _is_human(cell):
            row["cat"] = "follow_human"
        elif r["provenance"] in HUMAN:
            row["cat"] = "human_unapplied"
        else:
            row["cat"] = "machine"
        rows.append(row)
    return rows


def decide(row: dict, canon=None, top1: str | None = None, margin: float | None = None) -> str:
    """一例该怎么办 → 动作名。纯函数。`top1`：库图过字体模板的首位字（`machine`、`follow_human` 两类要）。

    `invalidate` 标这一页失效；`relabel` 库例改成文本的字（人裁来路）；`relabel_auto` 改标但保持机器来路；
    `review` 这一格进待审单复审；`evict_review` 撤库例并让这一格回人审；`evict` 只撤库例；`report` 只报；`none` 不动。"""
    canon = canon or (lambda c: c)
    cat = row["cat"]
    if cat in ("ok", "pending"):
        return "none"
    if cat == "text_stale":
        return "invalidate"
    if cat == "shifted":
        return "report" if row["lib_prov"] in HUMAN else "evict"
    if cat == "follow_human":
        if not _single_han(row.get("text")):
            return "report"
        if top1 is not None and canon(top1) != canon(row["text"]):
            # 库图不像人裁的那个字：多半是重切后库例还挂着旧格号（殿本 vol01 15 例），不能拿文本去改它的标
            return "report" if row["lib_prov"] in HUMAN else "evict"
        return "relabel"
    if cat == "human_unapplied":
        return "review"
    if cat == "orphan":
        return "report" if row["lib_prov"] in HUMAN else "evict"
    if top1 is None:
        return "report"
    if canon(top1) == canon(row.get("text") or ""):
        if margin is not None and margin < MARGIN_MIN:
            return "review"             # 模板首位领先太少，不够当改库的证据：送人看
        return "relabel_auto" if _single_han(row.get("text")) else "report"
    return "review"         # 认成库标（文本可疑）或两边都不是（都没佐证）：都送人看，库例不撤


def _single_han(ch: str | None) -> bool:
    return bool(ch) and len(ch) == 1 and ord(ch) >= 0x2E80


def _seed(root: Path, book: str) -> tuple[dict[str, dict], dict[int, str]]:
    cells: dict[str, dict] = {}
    page_at: dict[int, str] = {}
    made = _manifest_ts(root / book / "seed_admit" / "_manifest.jsonl")
    for f in sorted((root / book / "seed_admit").glob("p*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pm = d[next(iter(d))]
        try:
            page = int(pm.get("page") or f.stem.lstrip("p"))
        except ValueError:
            continue
        # 这一页是什么时候算的：认 manifest 的 `ts`（没重算的页存包、取包都不变）；没有才退回文件时刻
        # （取包会把文件时刻刷成取包那一刻，史記 11-18 两格因此没判成文本过期）。
        ts = made.get(f.stem) or f.stat().st_mtime
        page_at[page] = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat()
        for col in pm.get("columns") or []:
            for r in col.get("chars") or []:
                cells[r["id"]] = r
    return cells, page_at


def _manifest_ts(path: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("key") and isinstance(e.get("ts"), (int, float)):
            out[str(e["key"])] = float(e["ts"])       # 后到覆盖
    return out


def _neighbors(key: str) -> list[str]:
    """同一列上下各一格的格键（半格 a／b 保持同侧）。"""
    head, _, slot = key.rpartition(":")
    num = slot.rstrip("ab")
    if not num.lstrip("-").isdigit():
        return []
    return [f"{head}:{int(num) + d}{slot[len(num):]}" for d in (-1, 1)]


class _Top1:
    """库里存的图（已是入库口径）过字体模板，取首位字。"""

    def __init__(self, db_path):
        from .lib_backfill import Verifier
        self.v = Verifier()
        self.db_path = db_path

    def __call__(self, key: str) -> tuple[str, float] | None:
        import cv2
        from .._cv import normalize_patch
        np = self.v.np
        with sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True) as c:
            r = c.execute("SELECT patch_png FROM instances WHERE instance_id=?", (f"v2:{key}",)).fetchone()
        if not r or not r[0]:
            return None
        img = cv2.imdecode(np.frombuffer(r[0], np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        q = np.asarray(self.v.cnn.embed([normalize_patch(img)]), dtype=np.float32)[0]
        sc = self.v.mat @ (q / (np.linalg.norm(q) + 1e-9))
        o = np.argsort(-sc)[:2]
        return self.v.names[int(o[0])], round(float(sc[o[0]] - sc[o[1]]), 4)


def run(books: list[str], *, apply: bool = False, batch: str | None = None, top1=None, log=None,
        report: str | None = None, products: Path | str | None = None) -> dict:
    """对 `books` 各册比一遍，（`apply` 时）按 `decide` 处理。返回报告。"""
    from .._cv import glyph_db_path, load_book, products_root
    say = log or (lambda *_: None)
    if apply:
        from .lib_backfill import apply_problem
        bad = apply_problem()
        if bad:
            raise SystemExit("✗ 库文一致没处理：" + bad)
    dbp = glyph_db_path()
    root = Path(products) if products else products_root()
    stat: collections.Counter = collections.Counter()
    acts: collections.Counter = collections.Counter()
    todo: list[dict] = []
    skipped: list[str] = []
    for b in books:
        cells, page_at = _seed(root, b)
        if not cells:
            skipped.append(b)
            continue
        canon = load_book(b).canonical_char
        rows = classify(lib_rows(dbp, b), cells, canon, page_at)
        for r in rows:
            stat[r["cat"]] += 1
            if r["cat"] in ("ok", "pending"):
                continue
            t = mg = None
            if r["cat"] in ("machine", "follow_human"):
                top1 = top1 or _Top1(dbp)
                got = top1(r["key"])
                t, mg = got if isinstance(got, tuple) else (got, None)
                r["tpl_top1"], r["tpl_margin"] = t, mg
            r["action"] = decide(r, canon, t, mg if r["cat"] == "machine" else None)
            acts[r["action"]] += 1
            todo.append(r)
        say(f"  {b}: 刻例 {len(rows)}，不一致 {sum(1 for r in rows if r['cat'] not in ('ok', 'pending'))}")
    batch = batch or f"lib-text-check-{datetime.date.today():%Y%m%d}"
    rep = {"db": str(dbp), "books": books, "skipped_no_product": skipped, "batch": batch, "apply": apply,
           "stat": dict(stat), "actions": dict(acts), "rows": todo}
    if apply and todo:
        rep["applied"] = _apply(todo, batch, dbp)
    if report:
        Path(report).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep


def _apply(todo: list[dict], batch: str, dbp) -> dict:
    from .._cv import EventLog, EventTarget, ProductStore, export_store, glyph_store_path, make_event, page_key
    from .._cv import GlyphDB
    from ..feedback.glyph_audit import glyph_audit
    done: collections.Counter = collections.Counter()
    elog = EventLog()
    base = elog.latest_seq(batch)
    evs = []
    src = "库文一致"
    for r in todo:
        a, k = r["action"], r["key"]
        bk = k.split(":")[0]
        tgt = EventTarget(step="glyph_audit", unit="cell", key=f"v2:{k}", book=bk)
        if a == "relabel":
            p = {"v": "relabel", "char": r["text"], "instance_id": f"v2:{k}", "char_self": r["lib"],
                 "source": f"{src}:文本是人裁"}
        elif a == "relabel_auto":
            p = {"v": "relabel", "char": r["text"], "instance_id": f"v2:{k}", "char_self": r["lib"],
                 "provenance": "auto", "tpl_top1": r.get("tpl_top1"), "source": f"{src}:字体模板认成文本的字"}
        elif a in ("evict", "evict_review"):
            p = {"v": "evict", "instance_id": f"v2:{k}", "char_self": r["lib"],
                 "source": f"{src}:" + ({"shifted": "库图错位（旧切分）", "follow_human": "库图不像人裁的字（疑似旧格号）"}.get(r["cat"], "格已不在") if a == "evict" else "库标与文本都不被字体模板支持")}
            if a == "evict_review":
                p["review"] = True
        else:
            continue
        evs.append(make_event(batch, base + len(evs) + 1, "glyph_audit", tgt, p, actor="model"))
    if evs:
        elog.append(evs)
        res = glyph_audit([(e, None) for e in evs], db_path=str(dbp))
        elog.mark_consumed("glyph_audit", evs, note="库文一致：已直接处理")
        done["lib_events"] = len(evs)
        done["lib_errors"] = len(res.errors)
        db = GlyphDB(str(dbp))
        try:
            export_store(db, glyph_store_path())
        finally:
            db.close()
    st = ProductStore()
    pages = {(r["key"].split(":")[0], int(r["key"].split(":")[1])) for r in todo if r["action"] == "invalidate"}
    for bk, pg in sorted(pages):
        done["invalidated_pages"] += bool(st.manifest(bk, "seed_admit").invalidate(page_key(pg), "库文一致：库例晚于产物"))
    done["review_added"] = _to_review([r for r in todo if r["action"] == "review"])
    return dict(done)


def _to_review(rows: list[dict]) -> int:
    """把格加进待审单当复审格（库不动、文本不动，等人看）。待审单真源在数据目录，随 `guji db sync` 推。"""
    if not rows:
        return 0
    import os
    from .._cv import chapter_of, data_root, workspace_root
    from ..review import pending_items as P
    ws = Path(workspace_root())
    data = Path(data_root(ws) or ws)
    text_id = ws.name.split("-", 1)[0]
    by = os.environ.get("GUJI_ACTOR", "") or "lib_text_check"
    n = 0
    by_book: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        by_book[r["key"].split(":")[0]].append(r)
    for bk, rs in by_book.items():
        chapter = chapter_of(bk, None)
        if not chapter:
            continue
        store = P.ItemStore.open(data, text_id, chapter)
        for r in rs:
            cell = r["key"].split(":", 1)[1]
            note = (f"字形库这一格记的是「{r['lib']}」（{'人裁' if r['lib_prov'] in HUMAN else '机器'}），"
                    f"文本是「{r.get('text', '')}」，请看图定")
            try:
                store.add(cell, {"recheck": True, "note": note}, by=by, why="库文一致", src="script:lib_text_check")
                n += 1
            except (KeyError, ValueError):
                continue
        store.save()
        if P.sheet_path(data, text_id, chapter).exists():      # 整张单跟着重导（还没出过单的章不凭空造一张）
            from ..cli_pending import export
            export(store, data)
    return n


def summary(rep: dict) -> str:
    s, a = rep["stat"], rep["actions"]
    total = sum(s.values())
    bad = total - s.get("ok", 0) - s.get("pending", 0)
    names = {"invalidate": "标失效待重算", "relabel": "库跟人裁改标", "relabel_auto": "库按重新识别改标",
             "review": "进待审复审", "evict_review": "撤库例并回人审", "evict": "撤无格库例", "report": "只报"}
    parts = "、".join(f"{names[k]} {v}" for k, v in a.items() if v and k in names)
    return f"刻例 {total}，库文不一致 {bad}" + (f"（{parts}）" if parts else "")


def auto_check(args, eng, steps: list[str]) -> None:
    """`hooks.finished`：整册跑完，对这一册比一遍。缺省自动处理（`glyph_lib.text_check: report` 只报告）；
    这台机器不该改库时（借库跑批、部分副本、本机库比账本旧，同放行格回库的护栏）退回只报告。"""
    import os
    if os.environ.get("GUJI_LIB_TEXT_CHECK", "1") == "0":
        return
    if str(getattr(args, "pages", "")) != "all" or "seed_admit" not in steps:
        return
    book = eng.book.id
    try:
        from .._cv import workspace_root
        mode = config(workspace_root())
        if mode is None:
            return
        if mode == "apply":
            from .lib_backfill import apply_problem
            why = apply_problem()
            if why:
                print(f"  ⚠ 库文一致 {book}：这台机器不处理、只报告（{why}）")
                mode = "report"
        rep = run([book], apply=(mode == "apply"))
        bad = sum(v for k, v in rep["stat"].items() if k not in ("ok", "pending"))
        if bad:
            print(f"  {'✓' if mode == 'apply' else '⚠'} 库文一致 {book}：{summary(rep)}"
                  + ("" if mode == "apply" else f"；处理：guji glyph-db text-check --books {book} --apply"))
    except BaseException as e:     # noqa: BLE001 —— 核对失败不算跑批失败
        if isinstance(e, KeyboardInterrupt):
            raise
        print(f"  ⚠ 库文一致没跑成（{e}）：手动 guji glyph-db text-check --books {book}")
