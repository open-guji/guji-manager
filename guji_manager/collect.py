"""收单快路：``guji collect``——用户在网站投完一张单，人裁直接落进 book-text、KV／中心库，不重放、不重出单。

ZM 第一册线（11-17、11-19）实测：收一张单净计算不到 5 分钟，总耗时 20 分钟到 2 小时，大头是 3–5 次 pull/sync 和
等任务库从 seed_admit 重放（人裁只有重放后才进产物，再导出才进 book-text）。可 book-text 只录首选字（sheldon 11-09），
人裁定了字，book-text 那一格该是什么字已经知道了，不必等重放：

1. ``db pull`` 一次（增量）。
2. 读线上单：rev、出单版产物包（``rev-<rev>``，没有就退到 ★main 包）。
3. ``cellvotes draft --from-kv --items --pack``（读票、出草稿；挂起照旧）→ ``cellvotes write``（写人裁事件、落了票的条目标已裁、
   重导整张单）。批次名 ``H-web-<册>-<日期>-<rev>``，与 ``proof_cycle`` 同。
4. **定字直接写 book-text**：本次写下的定字票（``v=confirm`` 带字），加上 ``--batch`` 点名的早先人裁批次（过绑定表），
   逐格对 book-text 现文（dev）：
   - 字一样（含码位归一 别／別）：不动；
   - 格框对不上（出单版包的 cell_shrink 与 book-text cord 差 >8px、或本列格数不同＝book-text 不是这一版切分）：不写，
     记「等下一轮重放」；
   - 以图代字格（带 ``fig``）：不写（格里只能是 □）；
   - 其余：写人裁的字（去掉 lacuna／guess_c），校验字（标点 pre_char、专名 text）跟改，升 patch，``local_check --dev``，推 dev
     （1.x 册推 ``swap/<册>-1x`` 开草稿 PR，同 ``guji swap book-text``）。char-edits 手改与人裁冲突就停（守卫）。
   **AI 裁定也一起落**（用户 2026-11-20 定，``--no-ai`` 关）：出单版包里仍待审的格，文意裁定按窗口命中（同重放的键）且
   ``conf=high``、字在组内；终审看图裁定（group=O）``high``＋``admit_ok``、整理本对位字没变、不是夹注半格。人裁（票、现行人裁、
   ``--batch``）优先，AI 只补没人裁的格；单上的条目不结案（用户再投票仍以票为准）。见 ``ai_ruling_chars``。
5. ``--batch`` 落的格：线上单上还开着的条目标已裁。
6. ``db sync`` 一次（推事件、单子；人裁照常落字形库）。
7. 只发这一章（proofing-sync ``only=``），核线上单：本次定了字的格不再是待审。

不做的：不重放 seed_admit、不出新单（产物包里机器字等下一轮重放自然对上，人裁最高）；票的闸、挂起、切分票照旧
（看 ``draft/report.md``、``held.tsv``、``structure.tsv``）。

断点续跑：状态在 ``<工作区>/reports/<册>/_collect/<rev>/state.json``，每步做完记一笔；中途停了原命令再跑，做过的跳过
（``write`` 本身也有幂等键）。``--fresh`` 从头。

``guji collect --books vol20 -w <工作区> --book-text <book-text 检出> [--reviewer sheldon] [--batch <早先人裁批次> …]``
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .swap import DIANBEN_ID, LIVE, chapter_of, parse_books, vol_no

PLACEHOLDERS = ("□", "〓", "▣")
GUJI = [sys.executable, "-m", "open_guji_cv.cli_v2"]
STEPS = ("pull", "draft", "write", "book-text", "resolve", "sync", "publish", "verify")


# ───────────────────────── 纯函数（可测） ─────────────────────────

def _cells(char: dict) -> dict[str, dict]:
    return {x["a"]: x for pg in char.get("pages") or [] for col in pg.get("columns") or [] for x in col.get("cells") or []}


def bare(a: str) -> str:
    """``vol20:84:3:10`` → ``84:3:10``。"""
    parts = str(a).split(":")
    return ":".join(parts[1:]) if len(parts) == 4 else str(a)


def plan_edits(char: dict, want: dict[str, tuple[str, str]], box_problem=None, same=None) -> dict[str, list]:
    """``want``：{格: (人裁字, 来源)}。逐格对 book-text 现文分成：apply（要写）、already（已是这个字）、
    layout（格框对不上，等重放）、fig（以图代字格）、missing（book-text 没有这一格）。``box_problem(a)`` 返回 None＝对得上。"""
    eq = same or (lambda p, q: p == q)
    cur = _cells(char)
    out: dict[str, list] = {k: [] for k in ("apply", "already", "layout", "fig", "missing")}
    for a in sorted(want, key=_key):
        c, src = want[a]
        x = cur.get(a)
        if x is None:
            out["missing"].append((a, None, c, src))
            continue
        old = x.get("c") or ""
        if x.get("fig") is not None:
            out["fig"].append((a, old, c, src))
            continue
        if old and eq(old, c) and not x.get("lacuna"):
            out["already"].append((a, old, c, src))
            continue
        why = box_problem(a) if box_problem else None
        if why:
            out["layout"].append((a, old, c, src, why))
            continue
        out["apply"].append((a, old, c, src))
    return out


def apply_edits(char: dict, edits: list[tuple]) -> dict:
    """返回改好的 char 副本（只改 edits 里的格；格序不变，核对位）。"""
    from .swap.overlay_edits import _set_char, verify
    import copy
    out = copy.deepcopy(char)
    by = _cells(out)
    for a, _old, c, *_ in edits:
        _set_char(by[a], c)
    verify(char, out, {e[0] for e in edits})
    return out


def _key(a: str):
    import re
    return tuple(int(p) if p.isdigit() else p for p in re.findall(r"\d+|\D+", a))


def vote_chars(draft_dir: Path) -> dict[str, tuple[str, str]]:
    """草稿里可写的定字票 {格: (字, 来源)}：``v=confirm`` 且带 ``shape``、不是无法识别字。"""
    out = {}
    f = Path(draft_dir) / "drafts.jsonl"
    if not f.exists():
        return out
    for ln in f.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        r = json.loads(ln)
        pl = r.get("payload") or r
        if (pl.get("v") or r.get("v")) != "confirm" or pl.get("unk"):
            continue
        c = pl.get("shape") or r.get("shape")
        a = r.get("a") or bare(r.get("id") or "")
        if c and a and c not in PLACEHOLDERS:
            out[bare(a)] = (c, "票")
    return out


def consistent_cells(draft_dir: Path) -> dict[str, str]:
    """草稿里因「与已有人裁 X 一致」跳过的票 {格: 那条人裁的事件 id}：用户在这张单上投过、人裁早已落库，
    book-text 却可能还没跟上（上一轮只落了票、等重放），条目也可能还开着（11-19 前 write 不结条目）。"""
    import re
    meta = Path(draft_dir) / "meta.json"
    if not meta.exists():
        return {}
    out = {}
    for a, why in json.loads(meta.read_text(encoding="utf-8")).get("skipped") or []:
        m = re.match(r"与已有人裁 (\S+) 一致", str(why))
        if m:
            out[bare(a)] = m[1]
    return out


AI_VIS_VERS = ("vis-o1", "src-1", "ctx-m1")


def ai_ruling_chars(products_root, book: str, store=None, members=None) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """AI 裁定可直接落文本的格 {格（无册前缀）: (字, 来源)}（用户 2026-11-20 定：AI 裁定像人裁一样直接写 book-text，不等重放）。

    只认出单版包里**仍待审**的格，且裁定确定对得上这一格：
    - 文意（L3 组）：这格的 ask 窗口在裁定库里**按窗口命中**（与重放 seed_admit 同一把键），``conf=high``、字在组内、不是「其他」；
    - 终审／看图（group=O，``vis-o1``/``src-1``/``ctx-m1``）：按格号取最新一条，``conf=high``、``admit_ok``、有字，
      且裁定时的整理本对位字与包里现在的一样；夹注半格（格号带 a／b）不落（seed_admit 缺省也不放）。
    人裁优先由调用方处理（有现行人裁的格不用这里的字）。"""
    import re
    from ._cv import llm_questions_of_page
    if store is None:
        from ._cv import RulingStore
        store = RulingStore()
    if members is None:
        try:
            from ._cv import FLOW_GROUPS
            members = {k: set(v.members) for k, v in FLOW_GROUPS.items()}
        except Exception:  # noqa: BLE001
            members = {}
    root = Path(products_root) / book
    out: dict[str, tuple[str, str]] = {}
    notes: list[str] = []
    pending: set[str] = set()
    asks: list[dict] = []

    def mine(cid: str) -> bool:
        parts = str(cid).split(":")
        return len(parts) != 4 or parts[0] == book

    for f in sorted((root / "seed_admit").glob("p*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for col in (doc.get("seed_admit", doc).get("columns") or []):
            for c in col.get("chars") or []:
                if c.get("id") and not c.get("admit") and mine(c["id"]):
                    pending.add(c["id"])
        asks += [q for q in llm_questions_of_page(doc) if q.get("cell") and mine(q["cell"])]
    for q in asks:
        if q["cell"] not in pending:
            continue
        v = store.get(q["group"], q["ver"], q["l"], q["r"])
        if not v or v.get("other") or not v.get("char") or v.get("char") in PLACEHOLDERS:
            continue
        if v.get("conf") != "high":
            notes.append(f"{bare(q['cell'])} 文意裁定「{v.get('char')}」把握 {v.get('conf')}，不直接落")
            continue
        if members.get(q["group"]) and v["char"] not in members[q["group"]]:
            notes.append(f"{bare(q['cell'])} 文意裁定「{v['char']}」不在组 {q['group']} 内，不落")
            continue
        out.setdefault(bare(q["cell"]), (v["char"], f"AI文意/{q['group']}"))
    if not store.log.events_dir.exists():
        return out, notes
    from ._cv import RULING_KIND, replay_key
    vis: dict[str, dict] = {}
    for e in sorted((e for e in store.log.iter_all(raw=True) if e.kind == RULING_KIND), key=replay_key):
        p = e.payload or {}
        if p.get("cell") and p.get("group") == "O" and p.get("prompt_ver") in AI_VIS_VERS:
            vis[p["cell"]] = p
    vis = {k: v for k, v in vis.items() if k in pending and bare(k) not in out}
    if not vis:
        return out, notes
    ref: dict[str, str] = {}
    for f in sorted((root / "align_ref").glob("p*.json")):
        try:
            for c in json.loads(f.read_text(encoding="utf-8")).get("align_ref", {}).get("chars") or []:
                if c.get("id") in vis:
                    ref[c["id"]] = c.get("align_char") or ""
        except (OSError, ValueError):
            continue
    for k, v in sorted(vis.items()):
        if not (v.get("conf") == "high" and v.get("admit_ok") and v.get("char") and not v.get("other")):
            continue
        if v["char"] in PLACEHOLDERS:
            continue
        if re.search(r"[ab]$", k):
            notes.append(f"{bare(k)} 看图裁定「{v['char']}」是夹注半格，不直接落")
            continue
        if (v.get("ref") or "") != ref.get(k, ""):
            notes.append(f"{bare(k)} 看图裁定「{v['char']}」时整理本对位字 {v.get('ref') or '空'}，现 {ref.get(k) or '空'}，不落")
            continue
        out[bare(k)] = (v["char"], f"AI看图/{v.get('prompt_ver')}")
    return out, notes


def live_open_cells(doc: dict) -> set[str]:
    """线上单里还待审的格（``review`` 不是 human）。"""
    return {bare(c["cell"]) for c in doc.get("cells") or [] if c.get("cell") and c.get("review", "pending") != "human"}


# ───────────────────────── 状态 ─────────────────────────

def _load_state(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"done": {}}


def _save_state(p: Path, st: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


class Run:
    def __init__(self, sp: Path, fresh: bool, dry: bool = False):
        self.sp, self.dry = sp, dry
        self.st = {"done": {}} if fresh else _load_state(sp)
        self.t0 = time.time()

    def done(self, step: str) -> bool:
        return step in self.st["done"]

    def mark(self, step: str, info=None, t=None) -> None:
        self.st["done"][step] = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                 "s": round(time.time() - (t or self.t0), 1), **({"info": info} if info is not None else {})}
        if not self.dry:                         # 演练不留进度：真跑时照常拉库、重读票
            _save_state(self.sp, self.st)

    def skip(self, step: str) -> None:
        print(f"  · {step}：上次已做，跳过")


def _run(cmd: list, env: dict, tries: int = 1) -> int:
    """跑一条 guji 命令。``tries``>1 只给幂等的步（拉库、读票、落票带幂等键、推库）：网络读超时（R2／中心库 SSL timeout、
    StaleBase、断连）在这一步里重试，不让整册重来（ZM 11-19 B 轮 vol14／18）。"""
    rc = 1
    for i in range(tries):
        print("  $ " + " ".join(str(c) for c in cmd) + (f"   （第 {i + 1} 次）" if i else ""), flush=True)
        rc = subprocess.run([str(c) for c in cmd], env=env).returncode
        if rc == 0:
            return 0
        if i < tries - 1:
            time.sleep(10 * (i + 1))
    return rc


# ───────────────────────── 各步 ─────────────────────────

def _pack_for(book: str, rev: str) -> str | None:
    """出单版包 ``rev-<rev>``；没有就 ★main。都取不到返回 None。"""
    try:
        from .datastore import packs as PK
        src = PK._client()
        pre = PK._prefix(PK._ws_name(), book)
        try:
            PK._call(src, "GET", f"{pre}/rev-{rev}/manifest.json", raw=True)
            return f"rev-{rev}"
        except Exception:  # noqa: BLE001
            return PK.main_label(book, src)
    except Exception as e:  # noqa: BLE001
        print(f"  ⓘ 取不到产物包信息：{e}")
        return None


def _box_problem_fn(book: str, products_root: str | None, cord_path: Path):
    """出单版包（或本机产物根）的 cell_shrink 对 book-text cord：对不上返回理由。"""
    from . import cli_cellvotes as CV
    if products_root:
        try:                                     # 出单版包只含重跑过的页：缺的页退回本机主产物根（同 cellvotes draft）
            from ._cv import products_root as _pr
            main = os.environ.pop("GUJI_PRODUCTS_DIR", None)
            CV._MAIN_ROOT[0] = Path(main) if main and "_packs" not in main else _pr()
        except Exception:  # noqa: BLE001
            CV._MAIN_ROOT[0] = None
        os.environ["GUJI_PRODUCTS_DIR"] = products_root
    return CV._box_checker(book, cord_path, 8.0)


def current_human(book: str, products_root: str | None) -> dict[str, str]:
    """现行人裁 {格（无册前缀）: 字}：cv ``feedback.lookup.human_chars``（seed_admit 人裁通道同一口径），绑定按
    ``products_root``（出单版包）算。出错就抛，不退回按格号。"""
    if products_root:
        os.environ["GUJI_PRODUCTS_DIR"] = products_root
    from ._cv import human_chars
    return {bare(k): c for k, c in human_chars(book).items() if c and k.startswith(f"{book}:")}


def batch_cells(book: str, batches: list[str], products_root: str | None) -> tuple[dict[str, str], list[str]]:
    """``--batch`` 点名的人裁批次 → {现行格（绑定后）: 批次}；字由调用方从 ``current_human`` 取（每格最新、生效的那条）。"""
    if products_root:
        os.environ["GUJI_PRODUCTS_DIR"] = products_root
    from ._cv import EventLog, feedback_root, book_bindings, bindings_usable
    evs = [e for e in EventLog(feedback_root()).iter_all() if getattr(e, "batch", None) in batches
           and e.kind == "confirm" and e.target.unit == "cell" and e.target.key.startswith(f"{book}:")]
    if not evs:
        return {}, [f"批次 {','.join(batches)} 里没有 {book} 的格级人裁"]
    pages = sorted({int(bare(e.target.key).split(":")[0]) for e in evs})
    try:
        rows = book_bindings(book, pages=pages)
    except Exception as e:  # noqa: BLE001
        return {}, [f"绑定表算不出来（{type(e).__name__}: {e}），这些批次不落"]
    out, miss = {}, []
    for e in evs:
        cell = bindings_usable(rows.get(e.id), e.ts)
        if cell:
            out[bare(cell)] = e.batch
        else:
            miss.append(f"{bare(e.target.key)} 绑定 {(rows.get(e.id) or {}).get('status', '无')}，不落")
    return out, miss


def resolve_items(ws: Path, text_id: str, chapter: str, cells: dict[str, str], by: str, why: str) -> int:
    """线上单上这些格还开着的条目标已裁，重导整张单。返回标了几条。"""
    from .datastore.workcopy import data_dir
    from .review import pending_items as P
    from .cli_pending import export
    data = data_dir(ws)
    store = P.ItemStore.open(data, text_id, chapter)
    n = 0
    for a, ev in cells.items():
        hit = [x for x in store.find(a) if x["state"] in ("open", "withdrawn")]
        if hit:
            store.resolve(hit[0]["id"], by=by, event=ev or "", why=why)
            n += 1
    if n:
        store.save()
        export(store, data)
    return n


def live_sheet(text_id: str, chapter: str) -> dict | None:
    try:
        with urllib.request.urlopen(LIVE.format(text_id=text_id, n=int(chapter)) + f"?x={int(time.time())}", timeout=30) as r:
            return json.load(r)
    except Exception:  # noqa: BLE001
        return None


def collect_book(a, ws: Path, book: str) -> dict:
    from .datastore.workcopy import data_dir
    from .online_lists import book_text_dir
    text_id, ch = a.text_id, chapter_of(book)
    os.environ["GUJI_WORKSPACE"] = str(ws)        # 本进程里取包、读事件、核格框也认这个工作区
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    env.setdefault("GUJI_ACTOR", "collect")
    print(f"\n== {book}（{text_id}/{ch}）")

    # 1. 拉库（只一次）：线上单、事件以库为准
    t = time.time()
    sheet_p = data_dir(ws) / "feedback" / "lists" / "proofing" / text_id / f"{ch}.pending.json"
    pre_state = None
    if sheet_p.exists():
        rev0 = json.loads(sheet_p.read_text(encoding="utf-8")).get("rev")
        pre_state = ws / "reports" / book / "_collect" / str(rev0) / "state.json"
    if not a.no_pull and not (pre_state and not a.fresh and "pull" in _load_state(pre_state).get("done", {})
                               and "sync" not in _load_state(pre_state)["done"]):
        if _run([*GUJI, "db", "pull", "-w", ws], env, tries=3):
            return {"status": "blocked", "why": "guji db pull 失败"}
    if not sheet_p.exists():
        return {"status": "blocked", "why": f"数据目录没有线上单 {sheet_p}"}
    rev = json.loads(sheet_p.read_text(encoding="utf-8")).get("rev")
    out = ws / "reports" / book / "_collect" / rev
    R = Run(out / "state.json", a.fresh or a.dry_run, a.dry_run)
    if R.done("verify") or (R.done("sync") and R.st.get("no_publish")):
        # 收单不换 rev：上一趟收完之后用户在同一张单上又投了票，这是新的一趟。旧进度留底，从头做
        if not a.dry_run:
            os.replace(out / "state.json", out / f"state-{time.strftime('%Y%m%dT%H%M%S')}.json")
        R = Run(out / "state.json", True, a.dry_run)
    R.st["no_publish"] = bool(a.no_publish)
    R.mark("pull", {"rev": rev}, t)

    # 2–3. 读票、落人裁
    draft = out / "draft"
    # 同一张单可能收好几趟（不换 rev）：批次名带到分钟，免得撞名（ZM 以前手工加 b 后缀）
    batch = f"H-web-{book}-{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d-%H%M')}-{rev}"
    if R.done("draft"):
        R.skip("draft")
        pack, batch = R.st["done"]["draft"]["info"]["pack"], R.st["done"]["draft"]["info"]["batch"]
    else:
        t = time.time()
        pack = a.pack or _pack_for(book, rev)
        cmd = [*GUJI, "cellvotes", "draft", book, "--site-book", text_id, "--rev", rev, "--out", draft, "-w", ws,
               "--from-kv", "--items"]
        cmd += ["--pack", pack] if pack else ["--no-box-check"]
        if a.batch or not getattr(a, "no_ai", False):
            cmd += ["--allow-empty"]          # 只落早先批次／AI 裁定时单上可能 0 票
        if _run(cmd, env, tries=3):
            return {"status": "blocked", "why": "cellvotes draft 失败（见上；0 票又没给 --batch 时也会停）", "rev": rev}
        R.mark("draft", {"pack": pack, "batch": batch}, t)
    meta = json.loads((draft / "meta.json").read_text(encoding="utf-8")) if (draft / "meta.json").exists() else {}
    if a.dry_run:
        print(f"  --dry-run：不写人裁（可写 {meta.get('ready', 0)}、挂起 {meta.get('held', 0)}，见 {draft / 'report.md'}）")
    elif R.done("write"):
        R.skip("write")
    else:
        t = time.time()
        if meta.get("ready"):
            if _run([*GUJI, "cellvotes", "write", book, draft, "--batch", batch, "--reviewer", a.reviewer, "-w", ws], env, tries=3):
                return {"status": "blocked", "why": "cellvotes write 失败", "rev": rev}
        R.mark("write", {"ready": meta.get("ready", 0), "held": meta.get("held", 0)}, t)

    # 4. 定字直接写 book-text
    from .swap.booktext import _bt_dir, _worktree, do_book
    src = Path(a.book_text).resolve()
    wt = Path(a.worktree or (str(src) + "-collect")).resolve()
    landed: dict[str, str] = {}
    if R.done("book-text") and not a.dry_run:
        R.skip("book-text")
        landed = R.st["done"]["book-text"]["info"].get("landed") or {}
    else:
        t = time.time()
        sp = (Path(book_text_dir(".", text_id)).as_posix().lstrip("./"),)
        _worktree(src, wt, branch="collect-booktext", sparse=sp)
        vdir = _bt_dir(wt, text_id) / "default"
        cf, cordf = vdir / f"{ch}.char.json", vdir / f"{ch}.cord.json"
        if not cf.exists() or not cordf.exists():
            return {"status": "blocked", "why": f"book-text dev 上没有 {cf.name}／{cordf.name}", "rev": rev}
        char = json.loads(cf.read_text(encoding="utf-8"))
        # 落什么字只认 seed_admit 同一口径的现行人裁（cv human_chars：过绑定表，valid／rebound 到现格才算，
        # 页表 rev 不符、撤库标记、被推翻的都不算），按绑定后的格号取。11-19 v0.4.66 按事件原格号取字，
        # ZM vol01 88:1:12a（rebound 到 13a）、18a（迁移锚，旧格网）会落错格。
        same_ids = consistent_cells(draft)
        votes_now = vote_chars(draft)
        try:
            hc = current_human(book, meta.get("products_root"))
        except Exception as e:  # noqa: BLE001
            return {"status": "blocked", "rev": rev,
                    "why": f"现行人裁（human_chars）算不出来，不落 book-text：{type(e).__name__}: {str(e)[:300]}"}
        cells = {k: "票" for k in votes_now} | {k: "票与已有人裁一致" for k in same_ids if k not in votes_now}
        notes = []
        if a.batch:
            got, miss = batch_cells(book, a.batch, meta.get("products_root"))
            notes += miss
            for k, v in got.items():
                cells.setdefault(k, v)
        want = {k: (hc[k], src) for k, src in cells.items() if k in hc and hc[k] not in PLACEHOLDERS}
        if a.dry_run:                              # 演练没写票：这次新票按票上的字算（真跑时写完再从 human_chars 取）
            for k, (c, _) in votes_now.items():
                want[k] = (c, "票（未写）")
        for k in cells:
            if k not in want:
                notes.append(f"{k} 现行没有生效的定字人裁（绑定不是 valid／rebound 到本格、rev 不符或撤库），不落")
        # AI 裁定（文意、终审看图）直接落，不等重放（用户 11-20 定）；真人票／现行人裁优先，AI 只补没人裁的格
        n_ai = 0
        if not getattr(a, "no_ai", False):
            pr = meta.get("products_root") or os.environ.get("GUJI_PRODUCTS_DIR")
            if not pr:
                notes.append("没有出单版产物根，AI 裁定这次不落")
            else:
                try:
                    ai, ai_notes = ai_ruling_chars(pr, book)
                except Exception as e:  # noqa: BLE001
                    ai, ai_notes = {}, [f"AI 裁定读不出来（{type(e).__name__}: {str(e)[:200]}），这次不落"]
                notes += ai_notes
                for k, v in ai.items():
                    if k in hc or k in want or k in cells:
                        continue
                    want[k] = v
                    n_ai += 1
            print(f"  AI 裁定可直接落 {n_ai} 格（人裁优先；--no-ai 关）")
        from .charnorm import codepoints_of, load_norm
        try:
            extra = codepoints_of(data_dir(ws), book)
        except SystemExit:
            extra = {}
        same = load_norm(book, extra).same
        try:
            box = _box_problem_fn(book, meta.get("products_root"), cordf)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ 核不了格框（{e}）：全部按「等重放」处理，不写 book-text")
            box = lambda _a: "核不了格框"  # noqa: E731
        plan = plan_edits(char, want, box, same)
        rep = {k: [list(x) for x in v] for k, v in plan.items()}
        (out / "落文本.json").write_text(json.dumps({"plan": rep, "notes": notes}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  定字 {len(want)} 格：要写 {len(plan['apply'])}、已一致 {len(plan['already'])}、格框对不上等重放 "
              f"{len(plan['layout'])}、以图代字格 {len(plan['fig'])}、book-text 无此格 {len(plan['missing'])}")
        for x in plan["layout"][:8]:
            print(f"    等重放 {x[0]}「{x[2]}」：{x[4]}")
        for m in notes[:8]:
            print(f"    {m}")
        info = {"landed": {}, "plan": {k: len(v) for k, v in plan.items()}}
        if plan["apply"]:
            new_char = apply_edits(char, plan["apply"])
            exp = out / "export"
            exp.mkdir(parents=True, exist_ok=True)
            from .formats.guji_char_cord import dumps
            new_char["version"] = char.get("version", new_char.get("version"))
            (exp / f"{ch}.char.json").write_text(dumps(new_char), encoding="utf-8", newline="\n")
            (exp / f"{ch}.cord.json").write_bytes(cordf.read_bytes())
            srcs = sorted({x[3].split("/")[0] for x in plan["apply"]})
            n_ai_apply = sum(1 for x in plan["apply"] if x[3].startswith("AI"))
            note = (f"{book} 收单 {rev}：人裁定字直接落 {len(plan['apply'])} 格（{'、'.join(srcs)}"
                    + (f"，其中 AI 裁定 {n_ai_apply} 格" if n_ai_apply else "") + "），不重放"
                    + (f"；批次 {batch}" if meta.get("ready") else ""))
            title = (f"{book}：收单 {rev} 人裁定字 {len(plan['apply']) - n_ai_apply} 格"
                     + (f"＋AI 裁定 {n_ai_apply} 格" if n_ai_apply else "") + "直接落文本（patch）")
            r = do_book(wt, ws, book, text_id, exp, note=note, push=not (a.no_push or a.dry_run), pending={}, out_dir=out / "book-text",
                        merge=False, title=title, store_lineage=False,
                        detail=[f"人裁定字 {len(plan['apply'])} 格：" + "、".join(f"{x[0]} {x[1] or '□'}→{x[2]}" for x in plan["apply"][:40])
                                + ("…" if len(plan["apply"]) > 40 else ""),
                                f"来源：{'、'.join(srcs)}；已一致 {len(plan['already'])} 格，格框对不上等重放 {len(plan['layout'])} 格"])
            print(f"  book-text：{r['status']} {r.get('why', '')} {r.get('pr', '')}")
            if r["status"] not in ("pushed", "committed", "pr-opened", "pr-needed"):
                (out / "book-text-问题.txt").write_text(str(r.get("why")) + "\n" + "\n".join(r.get("problems") or []), encoding="utf-8")
                return {"status": "book-text-" + r["status"], "why": r.get("why"), "rev": rev}
            info.update(status=r["status"], commit=r.get("commit"), pr=r.get("pr"), branch=r.get("branch"))
            info["landed"] = {x[0]: x[2] for x in plan["apply"]}
            info["ai_landed"] = {x[0]: x[3] for x in plan["apply"] if x[3].startswith("AI")}
        landed = info["landed"]
        # AI 落的格不在单上结案：用户之后投票仍以票为准（下一轮重放后这格自然不再待审）
        info["batch_cells"] = {x[0]: x[3] for x in plan["apply"] + plan["already"] if x[3] != "票" and not x[3].startswith("AI")}
        info["batch_cells"].update({a_: "票与已有人裁一致" for a_ in same_ids if a_ in want})   # 现行生效的才结案
        if a.dry_run:
            print(f"  --dry-run 到此为止：book-text 改动提交在 {wt}（没推），计划见 {out / '落文本.json'}")
            return {"status": "dry-run", "rev": rev, "plan": info["plan"], "worktree": str(wt)}
        R.mark("book-text", info, t)

    # 5. --batch 落的格：单上还开着的条目结案（票的条目 write 已结）
    if R.done("resolve"):
        R.skip("resolve")
    else:
        t = time.time()
        bc = R.st["done"]["book-text"]["info"].get("batch_cells") or {}
        n = resolve_items(ws, text_id, ch, {a_: "" for a_ in bc}, by=a.reviewer, why=f"收单 {rev}：早先人裁已落文本") if bc else 0
        R.mark("resolve", {"n": n}, t)

    # 6. 推库（只一次）
    if R.done("sync"):
        R.skip("sync")
    else:
        t = time.time()
        if _run([*GUJI, "db", "sync", "-w", ws], env, tries=4):
            return {"status": "blocked", "why": "guji db sync 四次都失败，原命令再跑会从推库接着做", "rev": rev}
        R.mark("sync", None, t)

    # 7. 只发这一章，核线上单（多册时由 cmd_collect 最后一起发一次，见 publish_and_verify）
    if a.no_publish:
        print("  --no-publish：不触发网站发布（每日 proofing-sync 兜底）")
        return {"status": "synced", "rev": rev, "landed": len(landed)}
    if getattr(a, "_defer_publish", False):
        return {"status": "to-publish", "rev": rev, "landed": len(landed)}
    return publish_and_verify(a, ws, [book])[book]


def _state_of(ws: Path, text_id: str, book: str) -> tuple[Path, "Run", Path] | None:
    from .datastore.workcopy import data_dir
    sheet_p = data_dir(ws) / "feedback" / "lists" / "proofing" / text_id / f"{chapter_of(book)}.pending.json"
    if not sheet_p.exists():
        return None
    rev = json.loads(sheet_p.read_text(encoding="utf-8")).get("rev")
    return sheet_p, Run(ws / "reports" / book / "_collect" / rev / "state.json", False), ws / "reports" / book / "_collect" / rev


def verify_book(a, ws: Path, book: str, R: "Run", sheet_p: Path) -> dict:
    """线上单与本地单同 rev，且本地已结的格线上不再待审。"""
    text_id, ch = a.text_id, chapter_of(book)
    t = time.time()
    local = json.loads(sheet_p.read_text(encoding="utf-8"))
    rev = local.get("rev")
    landed = ((R.st["done"].get("book-text") or {}).get("info") or {}).get("landed") or {}
    want_open = live_open_cells(local)
    live = live_sheet(text_id, ch)
    if live is None:
        return {"status": "verify-fail", "why": "读不到线上单", "rev": rev}
    got_open = live_open_cells(live)
    bad = sorted(got_open - want_open, key=_key)
    if live.get("rev") != rev or bad:
        return {"status": "verify-fail", "rev": rev,
                "why": f"线上 {live.get('rev')}／本地 {rev}；线上仍待审而本地已结 {len(bad)} 格 {bad[:8]}（发站慢就过几分钟原命令再跑一次）"}
    R.mark("verify", {"open": len(got_open)}, t)
    total = round(sum(v.get("s", 0) for v in R.st["done"].values()), 1)
    print(f"  ✓ {book} {rev}：book-text 落 {len(landed)} 格，线上单还剩待审 {len(got_open)} 格；计时 {total} s")
    return {"status": "done", "rev": rev, "landed": len(landed), "open": len(got_open), "seconds": total}


def publish_and_verify(a, ws: Path, books: list[str]) -> dict:
    """这些册一起触发一次 proofing-sync（``only=`` 多章；分开触发会互相取消），等跑完逐册核线上单。
    发布没成不算失败：单子已在中心库，每日定时发布兜底；云端 gh 没鉴权时 trigger-fail（ZM 11-19）。"""
    from .swap import publish_batch
    st = {b: _state_of(ws, a.text_id, b) for b in books}
    todo = [b for b in books if st[b] and not st[b][1].done("publish")]
    if todo:
        t = time.time()
        concl = publish_batch(todo, a.text_id)
        if concl != "success":
            only = ",".join(f"{a.text_id}/{chapter_of(b)}" for b in todo)
            print(f"⚠ 网站发布没成（{concl}）：手动触发 kaiyuanguji-web proofing-sync.yml（target=production、parts=publish、"
                  f"only={only}），再原命令跑一次核线上；不管它，每日定时发布也会带上")
            return {b: {"status": "synced", "publish": str(concl)} for b in books}
        for b in todo:
            st[b][1].mark("publish", {"conclusion": concl}, t)
    out = {}
    for b in books:
        if not st[b]:
            out[b] = {"status": "verify-fail", "why": "数据目录没有线上单"}
            continue
        sheet_p, R, _ = st[b]
        out[b] = verify_book(a, ws, b, R, sheet_p)
    return out


def books_with_votes(votes: list[dict], open_of) -> list[str]:
    """网站条目票 → 有票落在还开着的条目上的册（``open_of(章)`` 给这一章开着的条目 id 集合）。按册序。"""
    chaps = sorted({str(v.get("vol") or "").zfill(3) for v in votes if v.get("vol") and v.get("item")})
    out = []
    for ch in chaps:
        live = open_of(ch)
        if any(v.get("item") in live for v in votes if str(v.get("vol") or "").zfill(3) == ch):
            out.append(f"vol{int(ch):02d}")
    return out


def auto_books(ws: Path, text_id: str) -> list[str]:
    """``--books auto``：读一遍网站条目票（KV），挑出有票落在还开着的条目上的册（ZM 11-19：不知道哪些册有新票，
    只能全拉自己比）。要 CELLREVIEW_TOKEN；先拉库，条目以库为准。"""
    from .cli_cellvotes import _fetch_kv_items
    from .datastore.workcopy import data_dir
    from .review import pending_items as P
    tok = os.environ.get("CELLREVIEW_TOKEN")
    if not tok:
        raise SystemExit("--books auto 要读网站票：设 CELLREVIEW_TOKEN")
    votes = _fetch_kv_items(text_id, tok)
    data = data_dir(ws)

    def open_of(ch: str) -> set[str]:
        st = P.ItemStore.open(data, text_id, ch)
        return {r["id"] for r in st.by_state("open", "withdrawn")}
    books = books_with_votes(votes, open_of)
    print(f"网站条目票 {len(votes)} 条；有票落在开着的条目上的册：{'、'.join(books) or '没有'}")
    return books


def cmd_collect(a) -> int:
    ws = Path(a.workspace).resolve()
    os.environ["GUJI_WORKSPACE"] = str(ws)
    if a.books == "auto":
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        if not a.no_pull and _run([*GUJI, "db", "pull", "-w", ws], env, tries=3):
            raise SystemExit("guji db pull 失败")
        a.no_pull = True                       # 各册不再各拉一次
        books = auto_books(ws, a.text_id)
    else:
        books = parse_books(a.books)
    a._defer_publish = len(books) > 1 and not a.dry_run
    res = {b: collect_book(a, ws, b) for b in books}
    ready = [b for b, v in res.items() if v["status"] == "to-publish"]
    if ready:
        print(f"\n== 发站：{'、'.join(ready)} 一起发一次，再逐册核线上单")
        res.update(publish_and_verify(a, ws, ready))
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if all(v["status"] in ("done", "synced", "dry-run") for v in res.values()) else 2


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("collect", help="收单快路：读票→写人裁→定字直接落 book-text（不重放）→KV 结案→pull/sync 各一次→发站核对（断点续跑）")
    p.add_argument("--books", required=True, help="如 vol20 或 vol20-vol25（逐册做）；auto＝读网站条目票，挑有票落在开着的条目上的册")
    p.add_argument("-w", "--workspace", required=True)
    p.add_argument("--book-text", required=True, help="book-text 检出（在它旁边建 <检出>-collect worktree，每册重置到 origin/dev）")
    p.add_argument("--worktree", default=None, help="book-text worktree 路径（缺省 <book-text>-collect）")
    p.add_argument("--text-id", default=DIANBEN_ID, help="book-text 书 ID（缺省殿本）")
    p.add_argument("--reviewer", default=os.environ.get("GUJI_REVIEWER", "sheldon"), help="裁决人（网站投票的人；缺省 sheldon）")
    p.add_argument("--batch", action="append", default=None,
                   help="另把早先写进库、还没进 book-text 的人裁批次也落了（可重复；只认人裁，过绑定表、每格取最新）")
    p.add_argument("--pack", default=None, help="出单版产物包标签（缺省 rev-<rev>，没有就 ★main）")
    p.add_argument("--no-pull", action="store_true", help="不先拉库（刚拉过）")
    p.add_argument("--no-push", action="store_true", help="book-text 只提交在 worktree，不推")
    p.add_argument("--no-publish", action="store_true", help="推库后不触发网站发布、不核线上")
    p.add_argument("--fresh", action="store_true", help="不认上次的进度，从头做")
    p.add_argument("--no-ai", action="store_true",
                   help="不落 AI 裁定（缺省会把出单版包里仍待审、裁定库按窗口命中的高把握文意裁定和可放行的终审看图裁定一起直接写 book-text；人裁优先）")
    p.add_argument("--dry-run", action="store_true", help="只拉库、读票出草稿、算要落哪些格并在 worktree 里提交 book-text（不推）；不写人裁、不推库、不发站")


def cmd(args) -> None:
    raise SystemExit(cmd_collect(args))


COMMANDS = {"collect": (add_parser, cmd)}
