"""收单快路：``guji collect``——用户在网站投完一张单，人裁直接落进 book-text、KV／中心库，不重放、不重出单。

ZM 第一册线（11-17、11-19）实测：收一张单净计算不到 5 分钟，总耗时 20 分钟到 2 小时，大头是 3–5 次 pull/sync 和
等任务库从 seed_admit 重放（人裁只有重放后才进产物，再导出才进 book-text）。可 book-text 只录首选字（sheldon 11-09），
人裁定了字，book-text 那一格该是什么字已经知道了，不必等重放：

1. ``db pull`` 一次（增量）。
2. 读线上单：rev、出单版产物包（``rev-<rev>``，没有就退到 ★main 包）。
3. ``cellvotes draft --from-kv --items --pack``（读票、出草稿；挂起照旧）→ ``cellvotes write``（写人裁事件、落了票的条目标已裁、
   条目标已裁）。批次名 ``H-web-<册>-<日期>-<时分>``。
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

**一条命令落网站人审（GM4 11-23，用户定）**：``guji feedback collect -w <工作区> --book-text <检出>``（``--books`` 缺省 auto：读收件箱，
挑有票落在开着条目上的册）。全自动，除「特殊需要分析」「待定」的票（挂起、切分类、推翻旧裁、格位变了、条目 fp_changed／撤下的旧单票、
策略要多人而没到的格）——这些留在 held／old_sheet／waiting 里不落。旧单（vote_rev≠现行 rev）上投的条目票，条目图没变就按条目现格落，
永远新结果覆盖旧的。落票策略 ``--policy``（缺省 auto；quorum:N 按审阅人会员身份分流，接口见 feedback/landing_policy.py）。
命令末尾打票账（每册：收件箱票→有效→旧单→等多人→写人裁→挂起→book-text 写／已一致／等重放），同存 ``reports/_collect/runs/<本趟>.ledger.tsv``。
批量落：每册一趟只做一个 book-text 提交；建议每半小时跑一次（没新票的册 auto 自动跳过）。

``guji collect --books vol20 -w <工作区> --book-text <book-text 检出> [--reviewer sheldon] [--batch <早先人裁批次> …]``
"""
from __future__ import annotations
from .products_io import decide_dir
from .products_io import decide_pages, layer

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .swap import DIANBEN_ID, SITE_PENDING, chapter_of, parse_books

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


def ai_ruling_chars(products_root, book: str, store=None, members=None,
                    rekey: list | None = None) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """AI 裁定可直接落文本的格 {格（无册前缀）: (字, 来源)}（用户 2026-11-20 定：AI 裁定像人裁一样直接写 book-text，不等重放）。

    只认出单版包里**仍待审**的格，且裁定确定对得上这一格：
    - 文意（L3 组）：这格的 ask 窗口在裁定库里**按窗口命中**（与重放 seed_admit 同一把键），``conf=high``、字在组内、不是「其他」；
    - 终审／看图（group=O，``vis-o1``/``src-1``/``ctx-m1``）：按格号取最新一条，``conf=high``、``admit_ok``、有字，
      且裁定时的整理本对位字与包里现在的一样；夹注半格（格号带 a／b）不落（seed_admit 缺省也不放）。
    人裁优先由调用方处理（有现行人裁的格不用这里的字）。

    ``rekey`` 给了列表：文意裁定按窗口键没命中、但这格最新一条裁定**窗口与 ask 相同**、只是提示词版本（含模型后缀）或字组名变了
    （ZM 11-21 殿本未命中 395 格里约 210 格是这种），也照上面的条件落，并把 ``(ask, 原裁定)`` 记进列表，由调用方按现行
    组／版本补写一条（下次重放即命中）。窗口不同的仍不认。"""
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

    for f in sorted(decide_pages(root)):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for col in (layer(doc).get("columns") or []):
            for c in col.get("chars") or []:
                if c.get("id") and not c.get("admit") and mine(c["id"]):
                    pending.add(c["id"])
        asks += [q for q in llm_questions_of_page(doc) if q.get("cell") and mine(q["cell"])]
    by_cell: dict[str, dict] = {}
    if store.log.events_dir.exists():
        from .ruling_hits import _rulings_by_cell
        from ._cv import ruling_ctx_hash
        by_cell = {k: v for k, v in _rulings_by_cell(store).items() if v.get("group") != "O" and mine(k)}
    asked: set[str] = set()
    for q in asks:
        if q["cell"] not in pending:
            continue
        v = store.get(q["group"], q["ver"], q["l"], q["r"])
        cross = False
        if v is not None:
            asked.add(q["cell"])
        if v is None and rekey is not None and q["cell"] in by_cell:
            r0 = by_cell[q["cell"]]
            c0 = r0.get("ctx") or {}
            if ruling_ctx_hash(c0.get("left", ""), c0.get("right", "")) == ruling_ctx_hash(q["l"], q["r"]):
                v, cross = r0, True
        if not v or v.get("other") or not v.get("char") or v.get("char") in PLACEHOLDERS:
            continue
        if v.get("conf") != "high":
            notes.append(f"{bare(q['cell'])} 文意裁定「{v.get('char')}」把握 {v.get('conf')}，不直接落")
            continue
        if members.get(q["group"]) and v["char"] not in members[q["group"]]:
            notes.append(f"{bare(q['cell'])} 文意裁定「{v['char']}」不在组 {q['group']} 内，不落")
            continue
        if cross:
            if bare(q["cell"]) in out:
                continue
            rekey.append((q, v))
            asked.add(q["cell"])
            out[bare(q["cell"])] = (v["char"], f"AI文意/{q['group']}/改版重键")
        else:
            out.setdefault(bare(q["cell"]), (v["char"], f"AI文意/{q['group']}"))
    if not store.log.events_dir.exists():
        return out, notes
    # 按格写的文意裁定（ZM write_ctx_ruling_by_cell：「格号＋字」、自算窗口）：这格 seed_admit 没记 ask
    # （字组没进：分差内有组外字，如 兩雨 格候选里的 而／南），或 ask 窗口与裁定窗口不完全一样 → 上面按窗口键取不到，
    # 以前静默跳过（ZM 11-21 vol28/36/98 兩雨、vol55 閔 landed 0）。现在按格号取最新一条，核对窗口大体一致再落。
    # 有 ask 但组／提示词版本不同的格归上面的改版重键路（rekey），这里不管
    ask_of: dict[str, dict] = {}
    for q in asks:
        ask_of.setdefault(q["cell"], {})[(q["group"], q["ver"])] = q
    rest = {k: v for k, v in by_cell.items() if k in pending and k not in asked and bare(k) not in out
            and (k not in ask_of or (v.get("group"), v.get("prompt_ver")) in ask_of[k])}
    if rest:
        _cell_rulings(root, rest, asks, members, out, notes)
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
        if not (v.get("char") and not v.get("other")) or v["char"] in PLACEHOLDERS:
            continue
        if v.get("conf") != "high" or not v.get("admit_ok"):
            notes.append(f"{bare(k)} 终审裁定「{v['char']}」{v.get('prompt_ver')} 把握 {v.get('conf')}、admit_ok={v.get('admit_ok')}，不直接落")
            continue
        if re.search(r"[ab]$", k):
            notes.append(f"{bare(k)} 看图裁定「{v['char']}」是夹注半格，不直接落")
            continue
        if (v.get("ref") or "") != ref.get(k, ""):
            notes.append(f"{bare(k)} 看图裁定「{v['char']}」时整理本对位字 {v.get('ref') or '空'}，现 {ref.get(k) or '空'}，不落")
            continue
        out[bare(k)] = (v["char"], f"AI看图/{v.get('prompt_ver')}")
    return out, notes


#: 按格写的文意裁定：裁定窗口与包里这格现在的窗口，格两边各这么多字必须一样，整体相似度不低于下面的比例
CELL_RULING_NEAR = 2
CELL_RULING_RATIO = 0.8


