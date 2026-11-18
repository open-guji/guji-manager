"""放行格回库：机器已放行、库里却没有刻例（或不足）的字，核验后补进本书字形库（2026-11-17，Sheldon 定）。

## 为什么

机器放行的格本来不进字形库：持续进库的只有人裁（`guji db sync` 顺带落库，`feedback/auto_admit.py`），
机器来路的刻例全靠人手跑批（cv `scripts/book_lib_auto.py`）。全唐文 11-08 之后没人再跑，结果 120 册里
`rare_ref`／`witness3` 放行了 6.2 万格的 3859 个字，库里一例都没有：5a 相似度模型认不出这些字，只能认成
共用部件的别的字（樹认成榭、鄲认成鄆），每册都要靠第 7 步纠回来。七册实测 198 个 5a 自信错里 173 个是这个原因。

## 做什么

对一册（或几册）`seed_admit` 已放行的格：

1. **选格**：放行通道在 `channels`（缺省 `rare_ref`、`witness3`，都是有整理本作证的通道）、放行字是单个汉字、
   库里该字现有刻例不足 `cap`（缺省 3）；该格已在库、已有人裁、曾被撤过库的一律不选。
2. **核验**：取管线自己的字块（`char_patch`），按入库同一把二值化和归一，得到**库里实际会存的那张图**，
   过字体模型（十万字模板）：模板首位必须就是放行字，墨量 >`INK_MIN`。不过的不进库，只记进报告。
   这一条是为了不重蹈 11-11 至 11-13「看图加厚」批的错：那一批凭「看着与参校本同形」入库，分不开形近字，
   占库 13% 却占查实错标的 75%。字体模板首位在十万字里选一，形近字的另一边就在候选里，认成它就不过。
3. **抢首位核验**（2026-11-18，史記 r80）：这一册核验过的候选整批模拟进库（cv `BackfillProbe.steal_check`），
   用本册已放行格回放，库首位被新字抢走（harm）、又没有格被它救回（help）的字整字不进，记 `near_common`。
   只看形状的门槛分不开好坏（回库字多半库里 0 例，近邻全是别字），所以直接模拟。cv 早于 #1679 时不闸、摘要里报 ⚠。
4. **入库**：`GlyphDB.admit_instance(provenance="auto")`，同时追加一条 `confirm` 事件
   （`actor=model`、`payload.source="auto"`、`backfill: true`，不算人裁，不进绑定表），证据里带通道、批次和
   核验结果，可按批次整批撤回（cv `scripts/book_lib_auto.py --withdraw <批次>`）。之后人裁同一格，以人裁为准。
   事件可重放：`db sync` 遇到两边都改了字形库会取库里的、让本地新事件重新消费，`glyphdb_admit` 认得带
   `backfill` 标的事件，按事件里的字块键从缓存取图重新进库（`feedback/consumers.py::_admit_backfills`）。

每字按 `glyph_match` 覆盖度从高到低试，补够 `cap` 例就停，所以每册只取几百格的图。

## 怎么触发

- 自动（缺省开，`workspace.yaml` 写 `glyph_lib.auto_backfill: false` 关）：`guji pipeline` 整册跑完没有失败页就对这一册跑一遍
  （`hooks.finished`；`GUJI_AUTO_BACKFILL=0` 临时关）。只改本机的库，随下一次 `guji db sync` 推上去。
- 手动：`guji glyph-db backfill --books 001,002 [--apply]`（不加 `--apply` 只报告）。

用法、数字与边界见 `doc/01-粗校/开书/放行格回库.md`。
"""
from __future__ import annotations

import collections
import datetime
import json
import sqlite3
from pathlib import Path

CHANNELS = ("rare_ref", "witness3")
CAP = 3
STEAL_CELLS_MAX = 8000     # 抢首位核验每册最多拿多少已放行格去模拟（0＝不限）
INK_MIN = 0.03
TRIES = 3          # 每个空位最多试几格（核验不过就换下一格）


