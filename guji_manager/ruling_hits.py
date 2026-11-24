"""AI 文意裁定命中核对：`guji rulings-hits`（A31 2026-11-20，流程慢痛点 K1）。

裁定（`feedback/rulings/`）按**窗口内容**取键（组＋前后各 20 字的哈希＋提示词版本），不按格号。
重放时 seed_admit 看到的窗口和写裁定时的不一样（邻格放行状态不同、整理本改了字），裁定就静默不命中：
全唐文 d1 有 15 格推了裁定仍待审，要等一整轮出包才知道。

本命令读一份产物（`--products <根>`，含 seed_admit），对每个**仍在问**（ask 还挂着）的格：
这格有裁定（按 `payload.cell`）却查不到 → 列为「未命中」，写出两边窗口。
`--rekey --batch <名>`：用产物里这格当时实际的窗口另写一条裁定（字、把握、模型照抄原裁定，why 前缀 rekey），
下一次重放即可命中。提示词版本不同的不改键（换版本本来就是要作废）。只读产物；--rekey 只追加裁定事件，推库照常 `guji db sync`。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def _rulings_by_cell(store) -> dict[str, dict]:
    """格号 → 这格最新一条文意裁定 payload（不含 src-2 私用码记录）。"""
    from ._cv import RULING_KIND
    from ._cv import replay_key
    out: dict[str, dict] = {}
    if not store.log.events_dir.exists():
        return out
    evs = [e for e in store.log.iter_all(raw=True) if e.kind == RULING_KIND]
    for e in sorted(evs, key=replay_key):
        p = e.payload or {}
        if p.get("cell") and p.get("ctx") and p.get("prompt_ver") != "src-2":
            out[p["cell"]] = p
    return out


def _hit(store, group: str, ver: str, left: str, right: str):
    """seed_admit 会不会命中这条窗口键：先精确键，cv 带版本等价表（`RulingStore.get_equiv`，cv #1830，
    `<feedback>/rulings/ver_equiv.yaml`）时再按等价版本查，不另写一套等价逻辑；旧 cv 没有 get_equiv 就只看精确键。"""
    return getattr(store, "get_equiv", store.get)(group, ver, left, right)


def check(products: Path, book: str, store) -> list[dict]:
    from ._cv import llm_questions_of_page, ruling_ctx_hash
    by_cell = _rulings_by_cell(store)
    rows = []
    for f in sorted((Path(products) / book / "seed_admit").glob("p*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        machine = {c.get("id"): c.get("char") for col in doc.get("seed_admit", doc).get("columns") or []
                   for c in col.get("chars") or []}
        ref: dict[str, str] = {}
        try:
            ar = json.loads((Path(products) / book / "align_ref" / f.name).read_text(encoding="utf-8")).get("align_ref", {})
            if ar.get("anchored", True) is not False:
                ref = {c["id"]: c.get("align_char") or "" for c in ar.get("chars") or [] if c.get("id")}
        except (OSError, ValueError):
            pass
        cands: dict[str, set[str]] = {}
        for col in doc.get("seed_admit", doc).get("columns") or []:
            for c in col.get("chars") or []:
                ks: set[str] = set()
                for sv in (((c.get("evidence") or {}).get("group") or {}).get("solvers") or []):
                    ks |= set((sv.get("probs") or {}).keys()) | set((sv.get("scores") or {}).keys())
                if c.get("id"):
                    cands[c["id"]] = ks
        for q in llm_questions_of_page(doc):
            r = by_cell.get(q["cell"])
            if not r or _hit(store, q["group"], q["ver"], q["l"], q["r"]) is not None:
                continue
            same_ver = r.get("prompt_ver") == q["ver"]
            rows.append({"cell": q["cell"], "组": q["group"], "裁定字": r.get("char") or ("其他" if r.get("other") else ""),
                         "把握": r.get("conf"), "原因": "窗口变了" if same_ver else (f"提示词版本 {r.get('prompt_ver')}→{q['ver']}"
                                                      + ("（--accept-old-ver 可换键）" if old_ver_ok(r, q, cands.get(q["cell"], set()) | {machine.get(q["cell"]) or "", ref.get(q["cell"]) or ""} - {""}) is None
                                                         else "（不收：" + old_ver_ok(r, q, cands.get(q["cell"], set()) | {machine.get(q["cell"]) or "", ref.get(q["cell"]) or ""} - {""}) + "）")),
                         "裁定窗口": f"{(r.get('ctx') or {}).get('left', '')}｜{(r.get('ctx') or {}).get('right', '')}",
                         "产物窗口": f"{q['l'][-20:]}｜{q['r'][:20]}", "差在": _diff(r.get("ctx"), q["l"], q["r"]), "_q": q, "_r": r,
                         "_hash": ruling_ctx_hash(q["l"], q["r"]), "_machine": machine.get(q["cell"]) or "",
                         "_ref": ref.get(q["cell"]) or "",
                         "_cands": cands.get(q["cell"], set()) | {machine.get(q["cell"]) or "", ref.get(q["cell"]) or ""} - {""}})
    return rows


VIS_VERS = ("vis-o1", "src-1", "ctx-m1")      # seed_admit 终审／看图裁定通道认的版本（group=O）


VIS_SUBS = frozenset({"Z", "N"})               # seed_admit _VIS_RULING_SPECS 里 ctx-m1 缺省收的子类


def _vis_window(doc: dict, amap: dict[str, str]) -> dict[str, tuple]:
    """一页 seed_admit 产物 → {格: (记录, 左窗, 右窗)}，取法同 seed_admit 5c `_vis_ruling_pass`（读序、跳 excluded、
    邻格 5c 时已放行用放行字否则用整理本对位字）。产物是整遍跑完的状态：5c 之后才放行／降审的邻格按当时状态退回
    （`final_review.pack.vis_windows`）；格带 `evidence.vis_ctx`（cv 当场记的窗口）时直接用它。"""
    from ._cv import CTX_WIDTH, PageAdmit, sort_by_reading
    from .final_review.pack import vis_windows
    page = PageAdmit.model_validate(doc.get("seed_admit", doc))
    seq = [r for c in sorted(page.columns, key=lambda c: c.col) for r in sort_by_reading(c.chars)
           if not (r.doubts and "excluded" in r.doubts)]
    w = vis_windows(seq, amap, CTX_WIDTH)
    return {r.id: (r, *w[r.id][:2]) for r in seq}


def _diff(ctx: dict | None, left: str, right: str) -> str:
    """裁定窗口与产物窗口差在哪几个字（「左1 撫→播」＝格左边第 1 字裁定时是 撫、现在是 播）。"""
    from .final_review.pack import window_diff
    ctx = ctx or {}
    return "；".join(x for x in (window_diff(ctx.get("left") or "", (left or "")[-20:], "左"),
                                 window_diff(ctx.get("right") or "", (right or "")[:20], "右")) if x)


def vis_reason(v: dict, rec, left: str, right: str, ref_now: str, subs: frozenset,
               override: tuple | None = None, store=None, anchored: bool = True, ts: str | None = None,
               cp_targets: frozenset = frozenset()) -> tuple[str, bool]:
    """终审看图裁定没放行的原因（按 seed_admit 判的次序）→ (原因, 能不能按产物窗口补键)。
    `store` 给了就核裁定库按这个窗口键实际取到的是不是这一条；`anchored`＝这页 align_ref 锚定了（没锚定管线不认整理本字）。"""
    from ._cv import ruling_ctx_hash
    if rec is None:
        if (v.get("ref") or "") != (ref_now or ""):
            return f"整理本对位字变了（裁定时 {v.get('ref') or '空'}，现 {ref_now or '空'}）", False
        return "算不出产物窗口（读不了这页 seed_admit）", False
    ds = {d for d in (rec.doubts or []) if isinstance(d, str)}
    if rec.provenance == "human" or rec.channel == "human":
        return "这格已有人裁（人裁优先）", False
    if ds & {"occluded", "excluded", "glyph_timeout"} or (rec.evidence or {}).get("occluded"):
        return "格带遮挡／超时疑点，终审不放", False
    if v.get("prompt_ver") == "ctx-m1" and v.get("subclass") not in subs:
        return f"子类 {v.get('subclass') or '空'} 不收（书级 vis_ruling_ctx_subclasses 没含）", False
    if half_cell(rec):
        half = "夹注半格（书级 group_flow_llm_skip_half 开着、vis_ruling_half 没开就不放）"
    else:
        half = ""
    if not anchored and v.get("ref"):
        return f"这页 align_ref 没锚定：管线不认整理本字（当空），与裁定时的 {v['ref']} 不同", False
    if (v.get("ref") or "") != (ref_now or ""):
        return f"整理本对位字变了（裁定时 {v.get('ref') or '空'}，现 {ref_now or '空'}）", False
    if not (v.get("ctx") or {}).get("hash"):
        return "裁定没写 ctx.hash：裁定库按窗口键永远取不到它，要按产物窗口补键", not half_cell(rec)
    if v["ctx"]["hash"] != ruling_ctx_hash(left, right):
        return "窗口变了（邻格放行字或对位字变了）" + (f"；另{half}" if half else ""), not half
    if half:
        return half, False
    if ref_now and v.get("char") != ref_now and v.get("prompt_ver") == "ctx-m1" and override is not None:
        from ._cv import seed_admit_override_ok
        if not seed_admit_override_ok(override, v["char"], ref_now):
            return (f"越过整理本（{ref_now}→{v.get('char')}）：两字不同属白名单 {','.join(override) or '（空）'} 里任一字组", False)
    if store is not None:
        cur = store.get(v.get("group") or "O", v.get("prompt_ver"), left, right)
        if cur is None:
            return "裁定库按这个窗口键取不到（本机裁定库没有这条？先 guji db pull）", False
        if cur is not v and (cur.get("cell"), cur.get("char"), cur.get("admit_ok"), cur.get("conf")) != \
                (v.get("cell"), v.get("char"), v.get("admit_ok"), v.get("conf")):
            return (f"同一窗口键有更晚的一条裁定盖过了它（格 {cur.get('cell')}、字 {cur.get('char')}、"
                    f"admit_ok={cur.get('admit_ok')}、{cur.get('conf')}）"), False
    ev = rec.evidence or {}
    if ev.get("vis_ruling"):
        return f"放行后被后面一遍降回待审（现疑点 {','.join(map(str, rec.doubts or [])) or '无'}）", False
    note = "" if override is not None or not ref_now or v.get("char") == ref_now else "（越过整理本，没给 --override-groups 未核白名单）"
    when = f"裁定写于 {ts}，" if ts else ""
    vc = ev.get("vis_ctx")
    if isinstance(vc, dict):
        return ("按 cv 当场记的 5c 窗口也对得上、manager 能核的条件都满足，仍没放：" + when
                + "先核产物是否晚于裁定推库（包 manifest 的 db_rev ≥ 裁定 rev）；晚于的话把格号报 GM2") + note, False
    hit = sorted({ch for ch in (left or "")[-20:] + (right or "")[:20] if ch in cp_targets})
    if hit:
        return ("多半是码位归一：产物窗口里有码位表目标字 " + "、".join(hit) + "，seed_admit 最后一步才把邻格放行字改成它们，"
                "5c 算键时还是原字，从产物终态算的窗口不准。产物用含 evidence.vis_ctx 的 cv（dev #1763 起）重跑 seed_admit 后再 --rekey"
                + ("；" + when.rstrip("，") if when else "")) + note, False
    return ("manager 能核的条件都满足，仍没放。两种可能：①产物早于裁定推库（" + when + "核包 manifest 的 db_rev ≥ 裁定 rev）；"
            "②5c 时邻格字与产物不同而 manager 看不出（码位归一 codepoint_semantic、pair_form 后来改了邻格放行字）。"
            "产物用含 evidence.vis_ctx 的 cv（dev #1763 起）重跑 seed_admit 后，rulings-hits／--rekey 直接按 5c 窗口") + note, False


def half_cell(rec) -> bool:
    return (getattr(rec, "id", None) or "")[-1:] in ("a", "b")


def codepoint_targets(book: str, data_dir=None) -> frozenset:
    """本书码位表的目标字（有别的码位归到它、且与源字不同）。读不到 → 空。"""
    m: dict = {}
    try:
        if data_dir:
            from .charnorm import codepoints_of
            m = codepoints_of(data_dir, book)
        else:
            from .charnorm import load_norm
            m = load_norm(book).map
    except Exception:  # noqa: BLE001
        m = {}
    return frozenset(v for k, v in m.items() if k != v)


def check_vis(products: Path, book: str, store, subs: frozenset = VIS_SUBS, override: tuple | None = None,
              cp_targets: frozenset = frozenset()) -> list[dict]:
    """终审／看图裁定（group=O，`vis_ruling` 通道）：写了可放行的裁定（high、admit_ok、有字）、产物里这格却仍待审。
    逐格按 seed_admit 的取法现算窗口，给出具体原因（人裁／疑点／子类／对位字／窗口／半格／越过整理本／产物旧）；
    只是窗口变了的可以 `--rekey` 按产物窗口补一条（字、子类、对位字照抄）。"""
    by_cell: dict[str, dict] = {}
    ts: dict[str, str] = {}
    for c, p in _rulings_by_cell_all(store, ts).items():
        if p.get("group") == "O" and p.get("prompt_ver") in VIS_VERS and p.get("conf") == "high" and p.get("admit_ok") \
                and p.get("char") and not p.get("other"):
            by_cell[c] = p
    if not by_cell:
        return []
    root = Path(products) / book
    rows = []
    for f in sorted((root / "seed_admit").glob("p*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        cols = doc.get("seed_admit", doc).get("columns") or []
        hit = [c for col in cols for c in col.get("chars") or [] if c.get("id") in by_cell and not c.get("admit")]
        if not hit:
            continue
        amap: dict[str, str] = {}
        anchored = True
        af = root / "align_ref" / f.name
        try:
            ar = json.loads(af.read_text(encoding="utf-8")).get("align_ref", {})
            anchored = ar.get("anchored", True) is not False      # 同 cv `_align`：没锚定整页不认整理本字
            for c in ar.get("chars") or []:
                if c.get("id") and anchored:
                    amap[c["id"]] = c.get("align_char") or ""
        except (OSError, ValueError):
            pass
        try:
            win = _vis_window(doc, amap)
        except Exception:  # noqa: BLE001
            win = {}
        for c in hit:
            v = by_cell[c["id"]]
            w = win.get(c["id"])
            rec, l, r = w if w is not None else (None, "", "")
            why, ok = vis_reason(v, rec, l, r, amap.get(c["id"], ""), subs, override, store=store, anchored=anchored,
                                 ts=ts.get(c["id"]),
                                 cp_targets=cp_targets if not ((rec.evidence or {}).get("vis_ctx") if rec is not None else None) else frozenset())
            rows.append({"cell": c["id"], "组": f"O/{v.get('prompt_ver')}/{v.get('subclass') or ''}", "裁定字": v["char"],
                         "把握": "high", "原因": why,
                         "裁定窗口": f"{(v.get('ctx') or {}).get('left', '')}｜{(v.get('ctx') or {}).get('right', '')}",
                         "产物窗口": f"{l[-20:]}｜{r[:20]}" if w else "",
                         "差在": _diff(v.get("ctx"), l, r) if w and why.startswith("窗口变了") else "", "_q": None, "_r": v,
                         "_vis": {"l": l, "r": r} if ok else None})
    return rows


def rekey_vis(rows: list[dict], batch: str, root=None) -> int:
    """只是窗口变了的终审裁定：照抄 payload、换成产物窗口另写一条（why 前缀 rekey）。"""
    from ._cv import RULING_KIND, RulingLog, ruling_ctx_hash
    from ._cv import EventTarget, make_event
    todo = [x for x in rows if x.get("_vis")]
    if not todo:
        return 0
    log = RulingLog(root) if root else RulingLog()
    seq = max((e.seq for e in log.read(batch, raw=True)), default=0)
    evs = []
    for x in todo:
        v, w = dict(x["_r"]), x["_vis"]
        l, r = w["l"][-20:], w["r"][:20]
        v["ctx"] = {"left": l, "right": r, "hash": ruling_ctx_hash(l, r)}
        v["why"] = ("rekey:" + (v.get("why") or ""))[:60]
        seq += 1
        cell = v["cell"]
        evs.append(make_event(batch, seq, RULING_KIND, EventTarget(step="seed_admit", unit="cell", key=cell,
                                                                    book=cell.split(":")[0] if cell.count(":") == 3 else None),
                              v, actor="model"))
    log.append(evs)
    return len(evs)


def _rulings_by_cell_all(store, ts: dict | None = None) -> dict[str, dict]:
    from ._cv import RULING_KIND
    from ._cv import replay_key
    out: dict[str, dict] = {}
    if not store.log.events_dir.exists():
        return out
    for e in sorted((e for e in store.log.iter_all(raw=True) if e.kind == RULING_KIND), key=replay_key):
        p = e.payload or {}
        if p.get("cell"):
            out[p["cell"]] = p
            if ts is not None:
                ts[p["cell"]] = getattr(e, "ts", None)
    return out


def _ver_base(v) -> str:
    """提示词版本去掉模型后缀（``ctx-m1#claude-opus:high`` → ``ctx-m1``）。"""
    return str(v or "").split("#", 1)[0]