def _window_ok(rl: str, rr: str, pl: str, pr: str) -> tuple[bool, str]:
    """裁定窗口 (rl, rr) 与产物窗口 (pl, pr) 大体一致：紧邻格的字一样、整体相似度够（邻格放行字小变不算换了地方）。"""
    import difflib
    rl, rr, pl, pr = (rl or "")[-20:], (rr or "")[:20], (pl or "")[-20:], (pr or "")[:20]
    n = CELL_RULING_NEAR
    if rl[-n:] != pl[-n:] or rr[:n] != pr[:n]:
        return False, f"紧邻字不同（裁定 {rl[-n:]}｜{rr[:n]}，现 {pl[-n:]}｜{pr[:n]}）"
    ratio = difflib.SequenceMatcher(None, rl + "|" + rr, pl + "|" + pr, autojunk=False).ratio()
    if ratio < CELL_RULING_RATIO:
        return False, f"窗口相似度 {ratio:.2f} < {CELL_RULING_RATIO}"
    return True, ""


def _cell_rulings(root: Path, rest: dict, asks: list, members: dict, out: dict, notes: list) -> None:
    """``ai_ruling_chars`` 的第三路：按格号取的文意裁定（非 group=O）。条件：``conf=high``、有字、不是「其他」；
    裁定字是这格整理本字、库候选或裁定组的组员之一；裁定窗口与包里这格的窗口大体一致（`_window_ok`；有 ask 用 ask 窗口，
    没有按 5c 口径现算）。落了也不会让下一次重放命中（seed_admit 不按格取裁定），所以照样记 AI 来源、单上条目不结案。"""
    from .ruling_hits import _vis_window
    by_page: dict[str, list[str]] = {}
    for k in rest:
        parts = k.split(":")
        if len(parts) == 4:
            by_page.setdefault(f"p{int(parts[1]):04d}.json", []).append(k)
    win = {q["cell"]: (q["l"], q["r"]) for q in asks
           if q["cell"] in rest and (q["group"], q["ver"]) == (rest[q["cell"]].get("group"), rest[q["cell"]].get("prompt_ver"))}
    refs: dict[str, str] = {}
    cands: dict[str, set] = {}
    for fn, ks in by_page.items():
        amap: dict[str, str] = {}
        try:
            ar = json.loads((root / "align_ref" / fn).read_text(encoding="utf-8")).get("align_ref", {})
            anchored = ar.get("anchored", True) is not False
            for c in ar.get("chars") or []:
                if c.get("id"):
                    if anchored:
                        amap[c["id"]] = c.get("align_char") or ""
                    if c["id"] in rest:
                        refs[c["id"]] = c.get("align_char") or ""
        except (OSError, ValueError):
            pass
        try:
            gm = json.loads((root / "glyph_match" / fn).read_text(encoding="utf-8"))
            stack = [gm]
            while stack:
                o = stack.pop()
                if isinstance(o, dict):
                    if o.get("id") in rest and isinstance(o.get("candidates"), list):
                        cands[o["id"]] = {c[0] for c in o["candidates"][:5] if c}
                    stack += [x for x in o.values() if isinstance(x, (dict, list))]
                elif isinstance(o, list):
                    stack += [x for x in o if isinstance(x, (dict, list))]
        except (OSError, ValueError):
            pass
        need = [k for k in ks if k not in win]
        if need:
            try:
                doc = json.loads((decide_dir(root) / fn).read_text(encoding="utf-8"))
                w = _vis_window(doc, amap)
                for k in need:
                    if k in w:
                        win[k] = (w[k][1], w[k][2])
            except Exception:  # noqa: BLE001
                pass
    for k, v in sorted(rest.items()):
        ch, g = v.get("char"), v.get("group")
        if not ch or v.get("other") or ch in PLACEHOLDERS:
            continue
        tag = f"{bare(k)} 按格文意裁定「{ch}」（{g}/{v.get('prompt_ver')}）"
        if v.get("conf") != "high":
            notes.append(f"{tag}把握 {v.get('conf')}，不直接落")
            continue
        ok_chars = {refs.get(k) or ""} | cands.get(k, set()) | set(members.get(g) or ())
        if ch not in ok_chars:
            notes.append(f"{tag}不是整理本字、库前五或组员，不落")
            continue
        if k not in win:
            notes.append(f"{tag}：算不出包里这格的窗口，不落")
            continue
        c0 = v.get("ctx") or {}
        ok, why = _window_ok(c0.get("left", ""), c0.get("right", ""), *win[k])
        if not ok:
            notes.append(f"{tag}与包里窗口对不上（{why}），不落")
            continue
        out[bare(k)] = (ch, f"AI文意/{g}/按格")


def write_rekeys(book: str, rk: list, batch: str | None = None) -> int:
    """``ai_ruling_chars(rekey=…)`` 收的 (ask, 原裁定)：按 ask 的现行组、提示词版本、窗口另写一条（字、把握、模型照抄，
    why 前缀 rekey）。只追加裁定事件，随本册 ``db sync`` 推库。"""
    import inspect
    from ._cv import RulingStore
    from .u_stamp import u_of
    store = RulingStore()
    has_u = "u" in inspect.signature(store.put).parameters        # cv #1848 起 put 收 u（字格永久编号，T2）
    store._batch = batch or f"llm-rekey-collect-{book}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M')}"
    for q, v in rk:
        store.put(q["group"], q["ver"], q["l"], q["r"], char=v["char"], conf=v.get("conf"),
                  why=("rekey:" + (v.get("why") or ""))[:60], model=v.get("model") or "session", cell=q["cell"],
                  pending_reason=v.get("pending_reason"),
                  **({"u": u} if has_u and (u := u_of(q["cell"])) is not None else {}))
    return len(rk)


def live_open_cells(doc: dict) -> set[str]:
    """线上单里还待审的格（``review`` 不是 human）。"""
    return {bare(c["cell"]) for c in doc.get("cells") or [] if c.get("cell") and c.get("review", "pending") != "human"}


# ───────────────────────── 状态 ─────────────────────────

RUN_KEY = "items"      # 状态目录键（原为整张单的 rev；整张单已撤，11-28）

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


#: 上一条 ``_run`` 输出的末几行（失败时并进 why，原因落到册内哪格；ZM 11-21 vol78 BadRequest、vol21 旧格号票只见「失败」）
_TAIL: list[str] = []


