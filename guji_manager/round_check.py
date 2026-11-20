"""收轮检查（`guji round-check`，任务库单型 `roundcheck`；A31 2026-11-20，QTW 要，口径照 QTW 收轮脚本
ai-team `domain/CV/新书登记/全唐文/收轮脚本/`：tot.py、cls36.py、gate3.sh）。

一轮跑完、标 main 之前每册要做的只读检查，一条命令跑完（原来各书在自己容器里手跑，45 册约 1.5 小时，容器一重启就断）：

  1. 取对照包（`--main`，缺省 ★main）、候选包（`--pack`）各到 <out>/_m、<out>/_c（`pack fetch --to`，不动工作区产物）
  2. 两份各 `guji seg check`（同页范围、同开关；缺省 `--no-defect`，书级可开）→ seg-main/、seg-new/
  3. `guji seg gate seg-new --base seg-main [--ledger 台账 --book 书名]` → seg-gate/（gate.md、gate.json、切分未定.tsv）
  4. `guji products diff`（候选对 main）→ diff/（report.md、summary.json 里的翻转数）
  5. `guji seg premain <册> --products <候选>` [--allow 放行.tsv] → premain.tsv
  6. 候选包待审格（seed_admit `admit` 假且 `channel` 不是 excluded，同 QTW tot.py）：
       - 按四层分层（同 QTW cls36.py，判序与阈值书级可配，见 `LayerConfig`）→ layers.tsv（逐格）
       - 按 `pending_reason` 计数（同出单判法 `review/reasons`）→ pending_by_reason.tsv
  7. summary.json：以上各项的结论与数，外加可复现用的中心库 rev、字形库刻例数指纹

只读：不推库、不标 main、不存包。

    guji round-check 046 -w <书仓> --pack <候选包> [--main main] --ledger auto --ledger-book 全唐文 --out rc/046

退出码：0 全过；3 gate 挡或 premain 有命中（`--job` 时一律 0，结论看 summary.json）；其它是出错。
任务库单型见 `jobs/spec.py`（kind=roundcheck）：交单时台账从 ai-team main 取最新版随单带上，执行机不用连 ai-team。
`--collect <任务号段>`：把任务库里一批 roundcheck 单的结果收成一份汇总 tsv。
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

LAYERS = ("1 切分", "2 库缺样本", "3 形近字组", "4 其余")


# ── 四层分层（QTW cls36.py）──
@dataclass
class LayerConfig:
    """书级可配（workspace.yaml 的 `round_check:` 段）。缺省＝QTW cls36（全唐文 11-20）。

    order      判序，先中先归；元素是 seg（1 切分）、group（3 形近字组）、lib（2 库缺样本），都不中归 4 其余
    cov_min    glyph_match 首位候选分低于它算切分（有候选时）
    lib_min    本书字形库刻例数低于它算库缺样本
    seg_defect seg check 跑不跑同字对照切坏检测（慢，要读全册字块；QTW 缺省关）"""
    order: list[str] = field(default_factory=lambda: ["seg", "group", "lib"])
    cov_min: float = 0.90
    lib_min: int = 5
    seg_defect: bool = False

    @classmethod
    def from_ws(cls, ws: str | Path | None, overrides: dict | None = None) -> "LayerConfig":
        """工作区 workspace.yaml 的 `round_check:` 段，再叠 ``overrides``（单子带的 ``roundcheck.config``、命令行 ``--set``）。

        注意：执行机准备时 `guji db pull` 会用**中心库**的 workspace.yaml 覆盖书仓检出里的那份，
        所以执行机上读到的是中心库版本；只改书仓不推库不生效（史記 #5968，11-20）。"""
        try:
            import yaml
            d = (yaml.safe_load((Path(ws) / "workspace.yaml").read_text(encoding="utf-8")) or {}).get("round_check") or {}
        except Exception:  # noqa: BLE001 —— 没有或写坏了照缺省跑，summary 里记着用的是什么
            d = {}
        if not isinstance(d, dict):
            d = {}
        try:
            d = parse_config(d)
        except ValueError:
            d = {k: v for k, v in d.items() if _try_parse(k, v)}
        return cls.from_dict({**d, **parse_config(overrides or {})})

    @classmethod
    def from_dict(cls, d: dict) -> "LayerConfig":
        c = cls()
        for k, v in parse_config(d).items():
            setattr(c, k, v)
        return c

    def as_dict(self) -> dict:
        return {"order": self.order, "cov_min": self.cov_min, "lib_min": self.lib_min, "seg_defect": self.seg_defect}