def old_ver_ok(r: dict, q: dict, cands: set[str]) -> str | None:
    """旧提示词版本的裁定能不能换成当前版本的键（用户 11-24 定两档）。能返回 None，不能返回原因。
    共同条件：high、单字（非「其他」）、窗口哈希与产物窗口相同（字组由键保证）。
    ① 只差模型后缀（版本基名相同）：直接换。
    ② 真换版：裁定字还在新候选里（机器首选、整理本对位字、各路候选）才换。异体闸、抽 10 格看图由执行方（ZM）另做。
    不收的走网站人审。换键后仍要过 seed_admit 的全部护栏。"""
    from ._cv import ruling_ctx_hash
    if r.get("conf") != "high" or r.get("other") or not r.get("char"):
        return "非 high／其他／无字"
    if (r.get("ctx") or {}).get("hash") != ruling_ctx_hash(q["l"], q["r"]):
        return "窗口也变了"
    if _ver_base(r.get("prompt_ver")) == _ver_base(q["ver"]):
        return None
    if r["char"] not in cands:
        return "AI 字不在新候选里"
    return None


def rekey(rows: list[dict], store, accept_old_ver: bool = False) -> int:
    n = 0
    for x in rows:
        r, q = x["_r"], x["_q"]
        if q is None:
            continue
        if r.get("prompt_ver") != q["ver"]:
            if not accept_old_ver or old_ver_ok(r, q, x.get("_cands") or set()) is not None:
                continue
        char = "其他" if r.get("other") else r.get("char")
        if not char:
            continue
        why = ("rekey:" if r.get("prompt_ver") == q["ver"] else f"rekey-ver {r.get('prompt_ver')}→{q['ver']}:") + (r.get("why") or "")
        store.put(q["group"], q["ver"], q["l"], q["r"], char=char, conf=r.get("conf"),
                  why=why[:60], model=r.get("model") or "session", cell=q["cell"],
                  pending_reason=r.get("pending_reason"))
        n += 1
    return n


