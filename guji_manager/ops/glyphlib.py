"""`guji glyphlib build`：从一本书的字形库精选刻例，出共享刻例库的新版本（共享方案 3.2 节，S5）。

共享刻例库每版一个中心库只读工作区 ``glyphlib-<族>-v<N>``，里面只有 ``workspace.yaml``、
``output/glyph_store/`` 和记升格来源的 ``feedback/promote.jsonl``。刻例图逐字节照搬来源书的
（R2 里按 sha 存，同一张图不另存一份）；实例 id、来源 id 加上来源工作区前缀，免得和借它的书撞号。

选哪些刻例（门槛由 sheldon 定，见方案第六节）：
- 来源书人裁过的实例（``label_status='human'``），且在至少 ``min_batches`` 个不同批次被确认过
  （``confirm`` 事件 ``v=confirm`` 且字形与库里一致，或 ``cell_review`` 选了这个字）；
- 体检（``glyph_audit``）没标过异常，不是近似字（``approx_labels``）；
- 每个字最多 ``per_char`` 张，确认批次多的优先，同数按实例 id。

多来源（2026-11-28，GM2，文渊阁组库 glyphlib-wyg）：``build`` 可给多本来源书，实例 id 各加各的来源前缀；
``with_auto`` 另收来源书的**放行格回库**例（``admissions.provenance='auto'``、证据带 ``backfill`` 与 ``verify``），出库前
再过一遍字体模板核验（首位＝字才收），``label_status`` 保留 ``auto``、不冒充人裁；``diverse`` 时每字先人裁后回库，
按 5a 底座向量挑互相不像的（同 ``lib_backfill.pick_diverse``）。``suspect`` 给出要标记的来源实例（如史記 11-26 回库
疑贴错图那批），标记写进入库证据与升格记录，``drop_suspect`` 时不收。

这里只读字形库真源的文本文件（不要 glyph.db），出的库再 ``rebuild_from_store`` 一遍核对能装、
``export_store`` 导出规范格式。推进中心库由 ``publish`` 以升级脚本身份做（``push(shared_writer=True)``）。
"""
from __future__ import annotations

import datetime
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

GS = "output/glyph_store"