CONFIG_KEYS = ("order", "cov_min", "lib_min", "seg_defect")


def parse_config(d: dict) -> dict:
    """校验、规整分层配置（workspace.yaml `round_check:`、单子 `roundcheck.config`、`--set` 共用）；不认识的键、坏值报 ValueError。"""
    if not isinstance(d, dict):
        raise ValueError("round_check 配置要是对象")
    bad = set(d) - set(CONFIG_KEYS)
    if bad:
        raise ValueError(f"round_check 配置只认 {', '.join(CONFIG_KEYS)}（不认 {', '.join(sorted(bad))}）")
    out: dict = {}
    for k, v in d.items():
        if v is None:
            continue
        if k == "order":
            if isinstance(v, str):
                v = [x.strip() for x in v.split(",") if x.strip()]
            if not (isinstance(v, list) and v and set(map(str, v)) <= {"seg", "group", "lib"} and len(set(v)) == len(v)):
                raise ValueError(f"order 是 seg／group／lib 的排列：{v!r}")
            out[k] = [str(x) for x in v]
        elif k == "cov_min":
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"cov_min 要是数：{v!r}") from None
            if not 0 <= out[k] <= 1:
                raise ValueError(f"cov_min 在 0–1：{v!r}")
        elif k == "lib_min":
            if isinstance(v, bool) or not str(v).strip().isdigit():
                raise ValueError(f"lib_min 要是非负整数：{v!r}")
            out[k] = int(v)
        elif k == "seg_defect":
            if isinstance(v, bool):
                out[k] = v
            elif str(v).strip().lower() in ("1", "true", "yes", "on"):
                out[k] = True
            elif str(v).strip().lower() in ("0", "false", "no", "off"):
                out[k] = False
            else:
                raise ValueError(f"seg_defect 要是 true／false：{v!r}")
    return out


def _try_parse(k, v) -> bool:
    try:
        parse_config({k: v})
        return True
    except ValueError:
        return False


def parse_sets(items: list[str] | None) -> dict:
    """命令行 ``--set KEY=VAL``（可多次）→ 规整后的配置。"""
    d = {}
    for it in items or []:
        k, eq, v = it.partition("=")
        if not eq:
            raise ValueError(f"--set 要写成 KEY=VAL：{it!r}")
        d[k.strip()] = v.strip()
    return parse_config(d)


_NAME = {"seg": "1 切分", "group": "3 形近字组", "lib": "2 库缺样本"}


def classify(f: dict, cfg: LayerConfig, group_chars: frozenset, near_form: frozenset, lib: Counter) -> str:
    """一格的事实 `f`（ref、top、cov、has_cands、r5、doubts、channel）→ 层。"""
    ds, ref, top, b = f["doubts"], f["ref"], f["top"], (f["r5"][0] if f["r5"] else "")
    tests = {
        "seg": lambda: "occluded" in ds or f["channel"] == "seal" or (f["has_cands"] and f["cov"] < cfg.cov_min),
        "group": lambda: (ref in group_chars or top in group_chars or b in group_chars or ref in near_form
                          or "near_form" in ds),
        "lib": lambda: lib[b or ref] < cfg.lib_min or lib[ref] < cfg.lib_min or not f["has_cands"],
    }
    for k in cfg.order:
        if tests[k]():
            return _NAME[k]
    return "4 其余"


def _layer(root: Path, step: str):
    for f in sorted((root / step).glob("p*.json")):
        try:
            yield json.loads(f.read_text(encoding="utf-8"))[step]
        except (OSError, ValueError, KeyError):
            continue


def _top(cd: list) -> tuple[str, float]:
    if not cd:
        return "", 0.0
    x = cd[0]
    if isinstance(x, (list, tuple)):
        return str(x[0]), float(x[1])
    if isinstance(x, dict):
        return str(x.get("char", "")), float(x.get("score", x.get("cov", 0)) or 0)
    return str(x), 0.0