def cmd(a) -> None:
    from ._cv import RulingStore
    store = RulingStore()
    if a.batch:
        store._batch = a.batch
    books = [b.strip() for b in a.books.split(",") if b.strip()]
    if getattr(a, "fetch", False):
        fetch_books(books, Path(a.products), a.label, a.jobs)
    allrows = []
    for b in books:
        rows = check(Path(a.products), b, store)
        ovr = tuple(x.strip() for x in a.override_groups.split(",") if x.strip()) if a.override_groups is not None else None
        cps = codepoint_targets(b, getattr(a, "data_dir", None))
        vis = check_vis(Path(a.products), b, store, VIS_SUBS | {x.strip() for x in (a.vis_subclasses or "").split(",") if x.strip()}, ovr,
                        cp_targets=cps)
        allrows += rows + vis
        print(f"{b}：仍在问且有文意裁定却没命中 {len(rows)} 格；终审／看图裁定可放行却仍待审 {len(vis)} 格", file=sys.stderr)
    cols = ["cell", "组", "裁定字", "把握", "原因", "差在", "裁定窗口", "产物窗口"]
    out = Path(a.out) if a.out else None
    text = "\t".join(cols) + "\n" + "".join("\t".join(str(r.get(c) or "") for c in cols) + "\n" for r in allrows)
    if out:
        out.write_text(text, encoding="utf-8")
        print(f"清单：{out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    if a.rekey and allrows:
        if not a.batch:
            sys.exit("--rekey 要给 --batch <批次名>（如 llm-rekey-QTW-20261120）")
        n = rekey(allrows, store, getattr(a, "accept_old_ver", False))
        nv = rekey_vis(allrows, a.batch, store.log.root if hasattr(store.log, "root") else None)
        print(f"按产物窗口补写文意裁定 {n} 条、终审裁定 {nv} 条（批次 {a.batch}）；guji db sync 推库后重放 seed_admit 即命中", file=sys.stderr)


FETCH_STEPS = ("seed_admit", "align_ref")


def fetch_books(books: list[str], root: Path, label: str | None = None, jobs: int = 4) -> None:
    """各册取产物包，只解 seed_admit／align_ref 到 `root`（已有就覆盖：这里是核对用的产物根，别指向本机正在跑的产物）。"""
    from concurrent.futures import ThreadPoolExecutor
    from .datastore import packs as PK

    def one(b):
        t = time.time()
        info = PK.fetch_products(b, root, label=label, force=True, steps=list(FETCH_STEPS))
        return b, info["name"].rsplit("/", 1)[-1], time.time() - t
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        for b, lab, dt in ex.map(one, books):
            print(f"  取 {b} 包 {lab}（只解 seed_admit、align_ref）{dt:.0f} 秒", file=sys.stderr)


# ---- 重放预演：重放包 vs ★main 基线，只看有 AI 裁定的格（2026-11-23，GM4）----
# 做法：先用 `guji job submit --from seed_admit`（缺省只跑有新裁定的页）出一个**不标 main** 的重放包，取回后
# `guji rulings-hits --books vol21 --products <基线包根> --replay <重放包根>`：对比这些格放行了没有、字变没变。
# 规则与正式重放同一套（就是 seed_admit 本身的结果），本命令不判规则，只对账。

def _ctx_ruling(rec: dict):
    """格记录里 ctx 那一路的 AI 裁定：(字, 把握) 或 None。"""
    g = ((rec.get("evidence") or {}).get("group") or {})
    for sv in g.get("solvers") or []:
        if str(sv.get("via") or sv.get("solver") or "").startswith("ctx") and sv.get("char"):
            return sv["char"], sv.get("llm_conf") or ""
    return None


def _cells_of(root: Path, book: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in sorted((Path(root) / book / "seed_admit").glob("p*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for col in doc.get("seed_admit", doc).get("columns") or []:
            for c in col.get("chars") or []:
                if c.get("id"):
                    out[c["id"]] = c
    return out


def replay_diff(base_root: Path, new_root: Path, book: str) -> list[dict]:
    """重放包相对基线的变化；只列重放包里 ctx 那路有 AI 裁定的格（重放包没有的页不比，按页重放时只比重放过的页）。
    类别：新放行（基线待审→放行）、新放行且改字、仍待审、放行改字、放行退回待审、没变；重放包里放行后证据不留 ctx 字的格，AI字列空，看「通道」列（human 通道可能是人裁事件，也可能是已落地的 AI 裁定，GM2 评估里 vol21 的一致格就是这样）。"""
    base, new = _cells_of(base_root, book), _cells_of(new_root, book)
    rows = []
    for cid, n in new.items():
        b = base.get(cid)
        if b is None:
            continue
        ai = _ctx_ruling(n) or _ctx_ruling(b)
        bad, nad = bool(b.get("admit")), bool(n.get("admit"))
        bch, nch = b.get("char") or "", n.get("char") or ""
        changed = (bad != nad) or (nch != bch)
        if ai is None and not changed:
            continue          # 没裁定、也没变：不列
        if ai is None:
            ai = ("", "")     # 变了但看不出裁定（放行后证据里不留 ctx 字）：裁定字留空，通道列可看来路
        if not bad and nad:
            k = "新放行·改字" if nch != bch else "新放行·字同机器首选"
        elif not bad and not nad:
            k = "仍待审"
        elif bad and not nad:
            k = "放行退回待审"
        else:
            k = "放行·改字" if nch != bch else "没变"
        rows.append({"cell": cid, "类别": k, "基线": ("放行" if bad else "待审") + f"·{bch}", "重放": ("放行" if nad else "待审") + f"·{nch}",
                     "通道": n.get("channel") or "", "AI字": ai[0], "AI把握": ai[1],
                     "AI＝机器首选": ("" if not ai[0] else ("是" if ai[0] == bch else "否")), "疑问码": ";".join(n.get("doubts") or [])[:120]})
    return rows


def replay_cmd(a) -> None:
    from collections import Counter
    books = [b.strip() for b in a.books.split(",") if b.strip()]
    allrows = []
    for b in books:
        rows = replay_diff(Path(a.products), Path(a.replay), b)
        allrows += rows
        cnt = Counter(r["类别"] for r in rows)
        print(f"{b}：对账格（有 AI 裁定或有变化）{len(rows)}；" + "、".join(f"{k} {v}" for k, v in cnt.most_common()), file=sys.stderr)
    cols = ["cell", "类别", "基线", "重放", "通道", "AI字", "AI把握", "AI＝机器首选", "疑问码"]
    text = "\t".join(cols) + "\n" + "".join("\t".join(str(r.get(c) or "") for c in cols) + "\n" for r in allrows)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"清单：{a.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("rulings-hits", help="AI 文意裁定命中核对：产物里仍在问、却有裁定没命中的格（窗口变了）；--rekey 按产物窗口补写")
    p.add_argument("--books", required=True, help="册，逗号分隔（如 001,002 或 vol20）")
    p.add_argument("--products", required=True, help="产物根（下有 <册>/seed_admit/）")
    p.add_argument("-w", "--workspace", default=None, help="工作区（定裁定库位置；缺省 GUJI_WORKSPACE）")
    p.add_argument("--out", default=None, help="清单 tsv（缺省打到标准输出）")
    p.add_argument("--rekey", action="store_true", help="按产物里的窗口另写一条裁定（同提示词版本的才写）")
    p.add_argument("--batch", default=None, help="--rekey 写进的裁定批次名")
    p.add_argument("--accept-old-ver", action="store_true",
                   help="--rekey 时旧提示词版本的裁定也换键（用户 11-24 定两档）：high 单字、窗口相同，且只差模型后缀，或裁定字仍在新候选里；其余不动。异体闸、抽样看图由执行方另做")
    p.add_argument("--replay", default=None, metavar="重放包根",
                   help="重放预演：--products 当基线（★main 包根），这里给重放包根，只对账有 AI 裁定的格（新放行／改字／仍待审／退回）；不写库")
    p.add_argument("--vis-subclasses", default=None,
                   help="书级 seed_admit.vis_ruling_ctx_subclasses（如殿本 P,D）：判「子类不收」时一并算收（缺省只算 Z,N）")
    p.add_argument("--fetch", action="store_true",
                   help="先按册取产物包（缺省 main），只解 seed_admit、align_ref 到 --products（覆盖；指向专门的核对目录），各册并行")
    p.add_argument("--label", default=None, help="--fetch 取哪个包标签（缺省各册 main）")
    p.add_argument("--jobs", type=int, default=4, help="--fetch 同时取几册（缺省 4）")
    p.add_argument("--data-dir", default=None, help="数据目录（读 config/codepoints.yaml 等码位表；缺省按 cv 找本册配置）")
    p.add_argument("--override-groups", default=None,
                   help="书级 seed_admit.ruling_override_groups，逗号分隔（殿本 ly,dt,wm,ts,mb,fc,rr,ry,guan,wxs,jys）；给了才核越过整理本")


def _cmd(a) -> None:
    import os
    if a.workspace:
        os.environ["GUJI_WORKSPACE"] = str(Path(a.workspace).resolve())
    if a.replay:
        return replay_cmd(a)
    cmd(a)


COMMANDS = {"rulings-hits": (add_parser, _cmd)}