def apply_problem(ws_dir: Path | str | None = None) -> str | None:
    """入库前核本机能不能安全推上中心库（2026-11-18，全唐文开 auto_backfill 前查的洞）。有问题返回说明。

    - ``GUJI_GLYPH_DB`` 指着别的书的库（借库跑批）：回库会写进那个库；
    - 本机是部分副本（``db pull --exclude``）：回库只留在本机，``db sync`` 推不上去；
    - glyph.db 比数据目录的字形账本旧（``db pull --no-rebuild``）：之后导出会用旧库盖掉账本、删别人新加的刻例。
    不是中心库工作区（没有 ``.central.json``）的不查。"""
    from .._cv import central_marker, workspace_root
    from ..datastore.workcopy import GLYPH_DB_STALE, data_dir, read_state
    from .central_glyph import foreign_glyph_db
    ws = Path(ws_dir) if ws_dir else Path(workspace_root())
    if not central_marker(ws):
        return None
    bad = foreign_glyph_db(ws)
    if bad:
        return bad
    st = read_state(data_dir(ws)) or {}
    if st.get("exclude"):
        return (f"本机是部分副本（pull 时排除了 {st['exclude']}），回库推不上中心库；到有完整副本的机器上 "
                f"`guji db pull` 后再 `guji glyph-db backfill --books … --apply`")
    if st.get(GLYPH_DB_STALE):
        return "本机 glyph.db 比字形账本旧（上次 pull 带了 --no-rebuild）：先 `guji db sync` 或 `guji db pull` 让它重建再回库"
    return None


def config(ws_dir: Path | str | None) -> dict | None:
    """`workspace.yaml` 的 `glyph_lib.auto_backfill`：false → None（关）；没写或 true → 缺省参数（缺省开）；
    写成对象可改 `channels`、`cap`、`steal_check`（抢首位核验，缺省开）、`steal_cells_max`（每册回放格数上限，0＝不限）。"""
    import yaml
    y = Path(ws_dir or ".") / "workspace.yaml"
    cfg = (yaml.safe_load(y.read_text(encoding="utf-8")) or {}) if y.exists() else {}
    v = (cfg.get("glyph_lib") or {}).get("auto_backfill", True)
    if v is None:
        v = True
    if v is False:
        return None
    v = v if isinstance(v, dict) else {}
    extra = set(v) - {"channels", "cap", "steal_check", "steal_cells_max"}
    if extra:
        raise SystemExit(f"glyph_lib.auto_backfill 只认 channels、cap、steal_check、steal_cells_max，不认 {sorted(extra)}")
    out = {"channels": tuple(v.get("channels") or CHANNELS), "cap": int(v.get("cap") or CAP)}
    if "steal_check" in v:
        out["steal_check"] = bool(v["steal_check"])
    if "steal_cells_max" in v:
        out["steal_cells_max"] = int(v["steal_cells_max"] or 0)
    return out


def lib_state(db_path: Path | str) -> dict:
    """现库的四样：在库实例、撤过的实例、各字现有刻例数、总数。

    刻例数要连 `instances` 数：撤库不删 `exemplars` 的行，只数 `exemplars` 会把撤掉的也算进去。
    **借来的刻例不算**（`borrowed` 表）：借库的书（新书冷启动）库里装着被借那本书的几万例，把它们算成「已有例」，
    本书一例都没有的字也会被当成不缺例而永远不补（脉经 11-18：本书 570 个字头，连借库数是 4,336 个）。"""
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as c:
        has_borrowed = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='borrowed'").fetchone()
        own = " WHERE e.instance_id NOT IN (SELECT instance_id FROM borrowed)" if has_borrowed else ""
        return {
            "in_lib": {r[0] for r in c.execute("SELECT instance_id FROM admissions")},
            "evicted": {r[0] for r in c.execute("SELECT instance_id FROM evictions")},
            "counts": collections.Counter(r[0] for r in c.execute(
                "SELECT g.char FROM exemplars e JOIN glyphs g USING(glyph_id) "
                "JOIN instances i ON i.instance_id = e.instance_id" + own)),
        }