def pending_facts(products: Path, book: str) -> tuple[int, dict[str, dict]]:
    """(全册非 excluded 格数, {格号: 事实})；待审＝seed_admit `admit` 假且 `channel` 不是 excluded（同 QTW tot.py）。"""
    root = Path(products) / book
    n, pend = 0, {}
    for sa in _layer(root, "seed_admit"):
        for col in sa.get("columns") or []:
            for c in col.get("chars") or []:
                if c.get("channel") == "excluded":
                    continue
                n += 1
                if not c.get("admit"):
                    pend[c["id"]] = {"char": c.get("char") or "", "channel": c.get("channel"),
                                     "doubts": " ".join(map(str, c.get("doubts") or []))}
    r5, gm, al = {}, {}, {}
    for d in _layer(root, "rare_candidates"):
        for col in d.get("columns") or []:
            for c in col.get("chars") or []:
                if c.get("id") in pend and c.get("candidates"):
                    r5[c["id"]] = [x["char"] for x in c["candidates"][:3]]
    for d in _layer(root, "glyph_match"):
        for col in d.get("columns") or []:
            for c in col.get("chars") or []:
                if c.get("id") in pend:
                    gm[c["id"]] = c.get("candidates") or []
    for d in _layer(root, "align_ref"):
        for c in d.get("chars") or []:
            if c.get("id") in pend:
                al[c["id"]] = c.get("align_char") or ""
    out = {}
    for i, p in pend.items():
        cd = gm.get(i) or []
        top, cov = _top(cd)
        out[i] = {"ref": al.get(i, p["char"]), "top": top, "cov": cov, "has_cands": bool(cd), "r5": r5.get(i) or [],
                  "doubts": p["doubts"], "channel": p["channel"]}
    return n, out


def lib_counter(path: Path | None) -> tuple[Counter, dict]:
    """本书字形库每字刻例数（glyph_store/exemplars.jsonl）＋指纹（行数、sha256 前 12 位，可复现用）。"""
    lib: Counter = Counter()
    if not path or not Path(path).is_file():
        return lib, {"path": str(path) if path else None, "rows": 0, "sha": None}
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for ln in fh:
            h.update(ln)
            if ln.strip():
                try:
                    lib[json.loads(ln)["char"]] += 1
                except (ValueError, KeyError):
                    pass
    return lib, {"path": str(path), "rows": sum(lib.values()), "sha": h.hexdigest()[:12]}


def _cv_sets() -> tuple[frozenset, frozenset]:
    from ._cv import NEAR_FORM_CHARS, groups_registry
    return (frozenset(c for g in groups_registry.GROUPS.values() for c in g.members), frozenset(NEAR_FORM_CHARS))


def layer_rows(facts: dict[str, dict], cfg: LayerConfig, lib: Counter, sets=None) -> list[dict]:
    g, nf = sets or _cv_sets()
    rows = []
    for i, f in facts.items():
        rows.append({"cell": i, "层": classify(f, cfg, g, nf, lib), "参校本": f["ref"], "库首位": f["top"],
                     "cov": round(f["cov"], 3), "5b前三": "".join(f["r5"]),
                     "库例数": lib[(f["r5"][0] if f["r5"] else "") or f["ref"]], "疑问": f["doubts"][:80]})
    return rows


# ── pending_reason 计数 ──
def reason_counts(products: Path, book: str, ids: list[str]) -> list[dict]:
    """这些待审格按出单判法（`review/reasons.reasons_for_pending`，带本机字形库算刻例数）的 pending_reason 计数。"""
    from .review import reasons as R
    from .review.pending_reason import specs
    try:
        from ._cv import glyph_db_path
        gdb = glyph_db_path()
    except Exception:  # noqa: BLE001 —— 没有工作区字形库就不判「刻例太少」
        gdb = None
    doc = {"cells": [{"cell": i if i.startswith(f"{book}:") else f"{book}:{i}"} for i in ids]}
    got = R.reasons_for_pending(doc, products, book, glyph_db=gdb, suspect=False)
    n = Counter(got.get(x["cell"], (R.R.UNKNOWN, ""))[0] for x in doc["cells"])
    sp = specs()
    return [{"码": sp[r].code, "pending_reason": r.value, "格数": k} for r, k in sorted(n.items(), key=lambda kv: sp[kv[0]].code)]


