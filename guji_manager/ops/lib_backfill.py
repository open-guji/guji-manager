"""放行格回库：机器已放行、库里却没有刻例（或不足）的字，核验后补进本书字形库（2026-11-17，Sheldon 定）。

## 为什么

机器放行的格本来不进字形库：持续进库的只有人裁（`guji db sync` 顺带落库，`feedback/auto_admit.py`），
机器来路的刻例全靠人手跑批（cv `scripts/book_lib_auto.py`）。全唐文 11-08 之后没人再跑，结果 120 册里
`rare_ref`／`witness3` 放行了 6.2 万格的 3859 个字，库里一例都没有：5a 相似度模型认不出这些字，只能认成
共用部件的别的字（樹认成榭、鄲认成鄆），每册都要靠第 7 步纠回来。七册实测 198 个 5a 自信错里 173 个是这个原因。

## 做什么（2026-11-18 规矩重定：确定了的格都是候选，每字最多 20 例，挑有区别的，来路分档）

对一册（或几册）`seed_admit` 已放行的格：

1. **选格**（`select`）：乙档通道（`match_ref`、`rare_ref`，两路独立证据）的格，库里该字不足 `cap`（20）例就是候选；
   丙档通道（`witness3`、`ref_lib` 等，整理本为主）只补不足 `thin`（3）例的字；文意通道和只有库自己作证的通道不选。
   `match_ref` 的格放行字领先别的候选字不到 `match_ref_gap` 的不选；己已巳、日曰 不选；该格已在库、已有人裁、曾被撤过库的不选。
2. **核验**（`Verifier.check`）：取管线自己的字块（`char_patch`），按入库同一把二值化和归一，得到**库里实际会存的那张图**，
   过字体模型（十万字模板）：模板首位必须就是放行字，墨量 >`INK_MIN`。不过的不进库，只记进报告。
   这一条是为了不重蹈 11-11 至 11-13「看图加厚」批的错（凭「看着与参校本同形」入库，分不开形近字，占库 13% 却占查实错标的 75%），
   也是「按刻形走」：整理本写郎、刻的是郞，模板首位落在郞上，这格不进。
3. **挑有区别的例**（`pick_diverse`）：用 5a 跨书通用底座的向量，与这个字已有某例相似度 ≥`dup_sim` 的算重复不进；
   每次挑离已有例最远的；同一个字每册最多进 `per_book`（2）例；已有 ≥`thin` 例而与已有例都不像（<`far_sim`）的算离群，不进、记进报告。
4. **抢首位核验**（2026-11-18，史記 r80，缺省关）：这一册的候选整批模拟进库（cv `BackfillProbe.steal_check`），
   库首位被新字抢走（harm）、又没有格被它救回（help）的字整字不进，记 `near_common`。
5. **入库**（`admit`）：`GlyphDB.admit_instance(provenance="auto")`，同时追加一条 `confirm` 事件
   （`actor=model`、`payload.source="auto"`、`backfill: true`，不算人裁，不进绑定表），证据里带通道、档、批次和
   核验结果，可按批次整批撤回（cv `scripts/book_lib_auto.py --withdraw <批次>`）。之后人裁同一格，以人裁为准。
   事件可重放（`feedback/consumers.py::_admit_backfills`）。

一次性补历史册：各册 `run(..., pool=…)` 只选格核验、存候选（可并行），再 `run_pools` 合起来统一挑、入库。

## 怎么触发

- 自动（缺省开，`workspace.yaml` 写 `glyph_lib.auto_backfill: false` 关）：`guji pipeline` 整册跑完没有失败页就对这一册跑一遍
  （`hooks.finished`；`GUJI_AUTO_BACKFILL=0` 临时关）。只改本机的库，随下一次 `guji db sync` 推上去。
- 手动：`guji glyph-db backfill --books 001,002 [--apply]`（不加 `--apply` 只报告）。

用法、数字与边界见 `wiki/自动化流程/放行格回库.md`。
"""
from __future__ import annotations