def _read(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def _safe(iid: str) -> str:
    from .._cv import _safe as s
    return s(iid)


def cell_key(iid: str) -> str:
    """实例 id → 人裁事件里的格号：``v2:vol01:57:8:2`` → ``vol01:57:8:2``；``vol01:10:4:17`` 原样。"""
    p = iid.split(":")
    return ":".join(p[1:]) if len(p) == 5 else iid


def _confirm_batches(events_dir: Path) -> tuple[dict[tuple[str, str], set[str]], set[str]]:
    """人裁事件 → ({(格号, 字): 确认过的批次}, 体检标过异常的实例 id)。"""
    conf: dict[tuple[str, str], set[str]] = defaultdict(set)
    bad: set[str] = set()
    from .._cv import iter_event_dicts
    for e in iter_event_dicts(Path(events_dir)):          # 换图源的页表 rev 判据在这里一并生效
        p = e.get("payload") or {}
        k = (e.get("target") or {}).get("key")
        kind = e.get("kind")
        if kind == "confirm" and p.get("v") == "confirm" and p.get("shape"):
            conf[(k, p["shape"])].add(str(e.get("batch")))
        elif kind == "cell_review" and p.get("verdict") == "pick" and p.get("picked"):
            conf[(k, p["picked"])].add(str(e.get("batch")))
        elif kind == "glyph_audit":
            iid = p.get("instance_id") or k
            if iid and (p.get("v") != "ok" or p.get("flags")):
                bad.add(str(iid))
    return conf, bad


def select(store: Path, events_dir: Path, *, min_batches: int = 2, per_char: int = 3) -> tuple[list[dict], dict]:
    """按门槛从字形库真源 ``store`` 里挑刻例。返回 (选中的 [{instance_id, char, batches}], 统计)。"""
    store = Path(store)
    conf, bad = _confirm_batches(events_dir)
    approx = {r["instance_id"] for r in _read(store / "approx_labels.jsonl")}
    shape = {r["instance_id"]: r["char"] for r in _read(store / "exemplars.jsonl")}
    stats: Counter = Counter()
    cands: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for f in sorted((store / "instances").glob("*.jsonl")):
        for r in _read(f):
            iid = r["instance_id"]
            if r.get("label_status") != "human":
                continue
            stats["human"] += 1
            ch = shape.get(iid)
            if ch is None:
                stats["no_exemplar"] += 1
                continue
            if iid in bad or iid in approx:
                stats["audit_or_approx"] += 1
                continue
            n = len(conf.get((cell_key(iid), ch), ()))
            if n < min_batches:
                stats["too_few_confirms"] += 1
                continue
            cands[ch].append((n, iid))
    picked = []
    for ch in sorted(cands):
        for n, iid in sorted(cands[ch], key=lambda x: (-x[0], x[1]))[:per_char]:
            picked.append({"instance_id": iid, "char": ch, "batches": n})
    stats.update(passed=sum(len(v) for v in cands.values()), picked=len(picked), chars=len(cands))
    return picked, dict(stats)


def _evidence(r: dict) -> dict:
    ev = r.get("evidence")
    if isinstance(ev, str):
        try:
            ev = json.loads(ev)
        except ValueError:
            ev = None
    return ev if isinstance(ev, dict) else {}


def select_auto(store: Path, events_dir: Path, *, skip: set[str] = frozenset()) -> tuple[list[dict], dict]:
    """来源书的放行格回库例：``admissions.provenance='auto'``、证据带 ``backfill`` 与 ``verify``（入库时过了字体核验），
    实例还在、标签仍是 auto，体检没标异常、不是近似字、没被撤。``skip`` 是已作人裁候选的实例。返回 ([{instance_id, char, batch}], 统计)。"""
    store = Path(store)
    _conf, bad = _confirm_batches(events_dir)
    approx = {r["instance_id"] for r in _read(store / "approx_labels.jsonl")}
    evicted = {r["instance_id"] for r in _read(store / "evictions.jsonl")}
    shape = {r["instance_id"]: r["char"] for r in _read(store / "exemplars.jsonl")}
    live = {}
    for f in sorted((store / "instances").glob("*.jsonl")):
        for r in _read(f):
            live[r["instance_id"]] = r.get("label_status")
    stats: Counter = Counter()
    out = []
    for r in _read(store / "admissions.jsonl"):
        if r.get("provenance") != "auto":
            continue
        stats["auto"] += 1
        iid = r["instance_id"]
        ev = _evidence(r)
        if not (ev.get("backfill") and ev.get("verify")):
            stats["not_verified_backfill"] += 1
            continue
        if iid in skip or live.get(iid) == "human":
            stats["human_too"] += 1
            continue
        if iid not in live or iid in evicted:
            stats["gone_or_evicted"] += 1
            continue
        if iid in bad or iid in approx:
            stats["audit_or_approx"] += 1
            continue
        ch = shape.get(iid)
        if ch is None or ch != r.get("char"):
            stats["no_exemplar_or_relabeled"] += 1
            continue
        out.append({"instance_id": iid, "char": ch, "batches": 0, "auto": True, "batch": ev.get("batch")})
    stats["passed"] = len(out)
    return out, dict(stats)


def suspect_of(store: Path, *, ids: set[str] = frozenset(), since: str | None = None,
               chars: str = "") -> dict[str, str]:
    """要标记的来源实例 → 原因：``ids`` 里点名的；入库时间（``admissions.admitted_at``）在 ``since`` 当天及以后的；
    字头在 ``chars`` 里的（如码位分歧待定的字，CV3 11-28：不在 build 里静默改码，没定的先不进）。"""
    out = {i: "点名" for i in ids}
    if chars:
        for r in _read(Path(store) / "exemplars.jsonl"):
            if r["char"] in chars:
                out.setdefault(r["instance_id"], f"字头 {r['char']} 待定")
    if since:
        for r in _read(Path(store) / "admissions.jsonl"):
            if str(r.get("admitted_at") or "")[:10] >= since:
                out.setdefault(r["instance_id"], f"入库于 {since} 及以后")
    return out


def pick_per_char(picked: list[dict], per_char: int, *, emb_of=None, dup_sim: float | None = None) -> tuple[list[dict], Counter]:
    """多来源合并后每字最多 ``per_char`` 张：人裁在前（确认批次多的优先，同数按来源给的先后），回库在后。给了 ``emb_of``（[png 路径] → 向量）
    就按 ``lib_backfill.pick_diverse`` 挑互相不像的（人裁先挑完再挑回库，与已选的太像的算重复不收）。"""
    from .lib_backfill import DUP_SIM, pick_diverse
    by: dict[str, list[dict]] = defaultdict(list)
    for p in picked:
        by[p["char"]].append(p)
    out: list[dict] = []
    st: Counter = Counter()
    for ch in sorted(by):
        xs = sorted(by[ch], key=lambda p: (bool(p.get("auto")), -int(p.get("batches") or 0), int(p.get("_ord") or 0),
                                           p["instance_id"]))
        if emb_of is None or len(xs) <= 1:
            got = xs[:per_char]
        else:
            vecs = emb_of(xs)
            if vecs is None:
                got = xs[:per_char]
            else:
                chosen, dropped = pick_diverse([], [(v, bool(p.get("auto"))) for v, p in zip(vecs, xs)], per_char,
                                               n_exist=0, thin=per_char, dup_sim=dup_sim or DUP_SIM, far_sim=-1.0)
                got = [xs[i] for i, _m in chosen]
                st["dup"] += sum(1 for r, _ in dropped.values() if r == "dup")
        st["over_cap"] += len(xs) - len(got)
        out += got
    return out, st


def write_store(src_store: Path, picked: list[dict], out_store: Path, *, src_ws: str, edition: str) -> dict:
    """把选中的刻例写成一个字形库真源（未规范化；``build`` 再装库、导出一遍）。单来源的老接口。"""
    return write_store_multi([(Path(src_store), picked, src_ws)], out_store, edition=edition)


def write_store_multi(parts: list[tuple[Path, list[dict], str]], out_store: Path, *, edition: str) -> dict:
    """多来源：``parts`` 是 [(来源字形库真源, 选中的刻例, 来源工作区名)]，实例 id 加 ``<来源>:``、来源 id 加 ``<来源>.``。
    选中项可带 ``auto``（回库例，标签保留 auto）、``suspect``（标记原因，写进入库证据）。"""
    from .._cv import K_MIN
    out_store = Path(out_store)
    if out_store.exists():
        shutil.rmtree(out_store)
    (out_store / "instances").mkdir(parents=True)
    (out_store / "patches").mkdir()
    (out_store / "events").mkdir()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    sources, glyph_rows, exemplars, admissions = [], {}, [], []
    n_by: Counter = Counter()
    used_all: list[str] = []
    for src_store, picked, src_ws in parts:
        src_store = Path(src_store)
        sel = {p["instance_id"]: p for p in picked}
        new = lambda iid, w=src_ws: f"{w}:{iid}"                       # noqa: E731
        new_src = lambda sid, w=src_ws: f"{w}.{sid}"                   # noqa: E731
        used_src: set[str] = set()
        for f in sorted((src_store / "instances").glob("*.jsonl")):
            rows = []
            for r in _read(f):
                if r["instance_id"] not in sel:
                    continue
                png = src_store / "patches" / f"{_safe(r['instance_id'])}.png"
                if not png.exists():
                    raise FileNotFoundError(f"来源库缺刻例图 {png}")
                shutil.copyfile(png, out_store / "patches" / f"{_safe(new(r['instance_id']))}.png")
                used_src.add(r["source_id"])
                rows.append({**r, "instance_id": new(r["instance_id"]), "source_id": new_src(r["source_id"])})
            for sid in {r["source_id"] for r in rows}:
                with open(out_store / "instances" / f"{sid}.jsonl", "a", encoding="utf-8") as fh:
                    for r in sorted((x for x in rows if x["source_id"] == sid), key=lambda x: x["instance_id"]):
                        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
        src_rows = {r["source_id"]: r for r in _read(src_store / "sources.jsonl")}
        for sid in sorted(used_src):
            # 来源库可能没有这条来源行：借库的书第一次回库时，同名来源 v2 是借来那本的，本书真源里就没写（汉书，11-28）。
            # 没有来源行的实例装库时会被丢掉，所以补一条最小的
            r = src_rows.get(sid) or {"source_id": sid, "kind": "woodblock", "created_at": now}
            sources.append({**r, "source_id": new_src(sid), "edition_tag": edition,
                            "notes": f"共享刻例库 {edition}：从 {src_ws} 的来源 {sid} 精选。"
                                     + (f"原注：{r['notes']}" if r.get("notes") else "")})
        used_all += [new_src(x) for x in used_src]
        n_by.update(p["char"] for p in picked)
        for r in _read(src_store / "glyphs.jsonl"):
            if r["char"] in {p["char"] for p in picked}:
                g = glyph_rows.setdefault(r["char"], {})
                for k in ("ids", "semantic", "unicode_cp"):
                    if g.get(k) is None and r.get(k) is not None:
                        g[k] = r[k]
        exemplars += [{"added_at": now, "char": p["char"], "edition_tag": edition,
                       "instance_id": new(p["instance_id"]), "role": "seed"} for p in picked]
        adm = {r["instance_id"]: r for r in _read(src_store / "admissions.jsonl")}
        for p in picked:
            ev = {"promoted_from": {"ws": src_ws, "instance_id": p["instance_id"]},
                  "confirm_batches": p["batches"],
                  "src_provenance": adm.get(p["instance_id"], {}).get("provenance")}
            if p.get("auto"):
                ev["src_batch"] = p.get("batch")
                ev["verify"] = p.get("verify")
            if p.get("suspect"):
                ev["suspect"] = p["suspect"]
            admissions.append({"admitted_at": now, "char": adm.get(p["instance_id"], {}).get("char", p["char"]),
                               "evidence": json.dumps(ev, ensure_ascii=False, sort_keys=True),
                               "instance_id": new(p["instance_id"]), "provenance": "promote"})

    def dump(name: str, recs: list[dict]) -> None:
        with open(out_store / name, "w", encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    dump("sources.jsonl", sorted(sources, key=lambda r: r["source_id"]))
    dump("glyphs.jsonl", [{**{k: glyph_rows.get(ch, {}).get(k) for k in ("ids", "semantic", "unicode_cp")},
                           "char": ch, "edition_tag": edition, "n_confirmed": n,
                           "status": "stable" if n >= K_MIN else "sparse", "updated_at": now}
                          for ch, n in sorted(n_by.items())])
    dump("exemplars.jsonl", sorted(exemplars, key=lambda x: (x["char"], x["instance_id"])))
    dump("admissions.jsonl", sorted(admissions, key=lambda x: x["instance_id"]))
    dump("meta.jsonl", [{"key": "book_edition", "value": edition}])
    n_inst = sum(len(p) for _s, p, _w in parts)
    return {"instances": n_inst, "chars": len(n_by), "sources": sorted(used_all)}


def promote_events(picked: list[dict], *, src_ws: str, lib: str, actor: str | None, note: str,
                   thresholds: dict) -> list[dict]:
    """升格记账（方案 4.1 节）：一条刻例一行，进目标工作区的 ``feedback/promote.jsonl``。"""
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    batch = f"promote-{lib}"
    out = []
    for i, p in enumerate(picked, 1):
        w = p.get("src_ws") or src_ws
        pl = {"from_ws": w, "from_instance": p["instance_id"], "char": p["char"],
              "confirm_batches": p["batches"], "thresholds": thresholds, "note": note}
        if p.get("auto"):
            pl["auto"] = True
        if p.get("suspect"):
            pl["suspect"] = p["suspect"]
        out.append({"id": f"evt_{batch}_{i:06d}", "batch": batch, "seq": i, "kind": "promote", "actor": actor,
                    "ts": ts, "payload": pl, "target": {"book": None, "key": f"{w}:{p['instance_id']}", "unit": "glyph"}})
    return out


def lib_workdir(name: str, branch: str = "main") -> Path:
    """升级脚本用的共享刻例库工作区目录（只有 ``workspace.yaml`` 和标记；数据在数据目录）。"""
    from .._cv import data_home
    from .._cv import SHARED_PREFIX
    if not name.startswith(SHARED_PREFIX):
        raise SystemExit(f"共享刻例库的工作区名要以 {SHARED_PREFIX} 开头（如 glyphlib-qkp-v1），收到 {name}")
    d = data_home() / branch.replace("/", "__") / ".shared" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "workspace.yaml").write_text(f"id: {name}\n", encoding="utf-8")
    (d / ".central.json").write_text(json.dumps({"ws": name, "branch": branch}) + "\n", encoding="utf-8")
    return d


def edition_of(name: str) -> str:
    """``glyphlib-qkp-v1`` → ``glyphlib-qkp``：字体族的 edition，跨版本不变（借哪版都按同一个族匹配）。"""
    base, _, v = name.rpartition("-v")
    return base if base and v.isdigit() else name


class _Embedder:
    """来源库图（canonical PNG）→ 5a 底座向量；回库例再过一遍字体模板核验。要 cv 的字体包与底座模型（``guji model fetch``）。"""

    def __init__(self):
        from .lib_backfill import Verifier
        self.v = Verifier()

    def emb(self, paths: list[Path]):
        z = self.v.embed_lib([Path(x).read_bytes() for x in paths])
        return z if len(z) == len(paths) else None

    def verify(self, path: Path, ch: str) -> dict:
        import cv2
        import numpy as np
        img = cv2.imdecode(np.frombuffer(Path(path).read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
        v = self.v.check(img, ch)
        v.pop("emb", None)
        return v


def build(src_ws_dir, name: str, *, min_batches: int = 2, per_char: int = 3, actor: str | None = None,
          note: str = "", branch: str = "main", gate_waive: str = "", with_auto: bool = False,
          diverse: bool = False, suspect: dict[str, dict] | None = None, drop_suspect: bool = False,
          embedder=None) -> dict:
    """出共享刻例库 ``name`` 到本机（``$GUJI_DATA_HOME/<分支>/<name>/``），不推。

    ``src_ws_dir`` 可以是一个或多个来源书工作区（多个时每书各自过门槛，再合起来每字最多 ``per_char`` 张）。
    ``with_auto``：True＝各来源都收回库例；给一组工作区名＝只收这几本的。
    ``suspect``：来源工作区名 → ``{"ids": 实例 id 集合, "since": "YYYY-MM-DD"}``，命中的标记，``drop_suspect`` 时不收。
    装好的库先过出版护栏（`ops/glyph_release_gate`），不过就拒出；``gate_waive`` 给理由可照出。"""
    from .._cv import GlyphDB, export_store, rebuild_from_store
    from .._cv import central_data_dir, central_marker, data_root
    dirs = [Path(src_ws_dir)] if isinstance(src_ws_dir, (str, Path)) else [Path(x) for x in src_ws_dir]
    srcs, stats_by, all_picks = [], {}, []
    emb = embedder if embedder is not None else (_Embedder() if (with_auto or diverse) else None)
    for d in dirs:
        m = central_marker(d)
        if not m:
            raise SystemExit(f"{d} 没迁到中心库；先 guji db migrate／pull")
        src_ws = str(m["ws"])
        root = data_root(d) or d
        store = root / GS
        picked, st = select(store, root / "feedback" / "events", min_batches=min_batches, per_char=10 ** 6)
        st = {"human": st}
        if with_auto is True or (with_auto and src_ws in with_auto):
            autos, sta = select_auto(store, root / "feedback" / "events", skip={p["instance_id"] for p in picked})
            ok, bad_v = [], 0
            for a in autos:          # 出库前再核一遍：库里存的那张图过字体模板，首位＝字才收
                v = emb.verify(store / "patches" / f"{_safe(a['instance_id'])}.png", a["char"])
                if v.get("ok"):
                    ok.append({**a, "verify": {k: v[k] for k in ("tpl_top1", "tpl_margin") if k in v}})
                else:
                    bad_v += 1
            sta["reverify_failed"] = bad_v
            st["auto"] = sta
            picked += ok
        sus = suspect_of(store, **(suspect or {}).get(src_ws, {})) if (suspect or {}).get(src_ws) else {}
        n_sus = 0
        keep = []
        for p in picked:
            p["src_ws"], p["_png"], p["_ord"] = src_ws, store / "patches" / f"{_safe(p['instance_id'])}.png", len(srcs)
            if p["instance_id"] in sus:
                p["suspect"] = sus[p["instance_id"]]
                n_sus += 1
                if drop_suspect:
                    continue
            keep.append(p)
        st["suspect"] = {"marked": n_sus, "dropped": n_sus if drop_suspect else 0}
        stats_by[src_ws] = st
        srcs.append((src_ws, store))
        all_picks += keep
    if not all_picks:
        raise SystemExit(f"按门槛一张刻例都没选出：{stats_by}")
    emb_of = (lambda xs: emb.emb([p["_png"] for p in xs])) if diverse else None
    final, cap = pick_per_char(all_picks, per_char, emb_of=emb_of)
    ws = lib_workdir(name, branch)
    data = central_data_dir(name, branch)
    tmp = data.parent / f".{name}.build.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    edition = edition_of(name)
    parts = [(store, [{k: v for k, v in p.items() if k not in ("_png", "_ord")} for p in final if p["src_ws"] == w], w)
             for w, store in srcs]
    info = write_store_multi([x for x in parts if x[1]], tmp / "raw", edition=edition)
    dbp = tmp / "check.sqlite"
    rebuild_from_store(tmp / "raw", dbp)                       # 装得进去才算数
    import sqlite3
    with sqlite3.connect(dbp) as c:
        n_db = c.execute("SELECT COUNT(*) FROM exemplars").fetchone()[0]
    if n_db != info["instances"]:
        raise SystemExit(f"出 {name}：选了 {info['instances']} 张，装库后只剩 {n_db} 张（来源行或图缺了），不出")
    from .._cv import glyph_release_gate_enforce as enforce
    gate = enforce(dbp, waive=gate_waive, what=f"出 {name}")
    db = GlyphDB(dbp)
    try:
        export_store(db, data / GS)
    finally:
        db.close()
    thresholds = {"min_confirm_batches": min_batches, "per_char": per_char, "audit_clean": True,
                  "no_approx": True, "with_auto": with_auto if isinstance(with_auto, bool) else sorted(with_auto), "diverse": diverse, "drop_suspect": drop_suspect}
    ev = data / "feedback" / "promote.jsonl"            # 不是人裁事件，不进 feedback/events/（规范 §9 F-8）
    ev.parent.mkdir(parents=True, exist_ok=True)
    clean = [{k: v for k, v in p.items() if k not in ("_png", "_ord")} for p in final]
    ev.write_text("".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n"
                          for e in promote_events(clean, src_ws=srcs[0][0], lib=name, actor=actor, note=note,
                                                  thresholds=thresholds)), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    by_src = Counter(p["src_ws"] for p in final)
    by_kind = Counter(("auto" if p.get("auto") else "human") for p in final)
    out = {"lib": name, "edition": edition, "from": [w for w, _ in srcs], "data_dir": str(data),
           "workspace_dir": str(ws), "thresholds": thresholds, "select": stats_by, "cap": dict(cap),
           "picked_by_source": dict(by_src), "picked_by_kind": dict(by_kind),
           "suspect_in_lib": sum(1 for p in final if p.get("suspect")), "gate": gate, **info}
    if len(dirs) == 1:
        out["from"] = srcs[0][0]
    return out


def publish(conn, name: str, *, actor: str | None = None, uploader=None, branch: str = "main",
            dry_run: bool = False) -> dict:
    """把本机出好的 ``name`` 推进中心库（升级脚本身份；``glyphlib-*`` 只能写一次）。"""
    from .._cv import workcopy_push as push
    return push(conn, lib_workdir(name, branch), actor=actor, uploader=uploader, shared_writer=True,
                dry_run=dry_run)