def _write_tsv(path: Path, header: list[str], rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ── 台账 ──
LEDGER_PATH = "domain/CV/A22/切分根因台账.tsv"


def filter_ledger(text: str, book: str) -> str:
    """只留表头和 `书` 等于 book（或 `*`、空）的行（同 `seg_gate.read_ledger` 的筛法），随单带的台账小一些。"""
    lines = text.splitlines()
    if not lines:
        return ""
    head = lines[0].split("\t")
    if "书" not in head:
        return text
    i = head.index("书")

    def bk(ln: str) -> str:
        cs = ln.split("\t")
        return cs[i].strip() if len(cs) > i else ""
    return "\n".join([lines[0]] + [ln for ln in lines[1:] if ln.strip() and bk(ln) in (book, "*", "")]) + "\n"


def fetch_ledger(ai_team: str | None = None) -> tuple[str, str]:
    """取 ai-team main 上最新的切分根因台账 → (全文, 来源说明)。先找本机 ai-team 克隆（`AI_TEAM_DIR`、~/ai-team、
    /home/user/ai-team），`git fetch` origin main 后从 FETCH_HEAD 读（不动工作树）；没有克隆就试 `gh api`。都不成抛 RuntimeError。"""
    cands = [ai_team, os.environ.get("AI_TEAM_DIR"), str(Path.home() / "ai-team"), "/home/user/ai-team"]
    errs = []
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    for d in dict.fromkeys(c for c in cands if c):
        if not (Path(d) / ".git").exists():
            continue
        try:
            subprocess.run(["git", "-C", d, "fetch", "-q", "--depth", "1", "origin", "main"], check=True,
                           capture_output=True, timeout=120, env=env)
            sha = subprocess.run(["git", "-C", d, "rev-parse", "FETCH_HEAD"], check=True, capture_output=True,
                                 text=True, timeout=30).stdout.strip()
            text = subprocess.run(["git", "-C", d, "show", f"FETCH_HEAD:{LEDGER_PATH}"], check=True,
                                  capture_output=True, timeout=60).stdout.decode("utf-8")
            return text, f"ai-team@{sha[:10]}"
        except (OSError, subprocess.SubprocessError) as e:
            errs.append(f"{d}: {type(e).__name__}")
    try:
        r = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github.raw",
                            f"repos/open-guji-core/ai-team/contents/{LEDGER_PATH}?ref=main"],
                           capture_output=True, timeout=120)
        if r.returncode == 0 and r.stdout:
            return r.stdout.decode("utf-8"), "ai-team@main(gh api)"
        errs.append(f"gh api 退出码 {r.returncode}")
    except (OSError, subprocess.SubprocessError) as e:
        errs.append(f"gh api: {type(e).__name__}")
    raise RuntimeError("取不到 ai-team 上的切分根因台账（" + "；".join(errs) + "）：克隆 ai-team 或给本地 TSV 文件")


# ── 跑命令 ──
def _guji() -> list[str]:
    exe = Path(sys.executable).with_name("guji")
    return [str(exe)] if exe.exists() else ["guji"]


def _sh(argv: list[str], ok=(0,), env: dict | None = None) -> str:
    print("$ " + " ".join(argv), flush=True)
    p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                       errors="replace", env={**os.environ, **(env or {})})
    sys.stdout.write(p.stdout)
    sys.stdout.flush()
    if p.returncode not in ok:
        tail = "\n".join(p.stdout.strip().splitlines()[-5:])
        raise RuntimeError(f"{' '.join(argv[1:3])} 退出码 {p.returncode}：{tail[-600:]}")
    return p.stdout


def _fetch(book: str, label: str, ws: str, to: Path) -> str:
    """取包到 `to`（不动工作区产物）→ 实际取到的包标签。main 取 ★main。"""
    args = [*_guji(), "products", "pack", "fetch", book, "--force", "--to", str(to), "-w", ws]
    if label != "main":
        args += ["--label", label]
    out = _sh(args)
    m = re.search(r"已取：(\S+)", out)
    return m.group(1).rsplit("/", 1)[-1] if m else label


def _seg_check(book: str, ws: str, products: Path, out: Path, pages: str | None, defect: bool) -> None:
    args = [*_guji(), "seg", "check", book, "-w", ws, "--out", str(out)]
    if not defect:
        args.append("--no-defect")
    if pages:
        args += ["--pages", pages]
    _sh(args, ok=(0, 3), env={"GUJI_PRODUCTS_DIR": str(products)})


def _central_rev() -> int | None:
    try:
        from ._cv import WorkerSource
        return int(WorkerSource().status())
    except Exception:  # noqa: BLE001
        return None


