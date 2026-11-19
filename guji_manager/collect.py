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


def _run(cmd: list, env: dict) -> int:
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], env=env).returncode


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


def batch_chars(book: str, batches: list[str], products_root: str | None) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """``--batch`` 点名的人裁批次 → {现行格: (字, 批次)}：每格只认最新一条人裁，且要过绑定表（valid／rebound）。
    返回 (格→字, 没认上的说明)。"""
    if products_root:
        os.environ["GUJI_PRODUCTS_DIR"] = products_root
    from ._cv import EventLog, feedback_root, book_bindings, bindings_usable
    from .feedback.web_votes import latest_human
    evs = list(EventLog(feedback_root()).iter_all())
    last = latest_human(evs)
    pick = {k: e for k, e in last.items() if getattr(e, "batch", None) in batches and k.startswith(f"{book}:")
            and (e.payload or {}).get("v") == "confirm" and (e.payload or {}).get("shape")
            and not (e.payload or {}).get("unk")}
    if not pick:
        return {}, [f"批次 {','.join(batches)} 里没有 {book} 的最新定字人裁（或已被后来的人裁盖过）"]
    pages = sorted({int(bare(k).split(":")[0]) for k in pick})
    try:
        rows = book_bindings(book, pages=pages)
    except Exception as e:  # noqa: BLE001
        return {}, [f"绑定表算不出来（{type(e).__name__}: {e}），这些批次不落；先 guji db pull 并确认产物根有本册 Step3"]
    out, miss = {}, []
    for k, e in pick.items():
        cell = bindings_usable(rows.get(e.id), e.ts)
        if not cell:
            miss.append(f"{bare(k)}「{e.payload['shape']}」绑定 {(rows.get(e.id) or {}).get('status', '无')}，不落")
            continue
        newer = last.get(cell if ":" in cell and cell.startswith(book) else f"{book}:{bare(cell)}")
        if newer is not None and newer.id != e.id and newer.ts > e.ts:
            miss.append(f"{bare(cell)} 有更新的人裁，批次里的不落")
            continue
        out[bare(cell)] = (e.payload["shape"], e.batch)
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
        if _run([*GUJI, "db", "pull", "-w", ws], env):
            return {"status": "blocked", "why": "guji db pull 失败"}
    if not sheet_p.exists():
        return {"status": "blocked", "why": f"数据目录没有线上单 {sheet_p}"}
    rev = json.loads(sheet_p.read_text(encoding="utf-8")).get("rev")
    out = ws / "reports" / book / "_collect" / rev
    R = Run(out / "state.json", a.fresh or a.dry_run, a.dry_run)
    if R.done("verify") and not a.fresh:
        print(f"  {rev} 上次已收完（{out / 'state.json'}）；要重来加 --fresh")
        return {"status": "done", "rev": rev, "again": True}
    R.mark("pull", {"rev": rev}, t)

    # 2–3. 读票、落人裁
    draft = out / "draft"
    batch = f"H-web-{book}-{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')}-{rev}"
    if R.done("draft"):
        R.skip("draft")
        pack, batch = R.st["done"]["draft"]["info"]["pack"], R.st["done"]["draft"]["info"]["batch"]
    else:
        t = time.time()
        pack = a.pack or _pack_for(book, rev)
        cmd = [*GUJI, "cellvotes", "draft", book, "--site-book", text_id, "--rev", rev, "--out", draft, "-w", ws,
               "--from-kv", "--items"]
        cmd += ["--pack", pack] if pack else ["--no-box-check"]
        if a.batch:
            cmd += ["--allow-empty"]          # 只落早先批次时单上可能 0 票
        if _run(cmd, env):
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
            if _run([*GUJI, "cellvotes", "write", book, draft, "--batch", batch, "--reviewer", a.reviewer, "-w", ws], env):
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
        want = vote_chars(draft)
        notes = []
        if a.batch:
            got, miss = batch_chars(book, a.batch, meta.get("products_root"))
            notes += miss
            for k, v in got.items():
                want.setdefault(k, v)              # 本次的票更新，盖过早先批次
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
            srcs = sorted({x[3] for x in plan["apply"]})
            note = (f"{book} 收单 {rev}：人裁定字直接落 {len(plan['apply'])} 格（{'、'.join(srcs)}），不重放"
                    + (f"；批次 {batch}" if meta.get("ready") else ""))
            title = f"{book}：收单 {rev} 人裁定字 {len(plan['apply'])} 格直接落文本（patch）"
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
        landed = info["landed"]
        info["batch_cells"] = {x[0]: x[3] for x in plan["apply"] + plan["already"] if x[3] != "票"}
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
        for i in range(3):
            if _run([*GUJI, "db", "sync", "-w", ws], env) == 0:
                break
            time.sleep(10 * (i + 1))          # StaleBase／断连：重跑即可
        else:
            return {"status": "blocked", "why": "guji db sync 三次都失败，原命令再跑会从推库接着做", "rev": rev}
        R.mark("sync", None, t)

    # 7. 只发这一章，核线上单
    if a.no_publish:
        print("  --no-publish：不触发网站发布（每日 proofing-sync 兜底）")
        return {"status": "synced", "rev": rev, "landed": len(landed)}
    if R.done("publish"):
        R.skip("publish")
    else:
        t = time.time()
        from .swap import publish_batch
        concl = publish_batch([book], text_id)
        R.mark("publish", {"conclusion": concl}, t)
        if concl != "success":
            return {"status": "publish-" + str(concl), "rev": rev, "landed": len(landed)}
    t = time.time()
    local = json.loads(sheet_p.read_text(encoding="utf-8"))
    want_open = live_open_cells(local)
    live = live_sheet(text_id, ch)
    if live is None:
        return {"status": "verify-fail", "why": "读不到线上单", "rev": rev}
    got_open = live_open_cells(live)
    bad = sorted(got_open - want_open, key=_key)
    if live.get("rev") != local.get("rev") or bad:
        return {"status": "verify-fail", "rev": rev,
                "why": f"线上 {live.get('rev')}／本地 {local.get('rev')}；线上仍待审而本地已结 {len(bad)} 格 {bad[:8]}（发站慢就过几分钟再跑一次）"}
    R.mark("verify", {"open": len(got_open)}, t)
    total = round(sum(v.get("s", 0) for v in R.st["done"].values()), 1)
    print(f"  ✓ {book} {rev}：book-text 落 {len(landed)} 格，线上单还剩待审 {len(got_open)} 格；计时 {total} s")
    return {"status": "done", "rev": rev, "landed": len(landed), "open": len(got_open), "seconds": total}


def cmd_collect(a) -> int:
    ws = Path(a.workspace).resolve()
    res = {b: collect_book(a, ws, b) for b in parse_books(a.books)}
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if all(v["status"] in ("done", "synced", "dry-run") for v in res.values()) else 2


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("collect", help="收单快路：读票→写人裁→定字直接落 book-text（不重放）→KV 结案→pull/sync 各一次→发站核对（断点续跑）")
    p.add_argument("--books", required=True, help="如 vol20 或 vol20-vol25（逐册做）")
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
    p.add_argument("--dry-run", action="store_true", help="只拉库、读票出草稿、算要落哪些格并在 worktree 里提交 book-text（不推）；不写人裁、不推库、不发站")


def cmd(args) -> None:
    raise SystemExit(cmd_collect(args))


COMMANDS = {"collect": (add_parser, cmd)}