import collections
import datetime
import json
import sqlite3
from pathlib import Path

# 来路分档（2026-11-18，Sheldon 定「确定了的格都该入库，每字上限 20，挑有区别的」；依据见文档第九节）：
# 乙档＝两路独立证据的通道，过核验就进，补到 `cap`；丙档＝整理本为主、库证据弱的通道，只补不足 `thin` 例的字；
# 其余通道（文意通道 context／group_flow／iron…、只有库自己作证的 match_solo／book_knn／near_knn／consensus_lib…）不自动进。
TIER_B = ("match_ref", "rare_ref")
TIER_C = ("witness3", "ref_lib", "match_replace", "match_margin", "coord_fallback")
CHANNELS = TIER_B + TIER_C
CAP = 20           # 每字最多几例（人审、自动合计；人审例超过的不撤）
THIN = 3           # 丙档只在这个字现有例数不足这么多时进，补到这么多为止
PER_BOOK = 2       # 同一个字每册最多进几例，让例来自不同的册
SIM_MODEL = "models/glyph_sim_base_v1/model.pt"   # 挑例用的向量：5a 跨书通用底座（各书同一把尺；字体模型的向量挑不出区别，见文档第九节）
DUP_SIM = 0.975   # 候选与这个字已有某例的向量相似度 ≥ 这个数算重复，不进
FAR_SIM = 0.75    # 这个字已有 ≥ `thin` 例时，候选与已有例最大相似度 < 这个数算离群，不自动进、记进报告
MATCH_REF_GAP = 0.003   # match_ref：放行字的库覆盖度领先别的候选字不到这么多不进（A24 11-13 盲读：≥0.003 的 96 格 0 错，以下错 4～10%）
CONTEXT_CHARS = frozenset("己已巳日曰")   # 按文意定的字组：刻形分不开，机器放行格不进库
STEAL_CELLS_MAX = 8000     # 抢首位核验每册最多拿多少已放行格去模拟（0＝不限）
STEAL_CHECK = False        # 抢首位核验缺省关：史記第 02 册真格实测分不开好坏、每册 20–40 分钟（见文档第三节），要用的书在 workspace.yaml 开
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
    写成对象可改 `channels`（收哪些通道）、`tier_c`（其中哪些算丙档）、`cap`、`thin`、`per_book`、`dup_sim`、`far_sim`、
    `match_ref_gap`、`steal_check`（抢首位核验，缺省关）、`steal_cells_max`（每册回放格数上限，0＝不限）。"""
    import yaml
    y = Path(ws_dir or ".") / "workspace.yaml"
    cfg = (yaml.safe_load(y.read_text(encoding="utf-8")) or {}) if y.exists() else {}
    v = (cfg.get("glyph_lib") or {}).get("auto_backfill", True)
    if v is None:
        v = True
    if v is False:
        return None
    v = v if isinstance(v, dict) else {}
    known = ("channels", "tier_c", "cap", "thin", "per_book", "dup_sim", "far_sim", "match_ref_gap",
             "steal_check", "steal_cells_max")
    extra = set(v) - set(known)
    if extra:
        raise SystemExit(f"glyph_lib.auto_backfill 只认 {'、'.join(known)}，不认 {sorted(extra)}")
    out = {"channels": tuple(v.get("channels") or CHANNELS), "cap": int(v.get("cap") or CAP)}
    if "tier_c" in v:
        out["tier_c"] = tuple(v["tier_c"] or ())
    for k in ("thin", "per_book"):
        if k in v:
            out[k] = int(v[k])
    for k in ("dup_sim", "far_sim", "match_ref_gap"):
        if k in v:
            out[k] = float(v[k])
    if "steal_check" in v:
        out["steal_check"] = bool(v["steal_check"])
    if "steal_cells_max" in v:
        out["steal_cells_max"] = int(v["steal_cells_max"] or 0)
    return out


def lib_state(db_path: Path | str) -> dict:
    """现库的三样：在库实例、撤过的实例、各字现有刻例数。

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