def select(cells: dict[str, dict], state: dict, human_keys: set[str], *,
           channels=CHANNELS, cap: int = CAP) -> tuple[dict[str, list[str]], collections.Counter]:
    """从一批 `seed_admit` 格记录（格键 → 记录）里选候选：字 → 按覆盖度从高到低的格键。纯函数。"""
    stat: collections.Counter = collections.Counter()
    cand: dict[str, list] = collections.defaultdict(list)
    for k, r in cells.items():
        if not r.get("admit"):
            continue
        stat["放行格"] += 1
        if r.get("channel") not in channels:
            continue
        ch = r.get("char") or ""
        if len(ch) != 1 or ord(ch) < 0x2E80:
            stat["不是单个汉字"] += 1
            continue
        if state["counts"][ch] >= cap:
            continue
        stat["缺例字的放行格"] += 1
        iid = f"v2:{k}"
        if iid in state["in_lib"]:
            stat["已在库"] += 1
        elif k in human_keys:
            stat["已有人裁"] += 1
        elif iid in state["evicted"]:
            stat["曾撤过库"] += 1
        else:
            cand[ch].append((-float((r.get("evidence") or {}).get("cov") or 0), k))
    return {ch: [k for _n, k in sorted(xs)] for ch, xs in cand.items()}, stat