def run(book: str, *, ws: str, out: Path, pack: str, main: str = "main", ledger: Path | None = None,
        ledger_book: str = "", ledger_src: str = "", allow: Path | None = None, pages: str | None = None,
        cfg: LayerConfig | None = None, keep_packs: bool = False, overrides: dict | None = None) -> dict:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    ws = str(Path(ws).resolve())
    os.environ["GUJI_WORKSPACE"] = ws
    cfg = cfg or LayerConfig.from_ws(ws, overrides)
    t0 = time.time()
    s: dict = {"book": book, "pack": pack, "main_req": main, "ledger_book": ledger_book or None,
               "ledger_src": ledger_src or (str(ledger) if ledger else None), "pages": pages or "all",
               "layer_config": cfg.as_dict(), "layer_overrides": parse_config(overrides or {}) or None,
               "central_rev": _central_rev()}
    pm_dir, pc_dir = out / "_m", out / "_c"
    for d in (pm_dir, pc_dir):
        shutil.rmtree(d, ignore_errors=True)
    s["main"] = _fetch(book, main, ws, pm_dir)
    s["pack_got"] = _fetch(book, pack, ws, pc_dir)
    _seg_check(book, ws, pm_dir, out / "seg-main", pages, cfg.seg_defect)
    _seg_check(book, ws, pc_dir, out / "seg-new", pages, cfg.seg_defect)

    gate = [*_guji(), "seg", "gate", str(out / "seg-new"), "--base", str(out / "seg-main"), "--out", str(out / "seg-gate"),
            "--new-label", s["pack_got"], "--base-label", s["main"]]
    if ledger:
        gate += ["--ledger", str(ledger), "--book", ledger_book]
    _sh(gate, ok=(0, 3))
    g = json.loads((out / "seg-gate" / "gate.json").read_text(encoding="utf-8"))
    s["gate"] = {k: g.get(k) for k in ("blocked", "n_regress", "n_geo_same", "n_bad_pages", "n_known", "n_fixed",
                                       "n_unregistered", "geometry")}

    n_pages = len(list((pc_dir / book / "seed_admit").glob("p*.json")))
    diff = [*_guji(), "products", "diff", book, "--a", str(pm_dir), "--b", str(pc_dir), "-w", ws,
            "--pages", pages or (f"1-{n_pages}" if n_pages else "all"), "--out", str(out / "diff")]
    _sh(diff)
    try:
        ds = json.loads((out / "diff" / "summary.json").read_text(encoding="utf-8"))
        s["diff"] = {"review_main": (ds.get("a") or {}).get("review"), "review_new": (ds.get("b") or {}).get("review"),
                     "flips": ds.get("flips") or {}}
    except (OSError, ValueError):
        s["diff"] = None

    pm = [*_guji(), "seg", "premain", book, "--products", str(pc_dir), "--out", str(out / "premain.tsv")]
    if allow:
        pm += ["--allow", str(allow)]
    if pages:
        pm += ["--pages", pages]
    _sh(pm, ok=(0, 3))
    hits = [ln.split("\t") for ln in (out / "premain.tsv").read_text(encoding="utf-8").splitlines()[1:] if ln.strip()]
    s["premain"] = {"hits": len(hits), "cols": len({tuple(h[:3]) for h in hits}), "pass": not hits}

    n_cells, facts = pending_facts(pc_dir, book)
    try:
        from ._cv import glyph_store_path
        ex = Path(glyph_store_path()) / "exemplars.jsonl"
    except Exception:  # noqa: BLE001
        ex = None
    lib, s["glyph_lib"] = lib_counter(ex)
    rows = layer_rows(facts, cfg, lib)
    _write_tsv(out / "layers.tsv", ["cell", "层", "参校本", "库首位", "cov", "5b前三", "库例数", "疑问"], rows)
    by_layer = Counter(r["层"] for r in rows)
    try:
        by_reason = reason_counts(pc_dir, book, list(facts))
        _write_tsv(out / "pending_by_reason.tsv", ["码", "pending_reason", "格数"], by_reason)
    except Exception as e:  # noqa: BLE001 —— 原因码是附带的，算不出不挡分层
        by_reason = None
        s["pending_reason_error"] = f"{type(e).__name__}: {e}"[:300]
    s["pending"] = {"cells": n_cells, "total": len(rows), "by_layer": {k: by_layer.get(k, 0) for k in LAYERS},
                    "by_reason": by_reason}
    s["pass"] = not s["gate"]["blocked"] and s["premain"]["pass"]
    s["secs"] = round(time.time() - t0, 1)
    if not keep_packs:
        for d in (pm_dir, pc_dir):
            shutil.rmtree(d, ignore_errors=True)
    (out / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    return s


def verdict_line(s: dict) -> str:
    g, p, ps, df = s["gate"], s["premain"], s["pending"], s.get("diff") or {}
    lay = "，".join(f"{k} {v}" for k, v in ps["by_layer"].items() if v)
    fl = df.get("flips") or {}
    return (f"收轮检查 {s['book']} {s['pack_got']} 对 {s['main']}：{'通过' if s['pass'] else '不能标 main'}"
            f"｜gate {'挡' if g['blocked'] else '过'}（回退 {g['n_regress']} 列、新页级错 {g['n_bad_pages']} 页、"
            f"已知未清 {g['n_known']} 列其中未挂台账 {g['n_unregistered']}）"
            f"｜premain {'命中 ' + str(p['hits']) + ' 条（' + str(p['cols']) + ' 列）' if p['hits'] else '过'}"
            f"｜待审 {ps['total']}/{ps['cells']}（{lay or '无'}）"
            + (f"｜放行字变 {fl.get('放行字变', 0)}、admit→review {fl.get('admit→review', 0)}、review→admit {fl.get('review→admit', 0)}"
               if df else ""))


# ── 收一批：把任务库里多条 roundcheck 单的结果合成一份 ──
SUMMARY_COLS = ["册", "任务", "状态", "候选包", "main", "结论", "gate", "回退列", "新页级错", "已知未清", "未挂台账",
                "premain命中", "premain列", "全册格", "待审", *LAYERS, "main待审", "放行字变", "admit→review", "review→admit",
                "人裁翻转", "中心库rev", "字形库指纹"]


def summary_row(job: dict, s: dict | None) -> dict:
    row = {"册": job.get("book") or "", "任务": job["id"], "状态": job["status"]}
    if not s:
        return row
    g, p, ps = s["gate"], s["premain"], s["pending"]
    df = s.get("diff") or {}
    fl = df.get("flips") or {}
    row.update({"候选包": s.get("pack_got"), "main": s.get("main"), "结论": "通过" if s.get("pass") else "不能标main",
                "gate": "挡" if g["blocked"] else "过", "回退列": g["n_regress"], "新页级错": g["n_bad_pages"],
                "已知未清": g["n_known"], "未挂台账": g["n_unregistered"], "premain命中": p["hits"], "premain列": p["cols"],
                "全册格": ps.get("cells"), "待审": ps["total"], **{k: ps["by_layer"].get(k, 0) for k in LAYERS},
                "main待审": df.get("review_main"), "放行字变": fl.get("放行字变", 0), "admit→review": fl.get("admit→review", 0),
                "review→admit": fl.get("review→admit", 0), "人裁翻转": fl.get("admit→human", 0) + fl.get("review→human", 0),
                "中心库rev": s.get("central_rev"), "字形库指纹": (s.get("glyph_lib") or {}).get("sha")})
    return row


def _data(r: dict) -> dict:
    d = r.get("data") or {}
    return json.loads(d) if isinstance(d, str) else d


def collect(db, ids: list[int], out: Path, say=print) -> int:
    """任务库里这些 roundcheck 单的结果 → out/汇总.tsv、待审按原因-合计.tsv，各册 gate.md／切分未定.tsv／premain.tsv／pending_by_reason.tsv。"""
    from .jobs import store as S
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows, reason_tot = [], Counter()
    for i in ids:
        j = db(S.detail, i)
        if j is None:
            say(f"✗ 没有 #{i}")
            continue
        if j.get("kind") not in (None, "roundcheck"):
            continue
        res = {r["name"]: _data(r) for r in j.get("results") or []}
        s = res.get("roundcheck", {}).get("summary")
        rows.append(summary_row(j, s))
        if not s:
            continue
        d = out / (j.get("book") or str(i))
        d.mkdir(exist_ok=True)
        for name, fn in (("seg_gate", "gate.md"), ("seg_gate_undecided", "切分未定.tsv"), ("seg_premain", "premain.tsv"),
                         ("pending_by_reason", "pending_by_reason.tsv")):
            t = res.get(name, {}).get("text")
            if t:
                (d / fn).write_text(t, encoding="utf-8")
        for r in (s["pending"].get("by_reason") or []):
            reason_tot[(r["码"], r["pending_reason"])] += r["格数"]
    _write_tsv(out / "汇总.tsv", SUMMARY_COLS, rows)
    _write_tsv(out / "待审按原因-合计.tsv", ["码", "pending_reason", "格数"],
               [{"码": c, "pending_reason": p, "格数": n} for (c, p), n in sorted(reason_tot.items())])
    bad = [r for r in rows if r.get("结论") != "通过"]
    say(f"{out}/汇总.tsv：{len(rows)} 册，通过 {len(rows) - len(bad)}，"
        f"不能标 main 或没结果 {len(bad)}" + (f"（{'、'.join(str(r['册']) for r in bad[:30])}）" if bad else ""))
    return 0 if not bad else 3


# ── 命令行 ──
def add_parser(sub) -> None:
    p = sub.add_parser("round-check", help="收轮检查（只读）：main 与候选包各 seg check → seg gate → products diff → seg premain → 待审分四层＋按 pending_reason 计数")
    p.add_argument("vol", nargs="?", help="册 id（参数名不叫 book：cv 会给带 book 的子命令再加一次 -w，冲突）")
    p.add_argument("-w", "--workspace", default=None)
    p.add_argument("--pack", default=None, help="候选包标签（必给）")
    p.add_argument("--main", default="main", help="对照包：main（缺省，取 ★main）或包标签")
    p.add_argument("--ledger", default="", help="切分根因台账 TSV；写 auto 从 ai-team main 取最新")
    p.add_argument("--ledger-book", default="", help="台账里的书名（殿本／史記／全唐文），给了 --ledger 必给")
    p.add_argument("--allow", default="", help="seg premain 的放行清单 TSV")
    p.add_argument("--pages", default="", help="只查这些页（各步同范围）")
    p.add_argument("--out", default="", help="输出目录（缺省 ./round-check/<册>）")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VAL",
                   help="覆盖 workspace.yaml round_check 段（可多次）：seg_defect=true、order=seg,group,lib、cov_min=0.9、lib_min=5")
    p.add_argument("--keep-packs", action="store_true", help="留下取到 <out>/_m、_c 的两份包（缺省做完删）")
    p.add_argument("--job", action="store_true", help="任务单用：结论只看 summary.json，挡了也退出 0")
    p.add_argument("--collect", default="", help="不跑检查，把任务库里这些 roundcheck 单的结果收成一份：12,13,20-40")