def match_gap(gm_rec: dict | None, ch: str) -> float | None:
    """`glyph_match` 一格的候选里，放行字的覆盖度减去别的字里最高的覆盖度。放行字不在候选里（或没有这格）→ None。
    纯字符比较：同字异形的另一码位也算「别的字」，两形贴得近的格就不自动进（按刻形走，留给人或字对分类器）。"""
    cand = (gm_rec or {}).get("candidates") or []
    own = [float(c) for x, c in cand if x == ch]
    if not own:
        return None
    return max(own) - max([float(c) for x, c in cand if x != ch], default=0.0)


def select(cells: dict[str, dict], state: dict, human_keys: set[str], *,
           channels=CHANNELS, cap: int = CAP, tier_c=TIER_C, thin: int = THIN,
           gm: dict[str, dict] | None = None, match_ref_gap: float = MATCH_REF_GAP,
           ) -> tuple[dict[str, list[str]], collections.Counter]:
    """从一批 `seed_admit` 格记录（格键 → 记录）里选候选：字 → 格键（乙档在前，档内覆盖度从高到低）。纯函数。

    - 乙档通道（`channels` 里不在 `tier_c` 的）：这个字现有例数不足 `cap` 就是候选；
    - 丙档通道（`tier_c`）：这个字现有例数不足 `thin` 才是候选；
    - `match_ref` 且给了 `gm`（这一册 `glyph_match` 的格记录）：放行字领先别的候选字不到 `match_ref_gap` 的不选；
    - 夹注半格靠看图裁定放行的格（`evidence.half`，cv `vis_ruling_half`）不选，有人裁的另走人裁入库；
    - 字形对照判「异」的格（`evidence.verdict == "diff"`）不选；
    - 按文意定的字组（`CONTEXT_CHARS`）不选；该格已在库、已有人裁、曾被撤过库的不选。"""
    stat: collections.Counter = collections.Counter()
    cand: dict[str, list] = collections.defaultdict(list)
    for k, r in cells.items():
        if not r.get("admit"):
            continue
        stat["放行格"] += 1
        if (r.get("evidence") or {}).get("half") or r.get("half"):
            stat["半格看图放行"] += 1      # A23 口径（Sheldon 11-19 同意）：半格字块切偏多，没人裁过的不入库
            continue
        if (r.get("evidence") or {}).get("verdict") == "diff":
            stat["对照判异"] += 1          # 定字时字形对照判「异」：多是切坏、带框线或邻字的格（史记 11-19 抽查 11/11 是坏格）
            continue
        chan = r.get("channel")
        if chan not in channels:
            continue
        ch = r.get("char") or ""
        if len(ch) != 1 or ord(ch) < 0x2E80:
            stat["不是单个汉字"] += 1
            continue
        weak = chan in tier_c
        if state["counts"][ch] >= (thin if weak else cap):
            continue
        stat["缺例字的放行格"] += 1
        iid = f"v2:{k}"
        if ch in CONTEXT_CHARS:
            stat["文意字组"] += 1
        elif iid in state["in_lib"]:
            stat["已在库"] += 1
        elif k in human_keys:
            stat["已有人裁"] += 1
        elif iid in state["evicted"]:
            stat["曾撤过库"] += 1
        elif chan == "match_ref" and gm is not None and match_ref_gap > 0 and (
                (match_gap(gm.get(k), ch) or -1.0) < match_ref_gap):
            stat["match_ref 分差不足"] += 1
        else:
            cand[ch].append((weak, -float((r.get("evidence") or {}).get("cov") or 0), k))
    return {ch: [k for _w, _n, k in sorted(xs)] for ch, xs in cand.items()}, stat


def spread(keys: list[str], n: int) -> list[str]:
    """从排好序的格键里等距取至多 n 个（含头尾）：覆盖度高低都取到，候选之间才有区别可挑。"""
    if n <= 0:
        return []
    if len(keys) <= n:
        return list(keys)
    if n == 1:
        return [keys[0]]
    return [keys[round(i * (len(keys) - 1) / (n - 1))] for i in range(n)]