def _seed_cells(root: Path, book: str, step: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in sorted((root / book / step).glob("p*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pm = d[next(iter(d))]
        for col in (pm.get("columns") or pm.get("char_index", {}).get("columns") or []):
            for r in col.get("chars") or []:
                out[r["id"]] = r
    return out


class Verifier:
    """字体模板核验：库里实际会存的图（canonical）过字体模型，模板首位＝放行字才算过。"""

    def __init__(self):
        import numpy as np
        from .._cv import clustering_cnn_candidates as cc
        from .._cv import load_current
        pk = load_current()
        m = np.asarray(pk.mat, dtype=np.float32)
        self.mat = m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)
        self.names = list(pk.chars)
        self.cnn = cc.CnnCandidates()
        self.np = np

    def check(self, bin_img, ch: str) -> dict:
        from .._cv import normalize_patch, to_canonical
        np = self.np
        x = normalize_patch(to_canonical(bin_img))
        q = np.asarray(self.cnn.embed([x]), dtype=np.float32)[0]
        sc = self.mat @ (q / (np.linalg.norm(q) + 1e-9))
        o = np.argsort(-sc)[:2]
        ink = float(x.mean())
        top, second = self.names[int(o[0])], self.names[int(o[1])]
        return {"ok": top == ch and ink > INK_MIN, "tpl_top1": top, "tpl_top2": second,
                "tpl_margin": round(float(sc[o[0]] - sc[o[1]]), 4), "ink": round(ink, 4)}


def _knn_params(ctx) -> dict:
    """这一册 `glyph_match` 的 kNN 参数（探针要和 5a 同一口径）；取不到用 cv 缺省。"""
    try:
        p = ctx.params_for(ctx.pipeline.step("glyph_match"))
        return {"knn_k": int(p.knn_k), "per_char": int(p.knn_per_char), "per_char_top": int(p.knn_per_char_top)}
    except Exception:      # noqa: BLE001
        return {"knn_k": 10, "per_char": 0, "per_char_top": 0}


def _norm(bin_img):
    """字块二值图 → 归一图，与入库存图、`Verifier.check` 同一口径。"""
    from .._cv import normalize_patch, to_canonical
    return normalize_patch(to_canonical(bin_img))


def steal_drop(sim: dict, new_chars: set[str]) -> dict[str, list[str]]:
    """回库模拟结果 → 该拦下的新字：抢了已放行格的库首位（harm）、又没救回任何格（help）的。字 → 被抢的格键。纯函数。"""
    harm, helped = sim.get("harm") or {}, sim.get("help") or {}
    return {ch: list(keys) for ch, keys in harm.items() if ch in new_chars and keys and not helped.get(ch)}


def steal_gate(book: str, book_picks: list, sa: dict, cs: dict, ctx, dbp, *, cells_max: int = STEAL_CELLS_MAX,
               probe_cls=None, say=None) -> tuple[dict[str, list[str]], dict]:
    """抢首位核验（2026-11-18，史記 r80）：把这一册核验过的候选整批加进库做模拟，看本册已放行格谁的库首位被抢。

    返回（该拦下的字 → 被抢的格键，统计）。cv 太旧（没有 `BackfillProbe`）时不闸，统计里记 `skipped`。
    已放行格超过 `cells_max` 时等距抽样（记 `sampled`）；每格要取字块图，量大，所以设上限。"""
    import time
    import cv2
    import numpy as np
    from .._cv import binarize_page
    t0 = time.monotonic()
    info: dict = {"book": book, "new": len(book_picks)}
    if probe_cls is None:
        try:
            from .._cv import BackfillProbe as probe_cls
        except Exception:      # noqa: BLE001 —— 装的 cv 早于 #1679
            info["skipped"] = "装的 cv 没有 BackfillProbe（要含 cv #1679 的版本），这一册没做抢首位核验、候选照常进库"
            if say:
                say("  ⚠ " + info["skipped"])
            return {}, info
    new_keys = {k for _ch, k, *_ in book_picks}
    new_items = [(k, ch, _norm(cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_GRAYSCALE)))
                 for ch, k, png, _m, _v in book_picks]
    keys = sorted(k for k, r in sa.items() if r.get("admit") and k not in new_keys
                  and len(r.get("char") or "") == 1 and (cs.get(k) or {}).get("patch_key"))
    if cells_max and len(keys) > cells_max:
        step = len(keys) / cells_max
        keys = [keys[int(i * step)] for i in range(cells_max)]
        info["sampled"] = True
    cells = []
    for k in keys:
        try:
            img = ctx.image("char_patch", cs[k]["patch_key"])
        except Exception:      # noqa: BLE001
            img = None
        if img is not None:
            cells.append((k, sa[k]["char"], _norm(binarize_page(img, edge_margin=0))))
    t1 = time.monotonic()
    probe = probe_cls(str(dbp), **_knn_params(ctx))
    sim = probe.steal_check(new_items, cells)
    drop = steal_drop(sim, {ch for ch, *_ in book_picks})
    info.update(cells=sim.get("cells", len(cells)), checked=sim.get("checked"),
                harm={c: len(v) for c, v in (sim.get("harm") or {}).items()},
                help={c: len(v) for c, v in (sim.get("help") or {}).items()}, dropped=sorted(drop),
                img_s=round(t1 - t0, 1), sim_s=round(time.monotonic() - t1, 1))
    return drop, info


def run(books: list[str], *, apply: bool = False, batch: str | None = None,
        channels=CHANNELS, cap: int = CAP, verifier=None, log=None, report: str | None = None,
        steal_check: bool = True, steal_cells_max: int = STEAL_CELLS_MAX, probe_cls=None) -> dict:
    """对 `books` 各册跑一遍选格、核验、抢首位核验、（`apply` 时）入库。返回报告。"""
    import cv2
    from .._cv import (EventLog, EventTarget, GlyphDB, ImageCache, ProductStore, RunContext,
                       binarize_page, enrich_events, export_store, glyph_db_path, glyph_store_path,
                       load_book, make_event, products_root)
    say = log or (lambda *_: None)
    if apply:
        bad = apply_problem()
        if bad:
            raise SystemExit("✗ 放行格回库没入库：" + bad)
    dbp, root, elog = glyph_db_path(), products_root(), EventLog()
    state = lib_state(dbp)
    human = {e.target.key for e in elog.iter_all() if e.actor == "user"}
    n_before = sum(state["counts"].values())
    chars_before = sum(1 for v in state["counts"].values() if v > 0)
    stat: collections.Counter = collections.Counter()
    picks, rejected, steal = [], [], []
    blocked: set[str] = set()      # 抢首位核验拦下的字：同一次跑后面的册不再选
    cache = ImageCache()
    for b in books:
        sa = _seed_cells(root, b, "seed_admit")
        cs = _seed_cells(root, b, "cell_shrink")
        cand, st = select(sa, state, human, channels=channels, cap=cap)
        stat.update(st)
        for ch in blocked & set(cand):
            stat["前册已拦"] += len(cand.pop(ch))
        if not cand:
            continue
        verifier = verifier or Verifier()
        ctx = RunContext(load_book(b), ProductStore(), cache, log=lambda *_: None)
        n0 = len(picks)
        for ch, keys in sorted(cand.items()):
            room = cap - state["counts"][ch]
            for k in keys[:room * TRIES]:
                if room <= 0:
                    break
                pk = (cs.get(k) or {}).get("patch_key")
                try:
                    img = ctx.image("char_patch", pk) if pk else None
                except Exception:      # noqa: BLE001 —— 原图或缓存取不到，这格跳过
                    img = None
                if img is None:
                    stat["取不到字块"] += 1
                    continue
                bin_img = binarize_page(img, edge_margin=0)
                v = verifier.check(bin_img, ch)
                r = sa[k]
                ev = r.get("evidence") or {}
                meta = {"channel": r.get("channel"), "verdict": ev.get("verdict"), "cov": ev.get("cov"),
                        "patch_key": pk}
                if not v.pop("ok"):
                    stat["核验不过"] += 1
                    rejected.append({"key": k, "char": ch, **meta, **v})
                    continue
                picks.append((ch, k, cv2.imencode(".png", bin_img)[1].tobytes(), meta, v))
                state["counts"][ch] += 1
                state["in_lib"].add(f"v2:{k}")
                room -= 1
        if steal_check and len(picks) > n0:
            # 抢首位核验：这一册的候选整批模拟进库，只害不帮的字整字不进（同一字的几格一起退），等人裁
            try:
                drop, info = steal_gate(b, picks[n0:], sa, cs, ctx, dbp, cells_max=steal_cells_max,
                                        probe_cls=probe_cls, say=say)
            except Exception as e:      # noqa: BLE001 —— 核验自己出错不挡回库，报出来
                drop, info = {}, {"book": b, "error": f"{type(e).__name__}: {e}"}
                say(f"  ⚠ {b}: 抢首位核验出错，这一册没闸：{info['error']}")
            steal.append(info)
            blocked |= set(drop)
            if drop:
                kept = []
                for ch, k, png, meta, v in picks[n0:]:
                    if ch in drop:
                        stat["抢常用字首位"] += 1
                        rejected.append({"key": k, "char": ch, **meta, **v, "reason": "near_common",
                                         "harm": drop[ch][:20]})
                        state["counts"][ch] -= 1
                        state["in_lib"].discard(f"v2:{k}")
                    else:
                        kept.append((ch, k, png, meta, v))
                picks[n0:] = kept
        say(f"  {b}: 候选字 {len(cand)}，累计可入库 {len(picks)} 格")
    batch = batch or f"auto-backfill-{datetime.date.today():%Y%m%d}"
    rep = {"db": str(dbp), "books": books, "batch": batch, "apply": apply, "channels": list(channels), "cap": cap,
           "stat": dict(stat), "picks": len(picks), "chars": len({p[0] for p in picks}), "steal_check": steal if steal_check else None,
           "lib_before": {"instances": n_before, "chars": chars_before},
           "rejected": rejected, "picked": [{"key": k, "char": ch, **meta, **v} for ch, k, _p, meta, v in picks]}
    if apply and picks:
        base = elog.latest_seq(batch)
        evs = []
        for i, (ch, k, png, meta, v) in enumerate(picks, 1):
            bk, pg, col, slot = k.split(":")
            slot = slot.rstrip("ab")          # 半格（19a／19b）：格号取数字部分，键仍带后缀（同库里现有刻例）
            evs.append(make_event(batch, base + i, "confirm",
                                  EventTarget(step="seed_admit", unit="cell", key=k, book=bk,
                                              page=int(pg), col=int(col), slot=int(slot)),
                                  {"v": "confirm", "shape": ch, "source": "auto", "backfill": True, **meta,
                                   "verify": v},
                                  actor="model"))
        # 先补锚（带产物页表的 source_rev）、先写事件日志，再进库：换过图源的册（yaml 有 source_rev）
        # 不带锚的事件会被日志拒写，原先这时库里已进了刻例、却没有事件，重放会丢（史记 36、42 册，11-18）
        enrich_events(evs, store=ProductStore())
        rep["events"] = elog.append(evs)
        db = GlyphDB(dbp)
        n = 0
        for e, (ch, k, png, meta, v) in zip(evs, picks):
            n += bool(db.admit_instance(
                f"v2:{k}", ch, png, provenance="auto", shape=ch,
                evidence={"event": e.id, "batch": batch, "source": "auto", "backfill": True,
                          **{x: meta[x] for x in ("channel", "verdict", "cov")}, "verify": v},
                page=k.split(":")[1], col=e.target.col, idx=e.target.slot))
        rep["admitted"] = n
        # 已直接进库，给字形库消费者记账；`db sync` 取了库里的字形库时会删掉这笔账、从事件重放（`_admit_backfills`）
        elog.mark_consumed("glyphdb_admit", evs, note="放行格回库：入库时已直接进库")
        rep["export"] = export_store(db, glyph_store_path())
        db.close()
        after = lib_state(dbp)["counts"]
        rep["lib_after"] = {"instances": sum(after.values()), "chars": sum(1 for x in after.values() if x > 0)}
    if report:
        Path(report).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep


def summary(rep: dict) -> str:
    s = rep["stat"]
    line = (f"缺例字的放行格 {s.get('缺例字的放行格', 0)}，核验过 {rep['picks']} 格（{rep['chars']} 字），"
            f"核验不过 {s.get('核验不过', 0)}，取不到字块 {s.get('取不到字块', 0)}")
    if s.get("抢常用字首位"):
        line += f"，会抢常用字首位没进 {s['抢常用字首位']} 格"
    sc = rep.get("steal_check")
    bad = [x["book"] for x in sc or [] if x.get("skipped") or x.get("error")]
    if sc is None:
        line += "（⚠ 抢首位核验已关）"
    elif bad:
        line += f"（⚠ {','.join(bad)} 没做抢首位核验，候选照常进库：{(sc[0].get('skipped') or sc[0].get('error') or '')[:60]}）"
    elif sc:
        line += f"，抢首位核验 {sum(x.get('img_s', 0) + x.get('sim_s', 0) for x in sc):.0f} 秒"
    if "admitted" in rep:
        line += (f"；已入库 {rep['admitted']} 格，库 {rep['lib_before']['instances']}→{rep['lib_after']['instances']} 例、"
                 f"{rep['lib_before']['chars']}→{rep['lib_after']['chars']} 字，批次 {rep['batch']}")
    return line


def auto_backfill(args, eng, steps: list[str]) -> None:
    """`hooks.finished`：整册跑完、`workspace.yaml` 没把 `glyph_lib.auto_backfill` 关掉 → 对这一册回库。

    只在 `--pages all` 且这次跑到了 `seed_admit` 时做；失败只提醒，不改跑批的返回码。"""
    import os
    if os.environ.get("GUJI_AUTO_BACKFILL", "1") == "0":
        return
    if str(getattr(args, "pages", "")) != "all" or "seed_admit" not in steps:
        return
    book = eng.book.id
    try:
        from .._cv import workspace_root
        cfg = config(workspace_root())
        if cfg is None:
            return
        rep = run([book], apply=True, **cfg)
        print(f"  ✓ 放行格回库 {book}：{summary(rep)}"
              + ("（随下一次 guji db sync 推上中心库）" if rep.get("admitted") else ""))
    except BaseException as e:     # noqa: BLE001 —— 回库失败不算跑批失败（含配置写错的 SystemExit）
        if isinstance(e, KeyboardInterrupt):
            raise
        print(f"  ⚠ 放行格回库失败（{e}）：手动 guji glyph-db backfill --books {book} --apply")