def _run(cmd: list, env: dict, tries: int = 1) -> int:
    """跑一条 guji 命令。``tries``>1 只给幂等的步（拉库、读票、落票带幂等键、推库）：网络读超时（R2／中心库 SSL timeout、
    StaleBase、断连）在这一步里重试，不让整册重来（ZM 11-19 B 轮 vol14／18）。输出照常打出，另留末 40 行在 ``_TAIL``。"""
    import collections
    rc = 1
    for i in range(tries):
        print("  $ " + " ".join(str(c) for c in cmd) + (f"   （第 {i + 1} 次）" if i else ""), flush=True)
        tail: collections.deque = collections.deque(maxlen=40)
        p = subprocess.Popen([str(c) for c in cmd], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace")
        for line in p.stdout:
            sys.stdout.write(line)
            tail.append(line.rstrip("\n"))
        rc = p.wait()
        _TAIL[:] = list(tail)
        sys.stdout.flush()
        if rc == 0:
            return 0
        if i < tries - 1:
            time.sleep(10 * (i + 1))
    return rc


def _why(msg: str) -> str:
    """失败原因带上命令输出里最后几行要紧的（报错行、带格号的行），没有就最后 3 行。"""
    keys = ("Error", "错误", "失败", "Exception", "BadRequest", "rev", "格", ":")
    hit = [ln.strip() for ln in _TAIL if ln.strip() and any(k in ln for k in keys)][-4:]
    hit = hit or [ln.strip() for ln in _TAIL if ln.strip()][-3:]
    return msg + ("｜" + "｜".join(x[:240] for x in hit) if hit else "")


# ───────────────────────── 各步 ─────────────────────────

def _pack_for(book: str) -> str | None:
    """出单版包：★main（没有整张单了，不再有 ``rev-<rev>`` 包）。取不到返回 None。"""
    try:
        from .datastore import packs as PK
        return PK.main_label(book, PK._client())
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


def current_human(book: str, products_root: str | None, pages: list[int] | None = None) -> dict[str, str]:
    """现行人裁 {格（无册前缀）: 字}：cv ``feedback.lookup.human_chars``（seed_admit 人裁通道同一口径），绑定按
    ``products_root``（出单版包）算。出错就抛，不退回按格号。"""
    if products_root:
        os.environ["GUJI_PRODUCTS_DIR"] = products_root
    from ._cv import human_chars
    try:                    # 只重绑票涉及的页（全书重绑 QTW 004 要 30 多分钟）；旧版 cv 没有 pages 参数就退回全书
        raw = human_chars(book, pages=pages) if pages else human_chars(book)
    except TypeError:
        raw = human_chars(book)
    return {bare(k): c for k, c in raw.items() if c and k.startswith(f"{book}:")}


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


def batch_u_cells(book: str, batches: list[str], char: dict) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """``--batch`` 里「只给 u 锚、没有页表锚」的人裁事件（target.anchor={"u":N}、page/col/slot 空）：
    绑定表按「页:列:格」认锚，这类事件判 unanchored 落不进去（11-27 全唐文寇/𡨥 213、市 98）。
    这里改按 u 直接在 book-text ``*.char.json`` 里查格（u 是册内永久格号，真源就在这份文件里）。
    每个 u 取批次内最新一条（replay_key，后到覆盖）；查不到或多于一格就不落并列出；返回 ({格号: (字, 批次)}, 说明)。"""
    from ._cv import EventLog, feedback_root, replay_key
    evs = [e for e in EventLog(feedback_root()).iter_all() if getattr(e, "batch", None) in batches
           and e.kind == "confirm" and e.target.unit == "cell" and e.target.key.startswith(f"{book}:")
           and isinstance(e.target.anchor, dict) and e.target.anchor.get("u") is not None
           and e.target.page is None and e.target.col is None and e.target.slot is None
           and e.payload.get("level", "human") == "human" and (e.payload.get("shape") or "").strip()]
    if not evs:
        return {}, []
    latest: dict[int, object] = {}
    for e in sorted(evs, key=replay_key):
        latest[int(e.target.anchor["u"])] = e
    index: dict[int, list[str]] = {}
    for pg in char.get("pages") or []:
        for col in pg.get("columns") or []:
            for c in col.get("cells") or []:
                if c.get("u") is not None:
                    index.setdefault(int(c["u"]), []).append(c["a"])
    out: dict[str, tuple[str, str]] = {}
    notes: list[str] = []
    for u, e in latest.items():
        hit = index.get(u) or []
        if len(hit) != 1:
            notes.append(f"u={u}（事件 {bare(e.target.key)}）在 book-text 里查到 {len(hit)} 格，不落")
            continue
        out[hit[0]] = (str(e.payload["shape"]).strip(), e.batch)
    return out, notes


def resolve_items(ws: Path, text_id: str, chapter: str, cells: dict[str, str], by: str, why: str) -> int:
    """这些格还开着的条目标已裁（只改条目，不再导整张单）。返回标了几条。"""
    from .datastore.workcopy import data_dir
    from .review import pending_items as P
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
    return n


def live_pending(text_id: str, chapter: str) -> dict | None:
    """读者侧网站 ``/api/pending``：由条目现拼，只含开着、没落定的格。"""
    try:
        with urllib.request.urlopen(SITE_PENDING.format(text_id=text_id, n=int(chapter)) + f"&x={int(time.time())}", timeout=30) as r:
            return json.load(r)
    except Exception:  # noqa: BLE001
        return None


def collect_book(a, ws: Path, book: str) -> dict:
    """收一册；收完（不论要不要发站）把这册的出单版包解出来的目录删掉腾盘（``--keep-pack`` 留着），
    省得每册前手工 ``rm -rf _packs/*``（ZM 11-21）。

    ``GUJI_ALLOW_LOST_HUMAN_BOOKS=vol01,vol20``：只对列出的册放行「丢人裁超上限」（等于这几册设
    ``GUJI_ALLOW_LOST_HUMAN=1``，用户 11-23 定 vol01／vol20 可以），别的册不受影响；定时任务用它。"""
    allow = {x.strip() for x in os.environ.get("GUJI_ALLOW_LOST_HUMAN_BOOKS", "").split(",") if x.strip()}
    had = os.environ.get("GUJI_ALLOW_LOST_HUMAN")
    if book in allow:
        os.environ["GUJI_ALLOW_LOST_HUMAN"] = "1"
    try:
        return _collect_book_guarded(a, ws, book)
    finally:
        if book in allow:
            if had is None:
                os.environ.pop("GUJI_ALLOW_LOST_HUMAN", None)
            else:
                os.environ["GUJI_ALLOW_LOST_HUMAN"] = had


def _collect_book_guarded(a, ws: Path, book: str) -> dict:
    try:
        res = _collect_book(a, ws, book)
    except Exception as e:  # noqa: BLE001 —— 并行时一册出错不拖垮别的册；原因落进结果
        import traceback
        traceback.print_exc()
        res = {"status": "blocked", "why": f"{type(e).__name__}: {str(e)[:400]}"}
    root = (getattr(a, "_pack_roots", None) or {}).get(book)
    if root and not getattr(a, "keep_pack", False) and res.get("status") in ("done", "synced", "to-publish", "to-sync"):
        d = Path(root) / book
        if "_packs" in Path(root).parts and d.is_dir():
            import shutil
            shutil.rmtree(d, ignore_errors=True)
            print(f"  已删本册出单版包解出的目录 {d}（--keep-pack 留）")
    return res


def _collect_book(a, ws: Path, book: str) -> dict:
    from .datastore.workcopy import data_dir
    from .online_lists import book_text_dir
    text_id, ch = a.text_id, chapter_of(book)
    os.environ["GUJI_WORKSPACE"] = str(ws)        # 本进程里取包、读事件、核格框也认这个工作区
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    env.setdefault("GUJI_ACTOR", "collect")
    print(f"\n== {book}（{text_id}/{ch}）")

    # 1. 拉库（只一次）：条目、事件以库为准。没有整张单了：状态目录用固定键 RUN_KEY（一趟收完 verify 后旧进度留底、下趟从头）
    t = time.time()
    rev = RUN_KEY
    out = ws / "reports" / book / "_collect" / rev
    pre_state = out / "state.json"
    if not a.no_pull and not (not a.fresh and "pull" in _load_state(pre_state).get("done", {})
                               and "sync" not in _load_state(pre_state)["done"]):
        if _run([*GUJI, "db", "pull", "-w", ws], env, tries=3):
            return {"status": "blocked", "why": _why("guji db pull 失败")}
    R = Run(out / "state.json", a.fresh or a.dry_run, a.dry_run)
    if R.done("verify") or (R.done("sync") and R.st.get("no_publish")):
        # 上一趟收完之后用户又投了票，这是新的一趟。旧进度留底，从头做
        if not a.dry_run:
            os.replace(out / "state.json", out / f"state-{time.strftime('%Y%m%dT%H%M%S')}.json")
        R = Run(out / "state.json", True, a.dry_run)
    R.st["no_publish"] = bool(a.no_publish)
    R.mark("pull", {}, t)

    # 2–3. 读票、落人裁
    draft = out / "draft"
    # 一册可能收好几趟：批次名带到分钟，免得撞名（ZM 以前手工加 b 后缀）
    batch = f"H-web-{book}-{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d-%H%M')}"
    if R.done("draft"):
        R.skip("draft")
        pack, batch = R.st["done"]["draft"]["info"]["pack"], R.st["done"]["draft"]["info"]["batch"]
    else:
        t = time.time()
        pack = a.pack or _pack_for(book)
        # 旧单条目票并入前要核「页面显示字＝book-text 现格字」：先取最新 dev 的 char（ZM 11-23 vol01 职名页改号后落邻格）
        from .swap.booktext import _bt_dir, _worktree
        from .online_lists import book_text_dir as _btd
        _src = Path(a.book_text).resolve()
        _wt = Path(a.worktree or (str(_src) + "-collect")).resolve()
        _child = bool(getattr(a, "child", False))
        _worktree(_src, _wt, branch="collect-booktext" + (f"-{book}" if _child else ""),
                  sparse=(Path(_btd(".", text_id)).as_posix().lstrip("./"),), fetch=not _child)
        _cj = _bt_dir(_wt, text_id) / "default" / f"{ch}.char.json"
        cmd = [*GUJI, "cellvotes", "draft", book, "--site-book", text_id, "--chapter", ch, "--out", draft, "-w", ws,
               votes_from_flag(), "--items"]
        cmd += ["--pack", pack] if pack else ["--no-box-check"]
        if getattr(a, "policy", None):
            cmd += ["--policy", a.policy]
        if _cj.exists():
            cmd += ["--char-json", _cj]
        if a.batch or not getattr(a, "no_ai", False):
            cmd += ["--allow-empty"]          # 只落早先批次／AI 裁定时单上可能 0 票
        if _run(cmd, env, tries=3):
            return {"status": "blocked", "why": _why("cellvotes draft 失败（见上；0 票又没给 --batch 时也会停）"), "rev": rev}
        R.mark("draft", {"pack": pack, "batch": batch}, t)
    meta = json.loads((draft / "meta.json").read_text(encoding="utf-8")) if (draft / "meta.json").exists() else {}
    if not hasattr(a, "_pack_roots"):
        a._pack_roots = {}
    a._pack_roots[book] = meta.get("products_root")
    write_ledger(out, book, rev, meta)
    if a.dry_run:
        print(f"  --dry-run：不写人裁（可写 {meta.get('ready', 0)}、挂起 {meta.get('held', 0)}，见 {draft / 'report.md'}）")
    elif R.done("write"):
        R.skip("write")
    else:
        t = time.time()
        if meta.get("ready"):
            if _run([*GUJI, "cellvotes", "write", book, draft, "--batch", batch, "--reviewer", a.reviewer, "-w", ws], env, tries=3):
                return {"status": "blocked", "why": _why("cellvotes write 失败"), "rev": rev}
        R.mark("write", {"ready": meta.get("ready", 0), "held": meta.get("held", 0)}, t)

    # 4. 定字直接写 book-text
    from .swap.booktext import _bt_dir, _worktree, do_book
    src = Path(a.book_text).resolve()
    wt = Path(a.worktree or (str(src) + "-collect")).resolve()
    child = bool(getattr(a, "child", False))       # 多册并行的子进程：父进程已取过 dev，各册各用一个 worktree／分支
    landed: dict[str, str] = {}
    if R.done("book-text") and not a.dry_run:
        R.skip("book-text")
        landed = R.st["done"]["book-text"]["info"].get("landed") or {}
    else:
        t = time.time()
        sp = (Path(book_text_dir(".", text_id)).as_posix().lstrip("./"),)
        _worktree(src, wt, branch="collect-booktext" + (f"-{book}" if child else ""), sparse=sp, fetch=not child)
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
        _ks = [str(c) for c in [*votes_now, *same_ids]]
        # 格键是「页:列:格」才能取页；册启用 u 后键可能是 u（无冒号），取不出页就整册绑（慢但对）
        _pg = sorted({int(k.split(":")[0]) for k in _ks}) if all(k.split(":")[0].isdigit() and ":" in k for k in _ks) else None
        if a.batch:
            _pg = None
        got, miss, u_got, u_notes = {}, [], {}, []
        if a.batch:
            got, miss = batch_cells(book, a.batch, meta.get("products_root"))
            u_got, u_notes = batch_u_cells(book, a.batch, char)
        # 只落「只给 u 锚」的批次、没票、不落 AI：全书绑定表（QTW 004 要 30 多分钟）一格也用不上，不算
        _skip_hc = bool(a.batch and getattr(a, "no_ai", False) and not votes_now and not same_ids and not got)
        try:
            try:
                if _skip_hc:
                    print("  只有 u 锚批次事件、没票、--no-ai：不算全书绑定表")
                    hc = {}
                else:
                    hc = current_human(book, meta.get("products_root"), _pg)
            except RuntimeError as e:
                if "字块图拿不到" not in str(e):
                    raise
                # 新机器没有原图／字块缓存：自己补拉再算一遍（11-22 实测 source pull 4 s＋cache warm 1 s），不再停下来等人跑
                print(f"  缺字块图，自动 source pull＋cache warm {book} 后重算人裁")
                env_ = dict(os.environ)
                _run([*GUJI, "source", "pull", book, "-w", str(ws)], env_)
                _run([*GUJI, "cache", "warm", "--book", book, "-w", str(ws)], env_)
                hc = current_human(book, meta.get("products_root"), _pg)
        except Exception as e:  # noqa: BLE001
            return {"status": "blocked", "rev": rev,
                    "why": f"现行人裁（human_chars）算不出来，不落 book-text：{type(e).__name__}: {str(e)[:300]}"}
        cells = {k: "票" for k in votes_now} | {k: "票与已有人裁一致" for k in same_ids if k not in votes_now}
        notes = []
        if a.batch:
            miss = [m for m in miss if not any(m.startswith(f"{k} 绑定") for k in u_got)]
            notes += miss + u_notes
            for k, v in got.items():
                cells.setdefault(k, v)
            for k, (_c, b_) in u_got.items():
                cells.setdefault(k, b_)
        want = {k: (hc[k], src) for k, src in cells.items() if k in hc and hc[k] not in PLACEHOLDERS}
        if a.batch:                                # 只给 u 锚的批次事件：按 u 直接查格（见 batch_u_cells）；绑定表认得的格以 human_chars 为准
            for k, (c_, b_) in u_got.items():
                if k not in want and c_ not in PLACEHOLDERS:
                    want[k] = (c_, b_)
        if a.dry_run:                              # 演练没写票：这次新票按票上的字算（真跑时写完再从 human_chars 取）
            for k, (c, _) in votes_now.items():
                want[k] = (c, "票（未写）")
        for k in cells:
            if k not in want:
                notes.append(f"{k} 现行没有生效的定字人裁（绑定不是 valid／rebound 到本格、rev 不符或撤库），不落")
        # AI 裁定（文意、终审看图）直接落，不等重放（用户 11-20 定）；真人票／现行人裁优先，AI 只补没人裁的格
        n_ai = 0
        rk: list = []
        if not getattr(a, "no_ai", False):
            pr = meta.get("products_root") or os.environ.get("GUJI_PRODUCTS_DIR")
            if not pr:
                notes.append("没有出单版产物根，AI 裁定这次不落")
            else:
                try:
                    ai, ai_notes = ai_ruling_chars(pr, book, rekey=rk)
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
        if a.batch and u_got:                      # u 直接在 book-text 里查到的格，格号就是 book-text 自己的，不用产物核格框
            _box0 = box
            box = lambda _a: None if _a in u_got else _box0(_a)  # noqa: E731
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
        write_ledger(out, book, rev, meta, plan={k: len(v) for k, v in plan.items()}, want=len(want), n_ai=n_ai)
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
            if r.get("needs_review"):
                info["needs_review"] = r["needs_review"]
                (out / "needs_review.tsv").write_text("说明\n" + "\n".join(r["needs_review"]) + "\n", encoding="utf-8")
            info["landed"] = {x[0]: x[2] for x in plan["apply"]}
            info["ai_landed"] = {x[0]: x[3] for x in plan["apply"] if x[3].startswith("AI")}
        landed = info["landed"]
        # 提示词改版／字组改名、窗口没变的文意裁定：按现行组／版本补写一条（下次重放即命中，不用另跑 rulings-hits --rekey）
        hit = {x[0] for x in plan["apply"] + plan["already"]}
        rk = [(q, v) for q, v in rk if bare(q["cell"]) in hit]
        if rk and not a.dry_run:
            info["rekeyed"] = write_rekeys(book, rk)
            print(f"  提示词改版、窗口没变的文意裁定按现行版本补键 {info['rekeyed']} 条")
        elif rk:
            print(f"  --dry-run：提示词改版、窗口没变的文意裁定 {len(rk)} 条，真跑时补键")
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

    # 6. 推库（只一次）；并行子进程不推，父进程等各册都到这一步统一推一次
    if child and not R.done("sync"):
        return {"status": "to-sync", "rev": rev, "landed": len(landed)}
    if R.done("sync"):
        R.skip("sync")
    else:
        t = time.time()
        if _run([*GUJI, "db", "sync", "-w", ws], env, tries=4):
            return {"status": "blocked", "why": _why("guji db sync 四次都失败，原命令再跑会从推库接着做"), "rev": rev}
        R.mark("sync", None, t)

    # 7. 只发这一章，核线上单（多册时由 cmd_collect 最后一起发一次，见 publish_and_verify）
    if a.no_publish:
        print("  --no-publish：不触发网站发布（每日 proofing-sync 兜底）")
        return {"status": "synced", "rev": rev, "landed": len(landed)}
    if getattr(a, "_defer_publish", False):
        return {"status": "to-publish", "rev": rev, "landed": len(landed)}
    return publish_and_verify(a, ws, [book])[book]


# ───────────────────────── 对账表（票 → 事件 → book-text） ─────────────────────────

LEDGER_COLS = (("votes", "收件箱票"), ("valid", "有效票"), ("old_landed", "旧单并入"), ("old_blocked", "旧单挡下"),
               ("stale_votes", "票早于人裁"), ("waiting", "等多人"), ("ready", "写人裁"), ("held", "挂起"), ("skipped", "跳过"),
               ("apply", "写book-text"), ("already", "已一致"), ("layout", "等重放"), ("fig", "以图代字"), ("missing", "无此格"))


def ledger_of(book: str, rev: str, meta: dict, plan: dict | None = None, want: int | None = None, n_ai: int | None = None) -> dict:
    """一册一趟的票账：收件箱票 → 有效 → 策略（等多人）→ 分流（写人裁／挂起／跳过）→ book-text（写／已一致／等重放…）。
    票按「人×格」计，之后按格计；两段口径不同，不强求相加，但每一段都有数。"""
    sk = meta.get("skipped")
    return {"book": book, "rev": rev, "votes": meta.get("n_raw", 0), "valid": meta.get("n_votes", 0),
            "old_landed": meta.get("old_landed", 0), "old_blocked": meta.get("old_sheet", 0),
            "waiting": meta.get("waiting", 0), "stale_votes": meta.get("stale_votes", 0), "ready": meta.get("ready", 0), "held": meta.get("held", 0),
            "skipped": len(sk) if isinstance(sk, list) else (sk or 0), "policy": meta.get("policy", "auto"),
            **({"want": want, "ai": n_ai, **{k: (plan or {}).get(k, 0) for k in ("apply", "already", "layout", "fig", "missing")}}
               if plan is not None else {})}


def write_ledger(out: Path, book: str, rev: str, meta: dict, **kw) -> None:
    try:
        out.mkdir(parents=True, exist_ok=True)
        p = out / "ledger.json"
        new = ledger_of(book, rev, meta, **kw)
        if "apply" not in new and p.exists():          # 续跑跳过了落文本那步：保留上次已记的 book-text 各段
            try:
                old = json.loads(p.read_text(encoding="utf-8"))
                new = {**{k: v for k, v in old.items() if k in ("want", "ai", "apply", "already", "layout", "fig", "missing")}, **new}
            except (OSError, ValueError):
                pass
        p.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def render_ledger(rows: list[dict], status: dict[str, str] | None = None) -> str:
    """每册一行的 TSV（也直接打印）。``status`` 是各册本趟结果。"""
    head = ["册", "单版", *[t for _, t in LEDGER_COLS], "状态"]
    L = ["\t".join(head)]
    tot = {k: 0 for k, _ in LEDGER_COLS}
    for r in rows:
        L.append("\t".join([r["book"], str(r["rev"]), *[str(r.get(k, "-")) for k, _ in LEDGER_COLS], (status or {}).get(r["book"], "")]))
        for k in tot:
            tot[k] += int(r.get(k) or 0)
    L.append("\t".join(["合计", "", *[str(tot[k]) for k, _ in LEDGER_COLS], ""]))
    return "\n".join(L)


def print_ledger(ws: Path, res: dict, run_log: Path) -> None:
    rows = []
    for b, v in res.items():
        p = ws / "reports" / b / "_collect" / str(v.get("rev") or "") / "ledger.json"
        if v.get("rev") and p.exists():
            rows.append(json.loads(p.read_text(encoding="utf-8")))
    if not rows:
        return
    txt = render_ledger(rows, {b: v.get("status", "") for b, v in res.items()})
    print("\n== 票账（每册：票→事件→book-text 各段数量；票按人×格、后段按格）\n" + txt)
    try:
        run_log.with_suffix(".ledger.tsv").write_text(txt + "\n", encoding="utf-8")
    except OSError:
        pass


def needs_review_of(ws: Path, res: dict) -> dict[str, list[str]]:
    """各册本趟要交项目确认的格（要看图或前后文的，总管不定）：落文本时账不平的格（``needs_review.tsv``）、
    旧单被挡的票（``old_sheet.tsv``：图变了／撤下）、被人裁让位的旧票（``stale_votes.tsv``）。"""
    out: dict[str, list[str]] = {}
    for b, v in res.items():
        d = ws / "reports" / b / "_collect" / str(v.get("rev") or "")
        if not v.get("rev"):
            continue
        rows: list[str] = []
        for fn, tag in (("needs_review.tsv", "落字≠人裁／手改"), ("draft/old_sheet.tsv", "旧单票挡下"), ("draft/stale_votes.tsv", "票早于人裁，让位")):
            p = d / fn
            if p.exists():
                rows += [f"{tag}：" + ln.replace("\t", " | ") for ln in p.read_text(encoding="utf-8").splitlines()[1:] if ln.strip()]
        if rows:
            out[b] = rows
    return out


HANDOFF_HEAD = ["类别", "格号", "票", "读者当时看到的字", "book-text 现字", "票时间", "说明"]


def handoff_rows(ws: Path, book: str, rev: str) -> list[list[str]]:
    """一册的「交项目确认」清单转成 tsv 行（列见 ``HANDOFF_HEAD``），项目拿到就能按格看图，不用去执行机找文件。"""
    import re
    d = ws / "reports" / book / "_collect" / rev
    rows: list[list[str]] = []

    def lines(fn):
        p = d / fn
        return [ln.split("\t") for ln in p.read_text(encoding="utf-8").splitlines()[1:] if ln.strip()] if p.exists() else []
    for c in lines("needs_review.tsv"):
        rows.append(["落字≠人裁／手改", c[0], "", "", "", "", " | ".join(c[1:])])
    for c in lines("draft/old_sheet.tsv"):          # 现格 投票时格 投票时单 票 当年人裁 挡下原因
        c += [""] * (6 - len(c))
        m = re.search(r"页面显示字「(.*?)」.*?现格字「(.*?)」", c[5])
        day = re.search(r"(\d{4}-\d\d-\d\d)", c[4])
        rows.append(["旧单票挡下", c[0], c[3], m.group(1) if m else "", m.group(2) if m else "", day.group(1) if day else "",
                     f"{c[5]}（投票时格 {c[1]}，单 {c[2]}，批次事件 {c[4]}）"])
    for c in lines("draft/stale_votes.tsv"):        # 格位 票 票时间(ms) 现行人裁 人裁时间
        c += [""] * (5 - len(c))
        try:
            ts = dt.datetime.fromtimestamp(int(c[2]) / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            ts = c[2]
        rows.append(["票早于人裁，让位", c[0], c[1], "", "", ts, f"现行人裁 {c[3]}（{c[4]}），按新的判定走，票未写"])
    return rows


def write_handoff(ws: Path, res: dict, outdir: Path) -> list[Path]:
    """每册写 ``<册>-交项目确认.tsv``（覆盖更新）到 outdir；返回写了的文件。没有待确认项的册，已有的旧文件删掉。"""
    outdir.mkdir(parents=True, exist_ok=True)
    out = []
    for b, v in res.items():
        if not v.get("rev"):
            continue
        rows = handoff_rows(ws, b, str(v["rev"]))
        p = outdir / f"{b}-交项目确认.tsv"
        if not rows:
            p.unlink(missing_ok=True)
            continue
        p.write_text("\n".join("\t".join(r) for r in [HANDOFF_HEAD, *rows]) + "\n", encoding="utf-8")
        out.append(p)
    return out


def push_handoff(outdir: Path, files: list[Path]) -> str:
    """outdir 在一个 git 检出（ai-team）里：提交、rebase、推 main。失败只报不拦。"""
    def g(*args):
        return subprocess.run(["git", "-C", str(outdir), *args], capture_output=True, text=True)
    g("add", "-A", ".")
    if not g("status", "--porcelain", "--", ".").stdout.strip():
        return "无变化"
    g("commit", "-q", "-m", "交项目确认清单更新（收单自动）：" + "、".join(p.stem.split("-")[0] for p in files))
    for i in range(4):
        g("pull", "-q", "--rebase", "origin", "main")
        r = g("push", "-q", "origin", "HEAD:main")
        if r.returncode == 0:
            return "已推 main"
        time.sleep(2 ** i)
    return "推送失败：" + r.stderr.strip()[-200:]


def sweep_unconsumed(ws: Path, a) -> dict:
    """端到端票账的最后一段：人裁事件已写、路由表要它去消费者、却还没记账的（漏 route，或缺产物包）。
    GM4 管线写的批次（``H-web-*``）自动补 ``guji events route <批次>``，补完 ``guji db sync`` 推库；
    别的线的批次（ZM-、H-ZM-、H-quick- 等）不替他们跑，只列清单交书线。返回 {"routed": [批次], "remaining": {(批次, 消费者): 条数}}。"""
    from .cli_db import unconsumed_report
    out = {"routed": [], "remaining": {}, "errors": []}
    try:
        rep = unconsumed_report(ws)
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"读不了消费账：{type(e).__name__}: {e}")
        return out
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    # glyphdb_admit 要原图字块缓存，云端没有，route 了也消费不掉（每趟白跑）：只补有别的消费者没记账的批次，
    # glyphdb_admit 留给有产物的机器 db sync／CV3 扫尾，列进「事件未消费.tsv」
    mine = sorted({b for (b, c) in rep if b.startswith("H-web-") and c != "glyphdb_admit"})
    if mine and not a.dry_run:
        for b in mine:
            if _run([*GUJI, "events", "route", b, "-w", ws], env, tries=1):
                out["errors"].append(f"events route {b} 失败")
            else:
                out["routed"].append(b)
        if out["routed"] and not a.no_push:
            if _run([*GUJI, "db", "sync", "-w", ws], env, tries=3):
                out["errors"].append("补 route 后 guji db sync 失败，原命令再跑会续推")
        try:
            rep = unconsumed_report(ws)
        except Exception:  # noqa: BLE001
            pass
    out["remaining"] = rep
    if out["routed"] or rep or out["errors"]:
        print(f"\n== 事件未消费：本趟补 route {len(out['routed'])} 批（H-web-*）；仍未消费 {len(rep)} 组"
              f"（多为缺产物包或别的线手写批次，见交项目确认 tsv「事件未消费.tsv」）" + "".join(f"\n  ⚠ {e}" for e in out["errors"]))
    return out


def write_unconsumed(outdir: Path, remaining: dict) -> Path | None:
    import re
    p = outdir / "事件未消费.tsv"
    if not remaining:
        p.unlink(missing_ok=True)
        return None
    rows = ["\t".join(["批次", "消费者", "条数", "册", "怎么补"])]
    for (b, c), n in sorted(remaining.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        m = re.search(r"vol(\d+)", b)
        vol = f"vol{m.group(1)}" if m else ""
        rows.append("\t".join([b, c, str(n), vol, ("缺原图字块缓存，云端消费不了：到有产物包的机器 guji db sync，或交 CV3 扫尾" if c == "glyphdb_admit" else
                                          f"缺产物包先 guji products pack fetch {vol or '<册>'}，再 guji events route {b}；手写批次请对应书线补 route")]))
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return p


def print_needs_review(ws: Path, res: dict, unc: dict | None = None) -> None:
    nr = needs_review_of(ws, res)
    hd = os.environ.get("GUJI_HANDOFF_DIR")
    if hd:
        try:
            files = write_handoff(ws, res, Path(hd))
            if unc is not None:
                uf = write_unconsumed(Path(hd), unc.get("remaining") or {})
                if uf:
                    files.append(uf)
            print(f"\n== 交项目确认清单已写 tsv：{'、'.join(p.name for p in files) or '（无）'}（{push_handoff(Path(hd), files)}）；"
                  f"发给项目的消息只带 {hd} 下的路径")
        except Exception as e:  # noqa: BLE001 —— 写清单失败不拦收单
            print(f"⚠ 交项目确认 tsv 没写成：{type(e).__name__}: {e}")
    if not nr:
        return
    print("\n== 交项目确认（要看图或前后文；总管不逐个定，反馈给该书项目）")
    for b, rows in nr.items():
        print(f"  {b}：{len(rows)} 项")
        for r in rows[:30]:
            print(f"    {r}")


def _state_of(ws: Path, text_id: str, book: str) -> tuple[None, "Run", Path]:
    """这册收单的断点状态（目录固定键 RUN_KEY，不再依赖整张单的 rev）。第一项恒为 None（旧版是整张单路径，保留三元组形状）。"""
    d = ws / "reports" / book / "_collect" / RUN_KEY
    return None, Run(d / "state.json", False), d


def verify_book(a, ws: Path, book: str, R: "Run", sheet_p=None) -> dict:
    """网站 ``/api/pending``（只含开着的格）里，本趟 book-text 已落定的格不该还在。"""
    text_id, ch = a.text_id, chapter_of(book)
    t = time.time()
    rev = RUN_KEY
    landed = ((R.st["done"].get("book-text") or {}).get("info") or {}).get("landed") or {}
    live = live_pending(text_id, ch)
    if live is None:
        return {"status": "verify-fail", "why": "读不到网站待审", "rev": rev}
    got_open = live_open_cells(live)
    bad = sorted((got_open & {bare(c) for c in landed}), key=_key)
    if bad:
        return {"status": "verify-fail", "rev": rev,
                "why": f"网站仍待审而本地已落定 {len(bad)} 格 {bad[:8]}（发站慢就过几分钟原命令再跑一次）"}
    R.mark("verify", {"open": len(got_open)}, t)
    total = round(sum(v.get("s", 0) for v in R.st["done"].values()), 1)
    print(f"  ✓ {book}：book-text 落 {len(landed)} 格，网站待审还剩 {len(got_open)} 格；计时 {total} s")
    return {"status": "done", "rev": rev, "landed": len(landed), "open": len(got_open), "seconds": total}


def publish_and_verify(a, ws: Path, books: list[str]) -> dict:
    """这些册一起触发一次 proofing-sync（``only=`` 多章；分开触发会互相取消），等跑完逐册核线上单。
    发布没成不算失败：单子已在中心库，每日定时发布兜底；云端 gh 没鉴权时 trigger-fail（ZM 11-19）。"""
    from .swap import last_publish_age_hours, publish_batch
    st = {b: _state_of(ws, a.text_id, b) for b in books}
    todo = [b for b in books if st[b] and not st[b][1].done("publish")]
    if todo:
        t = time.time()
        minh = float(os.environ.get("GUJI_PUBLISH_MIN_HOURS", "3"))
        age = last_publish_age_hours() if minh > 0 else None
        if age is not None and age < minh:
            print(f"  网站发布节流：上次 proofing-sync 在 {age:.1f} 小时前（不足 {minh:g} 小时，CDN purge 每日配额有限）；"
                  f"本趟不发，已在中心库，下一趟有新写入时或每日定时发布会带上")
            return {b: {"status": "synced", "publish": f"throttled({age:.1f}h)", "rev": st[b][2].name if st[b] else None} for b in books}
        concl = publish_batch(todo, a.text_id)
        if concl != "success":
            only = ",".join(f"{a.text_id}/{chapter_of(b)}" for b in todo)
            print(f"⚠ 网站发布没成（{concl}）：手动触发 kaiyuanguji-web proofing-sync.yml（target=production、parts=publish、"
                  f"only={only}），再原命令跑一次核线上；不管它，每日定时发布也会带上")
            return {b: {"status": "synced", "publish": str(concl), "rev": st[b][2].name if st[b] else None} for b in books}
        for b in todo:
            st[b][1].mark("publish", {"conclusion": concl}, t)
    out = {}
    for b in books:
        _, R, _ = st[b]
        out[b] = verify_book(a, ws, b, R)
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


def votes_from_flag() -> str:
    """收单读网站票的来源：缺省中心库 web_inbox（``--from-inbox``，A20 11-22 起 D1 为网站票真源）；
    ``GUJI_VOTES_FROM=kv`` 应急改读网站 KV（KV 已不再写入，只是旧数据）。"""
    v = (os.environ.get("GUJI_VOTES_FROM") or "inbox").strip().lower()
    if v not in ("kv", "inbox"):
        raise SystemExit(f"GUJI_VOTES_FROM 只能是 kv 或 inbox：{v}")
    return "--from-inbox" if v == "inbox" else "--from-kv"


def auto_books(ws: Path, text_id: str) -> list[str]:
    """``--books auto``：读一遍网站条目票（KV），挑出有票落在还开着的条目上的册（ZM 11-19：不知道哪些册有新票，
    只能全拉自己比）。要 CELLREVIEW_TOKEN；先拉库，条目以库为准。"""
    from .cli_cellvotes import _fetch_kv_items
    from .datastore.workcopy import data_dir
    from .review import pending_items as P
    if votes_from_flag() == "--from-inbox":
        from .feedback import web_inbox as WI
        votes = WI.item_votes(WI.fetch("cellreview", text_id)[0], text_id)
    else:
        tok = os.environ.get("CELLREVIEW_TOKEN")
        if not tok:
            raise SystemExit("--books auto 要读网站票：设 CELLREVIEW_TOKEN")
        votes = _fetch_kv_items(text_id, tok)
    data = data_dir(ws)

    def open_of(ch: str) -> set[str]:
        st = P.ItemStore.open(data, text_id, ch)
        return {r["id"] for r in st.by_state("open", "withdrawn")}
    books = books_with_votes(votes, open_of)
    # 册 id 以工作区实有的 books/<册>.yaml 为准（史记叫 01 不叫 vol01；殿本叫 vol01）：不改名会白跑一趟 draft 报「没有 books/vol01.yaml」
    have = {q.stem for q in (data / "books").glob("*.yaml")}
    def stem_of(b: str) -> str:               # vol04 → 04（史记）／004（全唐文，三位）／vol04（殿本）；都对不上就原样
        if b in have:
            return b
        d = b[3:] if b.startswith("vol") else b
        for c in (d, d.zfill(2), d.zfill(3), str(int(d)) if d.isdigit() else d):
            if c in have:
                return c
        return b
    books = [stem_of(b) for b in books]
    print(f"网站条目票 {len(votes)} 条；有票落在开着的条目上的册：{'、'.join(books) or '没有'}")
    return books


def default_text_id(ws: Path) -> str:
    """没给 --text-id 时按工作区取书 ID：workspace.yaml 的 text_id → 工作区目录名前缀（``995ejelvk0-quan-tang-wen``）→ 殿本。
    （QTW 11-26：在全唐文工作区不带 --text-id 会按殿本收，收不到。）"""
    import re
    try:
        import yaml
        cfg = yaml.safe_load((Path(ws) / "workspace.yaml").read_text(encoding="utf-8")) or {}
        if isinstance(cfg, dict) and cfg.get("text_id"):
            return str(cfg["text_id"])
    except Exception:  # noqa: BLE001
        pass
    m = re.match(r"([0-9a-z]{10})-", Path(ws).name)
    return m.group(1) if m else DIANBEN_ID


def cmd_collect(a) -> int:
    ws = Path(a.workspace).resolve()
    if not a.text_id:
        a.text_id = default_text_id(ws)
        print(f"（未给 --text-id，按工作区取书 ID：{a.text_id}）")
    os.environ["GUJI_WORKSPACE"] = str(ws)
    if a.books == "auto":
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        if not a.no_pull and _run([*GUJI, "db", "pull", "-w", ws], env, tries=3):
            raise SystemExit("guji db pull 失败")
        a.no_pull = True                       # 各册不再各拉一次
        books = auto_books(ws, a.text_id)
    else:
        books = parse_books(a.books)
        if len(books) > 1 and not a.no_pull and not getattr(a, "child", False):
            # 多册只拉一次库（GM4 11-23：原先每册各拉一次，8 册拉 8 次）
            env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            if _run([*GUJI, "db", "pull", "-w", ws], env, tries=2):
                # 上一趟被打断、本地有没推的改动：拉不了，交各册自己判（续跑的册跳过拉库），不在这里整趟停下
                print("⚠ 整趟拉库没成，各册按各自进度处理（续跑的册不用再拉；不然先 guji db sync）")
            else:
                a.no_pull = True
    a._defer_publish = len(books) > 1 and not a.dry_run
    run_log = ws / "reports" / "_collect" / "runs" / f"{time.strftime('%Y%m%dT%H%M%S')}.json"
    if getattr(a, "child", False):
        res = {b: collect_book(a, ws, b) for b in books}
        rp = os.environ.get("GUJI_COLLECT_RESULT")
        if rp:
            Path(rp).write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    if (a.jobs or 1) > 1 and len(books) > 1 and not a.dry_run:
        res = run_parallel(a, ws, books, run_log)
    else:
        res = {}
        print(f"== 本趟收 {len(books)} 册：{'、'.join(books)}")
        for b in books:
            try:
                res[b] = collect_book(a, ws, b)
            except SystemExit as e:        # 某册的子步骤 SystemExit 不能把后面几册一起静默带走（GM2 11-23：--books 006,007,008 只跑了 006）
                res[b] = {"status": "blocked", "why": f"{b} 中途退出：{str(e)[:300]}"}
            except Exception as e:  # noqa: BLE001
                res[b] = {"status": "blocked", "why": f"{b} 出错 {type(e).__name__}：{str(e)[:300]}"}
                print(f"  ✗ {b} 出错 {type(e).__name__}: {e}")
            _save_run(run_log, res)
    ready = [b for b, v in res.items() if v["status"] == "to-publish"]
    if ready:
        print(f"\n== 发站：{'、'.join(ready)} 一起发一次，再逐册核线上单")
        for b, nv in publish_and_verify(a, ws, ready).items():
            res[b] = {**res[b], **nv}              # 保留 rev 等：票账、交项目确认清单要靠 rev 找各册的账
    _save_run(run_log, res)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    unc = sweep_unconsumed(ws, a)
    print_ledger(ws, res, run_log)
    print_needs_review(ws, res, unc)
    bad = {b: v for b, v in res.items() if v["status"] not in ("done", "synced", "dry-run")}
    if bad:
        print(f"\n没收完 {len(bad)} 册（原命令再跑，做过的步跳过）：")
        for b, v in bad.items():
            print(f"  {b} {v['status']}：{str(v.get('why') or '')[:300]}")
    print(f"本趟结果：{run_log}")
    return 0 if not bad else 2


def _save_run(p: Path, res: dict) -> None:
    """每收完一册就记一笔本趟结果（后台跑被重启杀掉时看得到收到哪册；各册进度另在各自 state.json）。"""
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def run_parallel(a, ws: Path, books: list[str], run_log: Path) -> dict:
    """多册并行（``--jobs N``，ZM 11-21：串行 1.5 分钟/册，大头是取包解包）：拉库、取 book-text dev 各在父进程做一次；
    每册一个子进程（``guji collect --child``），各用 ``<book-text>-collect-<册>`` worktree，做到落 book-text、结案为止；
    全部回来后父进程统一 ``db sync`` 一次、给各册记上推库，再由调用方一起发站核线上。各册日志在
    ``reports/_collect/runs/<本趟>/<册>.log``。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from .swap.booktext import DEV_REFSPEC, _git
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    env.setdefault("GUJI_ACTOR", "collect")
    if not a.no_pull and _run([*GUJI, "db", "pull", "-w", ws], env, tries=3):
        raise SystemExit(_why("guji db pull 失败"))
    src = Path(a.book_text).resolve()
    _git(src, "fetch", "-q", "origin", DEV_REFSPEC)
    logs = run_log.with_suffix("")
    logs.mkdir(parents=True, exist_ok=True)

    def one(b: str) -> tuple[str, dict]:
        cmd = [*GUJI, "collect", "--books", b, "-w", ws, "--book-text", src, "--worktree", f"{src}-collect-{b}",
               "--text-id", a.text_id, "--reviewer", a.reviewer, "--no-pull", "--child"]
        for x in a.batch or []:
            cmd += ["--batch", x]
        if getattr(a, "policy", None):
            cmd += ["--policy", a.policy]
        cmd += [f for f, on in (("--no-push", a.no_push), ("--no-ai", getattr(a, "no_ai", False)), ("--fresh", a.fresh),
                                ("--keep-pack", getattr(a, "keep_pack", False))) if on]
        rp = logs / f"{b}.result.json"
        rp.unlink(missing_ok=True)
        with open(logs / f"{b}.log", "w", encoding="utf-8") as lf:
            rc = subprocess.run([str(c) for c in cmd], env={**env, "GUJI_COLLECT_RESULT": str(rp)},
                                stdout=lf, stderr=subprocess.STDOUT).returncode
        try:
            return b, json.loads(rp.read_text(encoding="utf-8"))[b]
        except (OSError, ValueError, KeyError):
            tail = (logs / f"{b}.log").read_text(encoding="utf-8", errors="replace").strip().splitlines()[-3:]
            return b, {"status": "blocked", "why": f"子进程退出 {rc}，没给结果：{'｜'.join(tail)[:400]}（日志 {logs / (b + '.log')}）"}

    res: dict[str, dict] = {}
    t0 = time.time()
    print(f"\n== 并行收 {len(books)} 册（{a.jobs} 路），日志 {logs}/")
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        for f in as_completed([ex.submit(one, b) for b in books]):
            b, r = f.result()
            res[b] = r
            _save_run(run_log, res)
            print(f"  {b}：{r['status']} {str(r.get('why') or '')[:200]}（{len(res)}/{len(books)}，{time.time() - t0:.0f} s）", flush=True)
    todo = [b for b in books if res[b]["status"] == "to-sync"]
    if todo:
        t = time.time()
        if _run([*GUJI, "db", "sync", "-w", ws], env, tries=4):
            for b in todo:
                res[b] = {**res[b], "status": "blocked", "why": _why("guji db sync 四次都失败，原命令再跑会从推库接着做")}
            return res
        for b in todo:
            st = _state_of(ws, a.text_id, b)
            if st:
                st[1].mark("sync", {"shared": len(todo)}, t)
            res[b] = {**res[b], "status": "synced" if a.no_publish else "to-publish"}
    return res


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("collect", help="收单快路：读票→写人裁→定字直接落 book-text（不重放）→KV 结案→pull/sync 各一次→发站核对（断点续跑）")
    p.add_argument("--books", default="auto", help="如 vol20 或 vol20-vol25（逐册做）；auto（缺省）＝读网站条目票，挑有票落在开着的条目上的册")
    p.add_argument("-w", "--workspace", required=True)
    p.add_argument("--book-text", required=True, help="book-text 检出（在它旁边建 <检出>-collect worktree，每册重置到 origin/dev）")
    p.add_argument("--worktree", default=None, help="book-text worktree 路径（缺省 <book-text>-collect）")
    p.add_argument("--text-id", default=None, help="book-text 书 ID（缺省按工作区：workspace.yaml 的 text_id、目录名前缀，都没有才是殿本）")
    p.add_argument("--reviewer", default=os.environ.get("GUJI_REVIEWER", "sheldon"), help="裁决人（网站投票的人；缺省 sheldon）")
    p.add_argument("--batch", action="append", default=None,
                   help="另把早先写进库、还没进 book-text 的人裁批次也落了（可重复；只认人裁，过绑定表、每格取最新）")
    p.add_argument("--pack", default=None, help="出单版产物包标签（缺省 rev-<rev>，没有就 ★main）")
    p.add_argument("--policy", default=None,
                   help="落票策略：auto（缺省，有票就落；用户 11-23 定，现只有本人在审）｜quorum:N（高等级审阅人一票即定，其余要 N 人同一结论；"
                        "rules[:规则文件]（按会员等级与负责的书判：editor 以上、本书负责人一票即落，匿名票不直接落地）；没到门槛的格不落、不结案；也读 GUJI_LANDING_POLICY。详见 feedback/landing_policy.py")
    p.add_argument("--no-pull", action="store_true", help="不先拉库（刚拉过）")
    p.add_argument("--no-push", action="store_true", help="book-text 只提交在 worktree，不推")
    p.add_argument("--no-publish", action="store_true", help="推库后不触发网站发布、不核线上")
    p.add_argument("--fresh", action="store_true", help="不认上次的进度，从头做")
    p.add_argument("--no-ai", action="store_true",
                   help="不落 AI 裁定（缺省会把出单版包里仍待审、裁定库按窗口命中的高把握文意裁定和可放行的终审看图裁定一起直接写 book-text；人裁优先）")
    p.add_argument("-j", "--jobs", type=int, default=1,
                   help="多册并行路数（4–8；各册各用 <book-text>-collect-<册> worktree，拉库／推库／发站各一次）；缺省 1＝逐册")
    p.add_argument("--keep-pack", action="store_true", help="收完不删本册出单版包解出的目录（缺省删，腾盘）")
    p.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--dry-run", action="store_true", help="只拉库、读票出草稿、算要落哪些格并在 worktree 里提交 book-text（不推）；不写人裁、不推库、不发站")


def cmd(args) -> None:
    raise SystemExit(cmd_collect(args))


COMMANDS = {"collect": (add_parser, cmd)}