def pick_diverse(exist, cands: list[tuple], room: int, *, n_exist: int, thin: int = THIN,
                 dup_sim: float = DUP_SIM, far_sim: float = FAR_SIM) -> tuple[list[tuple[int, float | None]], dict[int, tuple[str, float]]]:
    """挑有区别的例。`exist`＝这个字已有例的向量（行已单位化，可为空）；`cands`＝[(向量, 是否丙档)]，按优先序。

    每次在乙档（没有了再丙档；丙档只在总例数不足 `thin` 时用）里挑**离已有例最远**的那个，挑中的并入已有例再挑下一个，
    挑满 `room` 个为止。与已有某例相似度 ≥ `dup_sim` 的算重复；总例数已 ≥ `thin` 而与已有例最大相似度 < `far_sim` 的算离群
    （可能是新写法，也可能是坏图或别的字，不自动进）。返回（[(候选下标, 入选时与已有例的最大相似度)]，{下标: (原因, 相似度)}）。纯函数。"""
    import numpy as np
    E = [np.asarray(e, dtype=np.float32) for e in (exist if exist is not None else [])]
    left = list(range(len(cands)))
    chosen: list[tuple[int, float | None]] = []
    dropped: dict[int, tuple[str, float]] = {}
    n = n_exist
    while len(chosen) < room and left:
        sims = {i: (max(float(np.dot(e, cands[i][0])) for e in E) if E else None) for i in left}
        for i in list(left):
            m = sims[i]
            if m is None:
                continue
            if m >= dup_sim:
                dropped[i] = ("dup", round(m, 4))
            elif n >= thin and m < far_sim:
                dropped[i] = ("far", round(m, 4))
            if i in dropped:
                left.remove(i)
        best = None
        for weak in (False, True):
            if weak and n >= thin:
                break
            pool = [i for i in left if bool(cands[i][1]) == weak]
            if pool:
                best = pool[0] if not E else min(pool, key=lambda i: sims[i])
                break
        if best is None:
            break
        m = sims[best]
        chosen.append((best, None if m is None else round(m, 4)))
        E.append(np.asarray(cands[best][0], dtype=np.float32))
        left.remove(best)
        n += 1
    return chosen, dropped