def _ids(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        a, _, b = part.strip().partition("-")
        if a:
            out.extend(range(int(a), int(b or a) + 1))
    return out


def cmd(args) -> None:
    if args.collect:
        from .jobs import store as S
        raise SystemExit(collect(S.DB(), _ids(args.collect), Path(args.out or "round-check")))
    book = args.vol
    if not book or not args.pack:
        raise SystemExit("❌ 要给册和 --pack（候选包标签）")
    ws = args.workspace or os.environ.get("GUJI_WORKSPACE")
    if not ws:
        raise SystemExit("❌ 要给 -w 工作区")
    try:
        overrides = parse_sets(args.set)
    except ValueError as e:
        raise SystemExit(f"❌ {e}") from None
    ledger, src = None, ""
    out = Path(args.out or f"round-check/{book}")
    if args.ledger:
        if not args.ledger_book:
            raise SystemExit("❌ 给了 --ledger 就要给 --ledger-book（台账里的书名）")
        if args.ledger == "auto":
            text, src = fetch_ledger()
            out.mkdir(parents=True, exist_ok=True)
            ledger = out / "ledger.tsv"
            ledger.write_text(filter_ledger(text, args.ledger_book), encoding="utf-8")
        else:
            ledger = Path(args.ledger)
    s = run(book, ws=ws, out=out, pack=args.pack, main=args.main, ledger=ledger, ledger_book=args.ledger_book,
            ledger_src=src, allow=Path(args.allow) if args.allow else None, pages=args.pages or None,
            keep_packs=args.keep_packs, overrides=overrides)
    print(verdict_line(s))
    raise SystemExit(0 if (args.job or s["pass"]) else 3)


COMMANDS = {"round-check": (add_parser, cmd)}