def lib_patches(db_path: Path | str, ch: str) -> list[bytes]:
    """这个字本书现有刻例的库图（借来的不算）。"""
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as c:
        has_borrowed = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='borrowed'").fetchone()
        own = " AND e.instance_id NOT IN (SELECT instance_id FROM borrowed)" if has_borrowed else ""
        return [r[0] for r in c.execute(
            "SELECT i.patch_png FROM exemplars e JOIN glyphs g USING(glyph_id) "
            "JOIN instances i ON i.instance_id = e.instance_id WHERE g.char = ?" + own, (ch,))]


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
        try:
            from .._cv import sim_load_net
            self.sim = sim_load_net(SIM_MODEL)
        except Exception as e:      # noqa: BLE001 —— 没有底座模型（没 `guji model fetch`）：不挑，按序取，摘要里报
            self.sim, self.sim_error = None, f"{type(e).__name__}: {e}"

    def _sim(self, norms: list):
        """归一图 → 单位化的 5a 底座向量；没有模型时 None。"""
        if self.sim is None or not norms:
            return None
        from .._cv import sim_embed
        z = self.np.asarray(sim_embed(self.sim, norms), dtype=self.np.float32)
        return z / (self.np.linalg.norm(z, axis=1, keepdims=True) + 1e-9)

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
                "tpl_margin": round(float(sc[o[0]] - sc[o[1]]), 4), "ink": round(ink, 4),
                "emb": None if (z := self._sim([x])) is None else z[0]}

    def embed_lib(self, pngs: list[bytes]) -> list:
        """库图（已是 canonical）→ 向量，与 `check` 里候选的向量同一口径。"""
        import cv2
        from .._cv import normalize_patch
        np = self.np
        xs = []
        for png in pngs:
            img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                xs.append(normalize_patch(img))
        z = self._sim(xs)
        return [] if z is None else list(z)


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
        channels=CHANNELS, cap: int = CAP, tier_c=TIER_C, thin: int = THIN, per_book: int = PER_BOOK,
        dup_sim: float = DUP_SIM, far_sim: float = FAR_SIM, match_ref_gap: float = MATCH_REF_GAP,
        verifier=None, log=None, report: str | None = None,
        steal_check: bool = STEAL_CHECK, steal_cells_max: int = STEAL_CELLS_MAX, probe_cls=None,
        pool: str | None = None) -> dict:
    """对 `books` 各册跑一遍选格、核验、挑有区别的例、抢首位核验、（`apply` 时）入库。返回报告。

    `pool`（一次性补历史册用，配 `run_pools`）：只选格、核验，把核验过的候选连图和向量存成这个 pickle，
    不挑、不入库；各册可以并行各出一份，再合起来统一挑。"""
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
    embs: dict[str, list] = {}     # 字 → 已有例（库里的＋这次已挑中的）的向量
    pooled: list[dict] = []
    for b in books:
        sa = _seed_cells(root, b, "seed_admit")
        cs = _seed_cells(root, b, "cell_shrink")
        gm = _seed_cells(root, b, "glyph_match") if match_ref_gap > 0 and "match_ref" in channels else None
        cand, st = select(sa, state, human, channels=channels, cap=cap, tier_c=tier_c, thin=thin,
                          gm=gm, match_ref_gap=match_ref_gap)
        stat.update(st)
        for ch in blocked & set(cand):
            stat["前册已拦"] += len(cand.pop(ch))
        if not cand:
            continue
        verifier = verifier or Verifier()
        ctx = RunContext(load_book(b), ProductStore(), cache, log=lambda *_: None)
        n0 = len(picks)
        for ch, keys in sorted(cand.items()):
            have = state["counts"][ch]
            room = min(per_book, cap - have)
            if room <= 0:
                continue
            strong = [k for k in keys if sa[k].get("channel") not in tier_c]
            weak = [k for k in keys if sa[k].get("channel") in tier_c] if have < thin else []
            ok = []       # 核验过的候选：(格键, 是否丙档, 库图 png, meta, 核验结果, 向量)
            for k in spread(strong, room * TRIES) + weak[:min(room, thin - have) * TRIES]:
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
                emb = v.pop("emb", None)
                r = sa[k]
                ev = r.get("evidence") or {}
                is_weak = r.get("channel") in tier_c
                meta = {"channel": r.get("channel"), "tier": "c" if is_weak else "b", "verdict": ev.get("verdict"),
                        "cov": ev.get("cov"), "patch_key": pk}
                if not v.pop("ok"):
                    stat["核验不过"] += 1
                    rejected.append({"key": k, "char": ch, **meta, **v})
                    continue
                ok.append((k, is_weak, cv2.imencode(".png", bin_img)[1].tobytes(), meta, v, emb))
            if not ok:
                continue
            if pool:
                pooled.extend({"char": ch, "key": k, "weak": w, "png": png, "meta": meta, "verify": v, "emb": emb}
                              for k, w, png, meta, v, emb in ok)
                continue
            if ch not in embs:
                embs[ch] = list(verifier.embed_lib(lib_patches(dbp, ch))) if have and ok[0][5] is not None else []
            if ok[0][5] is None:       # 没有底座模型、给不出向量：不挑，按序取
                stat["没有底座模型没挑"] += min(room, len(ok))
                chosen, dropped = [(i, None) for i in range(min(room, len(ok)))], {}
            else:
                chosen, dropped = pick_diverse(embs[ch], [(o[5], o[1]) for o in ok], room, n_exist=have,
                                               thin=thin, dup_sim=dup_sim, far_sim=far_sim)
            for i, (why, sim) in dropped.items():
                k, _w, _png, meta, v, _e = ok[i]
                stat["与已有例重复" if why == "dup" else "离群没进"] += 1
                if why == "far":
                    rejected.append({"key": k, "char": ch, **meta, **v, "reason": "far", "sim": sim})
            for i, sim in chosen:
                k, _w, png, meta, v, emb = ok[i]
                if sim is not None:
                    v = {**v, "sim": sim}
                picks.append((ch, k, png, meta, v))
                if emb is not None:
                    embs[ch].append(emb)
                state["counts"][ch] += 1
                state["in_lib"].add(f"v2:{k}")
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
                        embs.pop(ch, None)      # 被拦的例不算已有例：向量丢掉，要用时从库里重算
                    else:
                        kept.append((ch, k, png, meta, v))
                picks[n0:] = kept
        say(f"  {b}: 候选字 {len(cand)}，累计可入库 {len(picks)} 格")
    batch = batch or f"auto-backfill-{datetime.date.today():%Y%m%d}"
    rep = {"db": str(dbp), "books": books, "batch": batch, "apply": apply, "channels": list(channels), "cap": cap,
           "tier_c": list(tier_c), "thin": thin, "per_book": per_book, "dup_sim": dup_sim, "far_sim": far_sim,
           "match_ref_gap": match_ref_gap,
           "stat": dict(stat), "picks": len(picks), "chars": len({p[0] for p in picks}), "steal_check": steal if steal_check else None,
           "lib_before": {"instances": n_before, "chars": chars_before},
           "rejected": rejected, "picked": [{"key": k, "char": ch, **meta, **v} for ch, k, _p, meta, v in picks]}
    if pool:
        import pickle
        Path(pool).write_bytes(pickle.dumps(pooled, protocol=4))
        rep["pooled"] = len(pooled)
    if apply and picks and not pool:
        rep.update(admit(picks, batch, dbp=dbp, elog=elog))
    if report:
        Path(report).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep


def run_pools(paths: list[str], *, apply: bool = False, batch: str | None = None, cap: int = CAP, thin: int = THIN,
              per_book: int = PER_BOOK, dup_sim: float = DUP_SIM, far_sim: float = FAR_SIM, verifier=None,
              log=None, report: str | None = None) -> dict:
    """一次性补历史册的第二步：把各册 `run(..., pool=…)` 存下的候选合起来，按册序统一挑有区别的例、（`apply` 时）入库。

    候选已核验过，这里不再取图，也**不做抢首位核验**（`steal_check` 开了也不生效，补完按轮事后核）；对着现库重查一遍「已在库／已有人裁／撤过库」，上限、每册每字几例、去重、离群同 `run`。"""
    import pickle
    from .._cv import EventLog, glyph_db_path
    say = log or (lambda *_: None)
    if apply:
        bad = apply_problem()
        if bad:
            raise SystemExit("✗ 放行格回库没入库：" + bad)
    dbp, elog = glyph_db_path(), EventLog()
    state = lib_state(dbp)
    human = {e.target.key for e in elog.iter_all() if e.actor == "user"}
    n_before = sum(state["counts"].values())
    chars_before = sum(1 for v in state["counts"].values() if v > 0)
    stat: collections.Counter = collections.Counter()
    picks, rejected, embs = [], [], {}
    for path in sorted(paths):
        by_char: dict[str, list] = collections.defaultdict(list)
        for it in pickle.loads(Path(path).read_bytes()):
            iid = f"v2:{it['key']}"
            if iid in state["in_lib"] or it["key"] in human or iid in state["evicted"]:
                stat["已在库或已有人裁"] += 1
                continue
            if (it.get("meta") or {}).get("verdict") == "diff":
                stat["对照判异"] += 1             # 旧版攒的池子里可能有，取池时也挡
                continue
            by_char[it["char"]].append(it)
        stat["候选"] += sum(len(v) for v in by_char.values())
        for ch, items in sorted(by_char.items()):
            have = state["counts"][ch]
            room = min(per_book, cap - have)
            if room <= 0:
                continue
            if ch not in embs:
                verifier = verifier or Verifier()
                embs[ch] = list(verifier.embed_lib(lib_patches(dbp, ch))) if have else []
            chosen, dropped = pick_diverse(embs[ch], [(it["emb"], it["weak"]) for it in items], room, n_exist=have,
                                           thin=thin, dup_sim=dup_sim, far_sim=far_sim)
            for i, (why, sim) in dropped.items():
                stat["与已有例重复" if why == "dup" else "离群没进"] += 1
                if why == "far":
                    it = items[i]
                    rejected.append({"key": it["key"], "char": ch, **it["meta"], **it["verify"], "reason": "far", "sim": sim})
            for i, sim in chosen:
                it = items[i]
                v = {**it["verify"], **({"sim": sim} if sim is not None else {})}
                picks.append((ch, it["key"], it["png"], it["meta"], v))
                embs[ch].append(it["emb"])
                state["counts"][ch] += 1
                state["in_lib"].add(f"v2:{it['key']}")
        say(f"  {Path(path).name}: 累计可入库 {len(picks)} 格")
    batch = batch or f"auto-backfill-{datetime.date.today():%Y%m%d}"
    rep = {"db": str(dbp), "pools": sorted(paths), "batch": batch, "apply": apply, "cap": cap, "thin": thin,
           "per_book": per_book, "dup_sim": dup_sim, "far_sim": far_sim, "stat": dict(stat), "picks": len(picks),
           "chars": len({p[0] for p in picks}), "steal_check": None,
           "lib_before": {"instances": n_before, "chars": chars_before},
           "rejected": rejected, "picked": [{"key": k, "char": ch, **meta, **v} for ch, k, _p, meta, v in picks]}
    if apply and picks:
        rep.update(admit(picks, batch, dbp=dbp, elog=elog))
    if report:
        Path(report).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep


def admit(picks: list[tuple], batch: str, *, dbp=None, elog=None) -> dict:
    """把挑好的格（字, 格键, 库图 png, meta, 核验结果）入库：先写可重放的 `confirm` 事件，再进库、记账、导出账本。"""
    from .._cv import (EventLog, EventTarget, GlyphDB, ProductStore, enrich_events, export_store, glyph_db_path,
                       glyph_store_path, make_event)
    dbp = dbp or glyph_db_path()
    elog = elog or EventLog()
    rep: dict = {}
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
                      **{x: meta[x] for x in ("channel", "tier", "verdict", "cov")}, "verify": v},
            page=k.split(":")[1], col=e.target.col, idx=e.target.slot))
    rep["admitted"] = n
    # 已直接进库，给字形库消费者记账；`db sync` 取了库里的字形库时会删掉这笔账、从事件重放（`_admit_backfills`）
    elog.mark_consumed("glyphdb_admit", evs, note="放行格回库：入库时已直接进库")
    rep["export"] = export_store(db, glyph_store_path())
    db.close()
    after = lib_state(dbp)["counts"]
    rep["lib_after"] = {"instances": sum(after.values()), "chars": sum(1 for x in after.values() if x > 0)}
    return rep


def summary(rep: dict) -> str:
    s = rep["stat"]
    line = (f"缺例字的放行格 {s.get('缺例字的放行格', 0)}，核验过 {rep['picks']} 格（{rep['chars']} 字），"
            f"核验不过 {s.get('核验不过', 0)}，取不到字块 {s.get('取不到字块', 0)}")
    if s.get("没有底座模型没挑"):
        line += f"（⚠ 没有 {SIM_MODEL}，{s['没有底座模型没挑']} 格没按区别挑、按序取的：先 guji model fetch）"
    for k in ("match_ref 分差不足", "与已有例重复", "离群没进"):
        if s.get(k):
            line += f"，{k} {s[k]}"
    if s.get("抢常用字首位"):
        line += f"，会抢常用字首位没进 {s['抢常用字首位']} 格"
    sc = rep.get("steal_check")
    bad = [x["book"] for x in sc or [] if x.get("skipped") or x.get("error")]
    if sc is None:
        line += "（抢首位核验未开）"
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
