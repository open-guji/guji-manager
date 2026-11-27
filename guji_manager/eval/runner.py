"""跑一个评测器：子进程 → 抓 stdout → 解析指标 → 补金标状态 → 统一报告。

金标状态（`n_gold` / `stale_gold` / `uncertain_skipped`）**由 GoldStore 提供**，
不指望评测脚本自己报——它们读的是旧文件，压根不知道 stale 这回事。
这样「先查漂移再谈数字」就成了报告的固有部分，而不是靠人记得去查。
"""

from __future__ import annotations

from .. import _cv  # cv_repo()：本文件原在 cv 包里，按 __file__ 找 cv 仓
import json
import os
import re
import subprocess
import time
from pathlib import Path

from .registry import EvalSpec, find_eval, runnable
from .report import EvalReport, Metric, parse_metrics


def repo_root() -> Path:
    return _cv.cv_repo()


DEFAULT_TIMEOUT = 900


def parse_timeout_for(items) -> dict[str, int]:
    """`id=秒` 或 `前缀_=秒`／`前缀*=秒`（逗号分隔或多次给）→ {键: 秒}。写错直接报，别静默用默认。"""
    out: dict[str, int] = {}
    for item in items or []:
        for part in str(item).split(","):
            part = part.strip()
            if not part:
                continue
            k, sep, v = part.partition("=")
            if not sep or not k.strip() or not v.strip().isdigit():
                raise ValueError(f"超时写法不对：{part!r}，要 评测器id=秒 或 前缀_=秒（如 rare_=3600）")
            out[k.strip()] = int(v)
    return out


def _match_override(eval_id: str, overrides: dict[str, int]) -> int | None:
    if eval_id in overrides:
        return overrides[eval_id]
    best = None
    for k, v in overrides.items():
        pre = k[:-1] if k.endswith("*") else (k if k.endswith("_") else None)
        if pre is not None and eval_id.startswith(pre) and (best is None or len(pre) > best[0]):
            best = (len(pre), v)
    return best[1] if best else None


def eval_timeout(spec: EvalSpec, timeout: int | None = None,
                 overrides: dict[str, int] | None = None) -> int:
    """这个评测器用多少秒超时。先后：按评测器覆盖（--timeout-for，再环境变量 GUJI_EVAL_TIMEOUT_FOR）
    → 统一给的 --timeout → 环境变量 GUJI_EVAL_TIMEOUT → 注册表里评测器自己的默认（rare_* 2700）→ 900。"""
    hit = _match_override(spec.id, overrides or {})
    if hit is None:
        hit = _match_override(spec.id, parse_timeout_for([os.environ.get("GUJI_EVAL_TIMEOUT_FOR", "")]))
    if hit is not None:
        return hit
    if timeout is not None:
        return int(timeout)
    env = os.environ.get("GUJI_EVAL_TIMEOUT", "").strip()
    if env.isdigit():
        return int(env)
    return spec.timeout or DEFAULT_TIMEOUT


def _cv_desc() -> str:
    """当前用的 cv：版本＋仓路径（报缺脚本时让人一眼看出是不是旧 cv）。"""
    try:
        from importlib.metadata import version
        ver = version("open-guji-cv")
    except Exception:   # noqa: BLE001
        ver = "版本未知"
    try:
        where = str(repo_root())
    except Exception:   # noqa: BLE001
        where = "?"
    return f"cv {ver}（{where}）"


def missing_script(spec: EvalSpec) -> str:
    """cv 仓里没有这个评测脚本就返回给人看的提示，有就空串。

    旧 cv（<0.9.2）没有 eval_advset.py、eval_match_pool.py 这类新评测器，
    以前子进程报「can't open file」只记成「未验证」，看不出该换 cv（GM4 11-27 史記补跑 15 条未验证）。"""
    try:
        path = repo_root() / "scripts" / spec.script
    except Exception:   # noqa: BLE001
        return ""
    if path.exists():
        return ""
    lo, rec = cv_floor()
    return (f"当前 {_cv_desc()} 没有 scripts/{spec.script}——这个评测器要 cv ≥{lo}，"
            f"请用 cv ≥{lo}（建议 v{rec}）检出再跑")


# 护栏评测脚本要的 cv 下限与建议版本（CV0 11-27 核实：0.9.2 起每个 0.9.x 都带 eval_advset／eval_match_pool）。
# 写在这里一处；建议版本会过时，环境变量 GUJI_EVAL_CV_MIN／GUJI_EVAL_CV_SUGGEST 可盖，不用等发版。
EVAL_CV_MIN = "0.9.2"
EVAL_CV_SUGGEST = "0.9.10"


def cv_floor() -> tuple[str, str]:
    lo = os.environ.get("GUJI_EVAL_CV_MIN", "").strip().lstrip("v") or EVAL_CV_MIN
    rec = os.environ.get("GUJI_EVAL_CV_SUGGEST", "").strip().lstrip("v") or EVAL_CV_SUGGEST
    return lo, rec


# 缺权重／缺稀见字索引的报错特征（ZM 殿本 11-27 补齐这两样后护栏 5/5 过，GM4 报）
_NO_FILE = re.compile(r"(FileNotFoundError|No such file|not found|不存在|找不到|缺)", re.IGNORECASE)
_WEIGHT = re.compile(r"(models/|\.pt\b|\.pth\b|checkpoint|ckpt|glyph_cnn|glyph_sim|权重|模型)", re.IGNORECASE)
_RARE_IDX = re.compile(r"(emb_[\w-]+\.npz|rare[-_]index|向量包|稀见字索引)", re.IGNORECASE)

def missing_asset_hint(out: str) -> str:
    """子进程输出看着是缺模型权重或稀见字向量包，就给补法；看不出来返回空串（不瞎猜）。"""
    lines = [ln for ln in (out or "").splitlines() if _NO_FILE.search(ln)]
    if any(_RARE_IDX.search(ln) for ln in lines):
        return "缺稀见字索引：先 `guji cache pull-rare-index --charset unicode-cjk-ab` 再重跑"
    if any(_WEIGHT.search(ln) for ln in lines):
        return "缺模型权重：先 `guji pipeline model fetch`（要 GUJI_DATA_TOKEN 或 GUJI_DATA_TOKEN_READ）再重跑"
    return ""


def run_eval(key: str, dataset_root: Path | None = None, timeout: int | None = None,
             allow: tuple[str, ...] = ("products",),
             report_dir: Path | None = None, from_raw: bool = False,
             timeout_for: dict[str, int] | None = None) -> EvalReport:
    spec = find_eval(key)
    if spec is None:
        return EvalReport(eval_id=key, shard="", status="failed", error=f"没有这个评测器: {key}",
                          fail_kind="error")
    timeout = eval_timeout(spec, timeout, timeout_for)

    from .._cv import GoldStore
    store = GoldStore(dataset_root)
    ds = store.root

    rep = EvalReport(eval_id=spec.id, shard=spec.shard)
    ok, why = runnable(spec, allow)
    if not ok:
        rep.status = "skipped"
        rep.error = why
        rep.fail_kind = "precondition"
        _fill_gold(rep, store, spec)
        return rep

    gone = missing_script(spec)
    if gone:
        rep.status, rep.error, rep.fail_kind = "failed", gone, "missing_script"
        _fill_gold(rep, store, spec)
        return rep

    # `needs=("products",)` 声明了「跑得动的前提」，但没查过这台机器上产物是不是
    # 真的齐——干净 clone 上齐不齐得跑之前现查，不能到脚本报错才知道。
    if "products" in spec.needs:
        missing = _missing_pages_by_book(spec, store)
        if missing:
            if from_raw:
                broken = _bootstrap_missing(missing)
                if broken:
                    # 单个评测引用的册在本工作区里没有定义（如云端只挂四库总目、金标里有 bxgb）：
                    # 只让这一个评测失败并写明原因，别把整批 `eval run` 拖崩。
                    rep.status, rep.fail_kind = "failed", "precondition"
                    rep.error = "from-raw 补产物失败：" + "；".join(
                        f"{bk}（{why}）" for bk, why in broken.items())
                    _fill_gold(rep, store, spec)
                    return rep
            else:
                detail = "；".join(f"{bk} 缺第 {pgs} 页" for bk, pgs in missing.items())
                rep.status, rep.fail_kind = "failed", "precondition"
                rep.error = (f"缺产物，{detail}。"
                             f"加 --from-raw 从原图现跑补齐，或先跑 "
                             f"`seg_harness.py --from-raw`（不带 --pages 即全金标）")
                _fill_gold(rep, store, spec)
                return rep

    if "bench" in spec.needs:
        from .bench_bundle import ensure_bench
        ok_b, why_b = ensure_bench()
        if not ok_b:
            rep.status, rep.error, rep.fail_kind = "skipped", f"5b 评测集不齐：{why_b}", "precondition"
            return rep

    target = spec.target(ds)
    if target is not None and not target.exists():
        rep.status, rep.fail_kind = "skipped", "precondition"
        rep.error = f"金标路径不存在: {target}"
        return rep

    out_path = None
    if spec.out_flag:
        d = report_dir or (repo_root() / "runs" / "evals")
        d.mkdir(parents=True, exist_ok=True)
        out_path = d / f"{spec.id}.json"

    argv = spec.argv(ds, out_path)
    rep.command = " ".join(argv)
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    if spec.pythonpath:
        env["PYTHONPATH"] = str(repo_root()) + os.pathsep + env.get("PYTHONPATH", "")

    # 跑之前记下数据集仓里那个 report.json 在不在——只清本次新产生的
    stray_before = (ds / spec.shard / "report.json").exists() if spec.out_flag else None

    t0 = time.time()
    try:
        p = subprocess.run(argv, cwd=repo_root(), env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
        out = (p.stdout or "") + (("\n" + p.stderr) if p.returncode and p.stderr else "")
        rep.exit_code = p.returncode
    except subprocess.TimeoutExpired:
        rep.status, rep.elapsed, rep.fail_kind = "failed", time.time() - t0, "timeout"
        rep.error = (f"超时（{timeout}s）；要放宽就加 --timeout-for {spec.id}=秒"
                     f"（前缀写法 {spec.id.split('_')[0]}_=秒），或设 GUJI_EVAL_TIMEOUT_FOR")
        return rep
    except Exception as e:   # noqa: BLE001
        rep.status, rep.error, rep.elapsed = "failed", f"{type(e).__name__}: {e}", time.time() - t0
        rep.fail_kind = "error"
        return rep
    rep.elapsed = round(time.time() - t0, 2)
    rep.stdout_tail = "\n".join(out.strip().splitlines()[-25:])

    # 有的脚本 --out 默认值指向数据集仓（context_correction / char_ocr 的
    # `root / "report.json"`），不传就往那儿写、污染工作区。
    # **只删本次跑之前不存在的那个文件**——好几个分片的 report.json 是仓库里
    # 跟踪着的历史基线，删掉就把基线弄丢了（第一版防护就是这么删过头的）。
    if spec.out_flag and stray_before is not None and not stray_before:
        stray = ds / spec.shard / "report.json"
        if stray.exists() and (out_path is None or stray != out_path):
            try:
                stray.unlink()
                rep.stdout_tail += f"\n[适配层] 清掉脚本新写进数据集仓的 {stray.name}"
            except OSError:
                pass

    # 退出码不可靠：好几个脚本缺产物时 print 完就 return，退出码仍是 0；
    # 反过来也有脚本把指标印完了才在收尾处崩（left_cut 的除零）。
    # 所以判据是「有没有解析出指标」，退出码只作参考。
    rep.metrics = parse_metrics(out)
    structured_err = ""
    data = None
    if out_path and out_path.exists():
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
            from .extract import extract
            ms, structured_err = extract(spec.id, data)
            if ms is not None:
                # 识字评测器按 id 读 JSON（stdout 抠出来的数不全、头条取错路，见 extract 模块头）
                rep.metrics = ms
            else:
                rep.metrics = _merge_json_metrics(rep.metrics, data)
        except Exception:   # noqa: BLE001
            pass
    try:
        from .extract import bench_lock
        rep.lock = bench_lock(spec.id, repo_root(), ds, data if isinstance(data, dict) else None)
    except Exception:   # noqa: BLE001
        pass

    gate = _gate_verdict(out)
    if gate:
        rep.gate = gate
    if structured_err:
        # 数是假的（如 rare_* 缺向量包全 0%）：判失败，别报 ok
        rep.status, rep.error = "failed", structured_err
        rep.fail_kind = "missing_asset" if "pull-rare-index" in structured_err else "error"
    elif rep.metrics or gate:
        # **回归门的结论本身就是结果**：印了「回归门：通过」而没有别的数字，
        # 也是跑成功了（这类闸的产出就是过没过）。失败同理——门拦住了东西，
        # 跟门本身坏掉是两回事，混报会让人分不清该看算法还是该修评测。
        rep.status = "regressed" if gate == "失败" else "ok"
        if gate and not rep.metrics:
            rep.metrics = [Metric(name="回归门", value=gate)]
        if rep.exit_code not in (0, None):
            rep.error = f"脚本以 {rep.exit_code} 退出（结果已产出，多为收尾处报错）：" \
                        + (rep.stdout_tail.splitlines() or [""])[-1][:120]
    elif rep.exit_code not in (0, None):
        rep.status, rep.error = "failed", (rep.stdout_tail.splitlines() or [""])[-1][:200]
    else:
        # 确定的事实与猜测分两行报，猜测标明是猜测——别把两者糊成一句话让猜测
        # 读起来像结论（2026-09-09 吃过一次亏：产物齐全后报错一字不变，
        # 真根因是 parse_metrics 认不出这个脚本的输出，不是缺产物）。
        rep.status = "failed"
        tail = (rep.stdout_tail.splitlines() or [""])[-1][:120]
        rep.error = (f"事实：脚本以 {rep.exit_code} 退出，parse_metrics 解析到 0 条指标；"
                     f"stdout 尾行：{tail}\n"
                     f"猜测（未证实，别当结论）：产物已经在跑之前查过（见上面 needs 检查），"
                     f"多半是 parse_metrics 认不出这个脚本的输出格式")

    if rep.status == "failed" and not rep.fail_kind:
        hint = missing_asset_hint(out)
        if hint:
            rep.fail_kind = "missing_asset"
            rep.error = hint + "；原报错：" + rep.error
    if rep.status in ("failed", "skipped") and not rep.fail_kind:
        rep.fail_kind = "error"
    _apply_guards(rep, ds)
    _fill_gold(rep, store, spec)
    return rep


def _apply_guards(rep: EvalReport, ds: Path) -> None:
    """dataset guards/*.yaml 里有这个评测器的护栏就逐条比；越线 → regressed（回归门失败）。"""
    try:
        from .guards import check_report, guards_for, load_guards
        gs = guards_for(load_guards(ds), rep.eval_id)
    except Exception as e:   # noqa: BLE001 —— 护栏表坏了要让人看见，但别吞掉评测结果
        rep.error = (rep.error + "；" if rep.error else "") + f"护栏表读不了：{e}"
        return
    if not gs:
        return
    res = check_report(rep, gs)
    rep.guards = [r.to_dict() for r in res]
    if rep.status == "ok" and any(r.verdict == "fail" for r in res):
        rep.status, rep.gate = "regressed", "失败"


def _missing_pages_by_book(spec: EvalSpec, store) -> dict[str, list[int]]:
    """这个评测器的金标条目锚定在哪些 (book, page) 上，逐页查产物在不在。

    按金标条目的 `anchor` 算，不是按位置参数猜——分片可能横跨多册，
    没有 page 锚点的条目（非按页组织的分片）直接跳过，不强加语义。
    """
    from .._cv import ProductStore
    from .._cv import has_products

    items = [i for i in store.list(spec.shard)
             if i.status == "active" and i.anchor.book and i.anchor.page is not None]
    by_book: dict[str, set[int]] = {}
    for it in items:
        by_book.setdefault(it.anchor.book, set()).add(it.anchor.page)
    pstore = ProductStore()
    missing: dict[str, list[int]] = {}
    for book, pages in by_book.items():
        miss = sorted(pg for pg in pages if not has_products(book, pg, store=pstore))
        if miss:
            missing[book] = miss
    return missing


def _bootstrap_missing(missing: dict[str, list[int]]) -> dict[str, str]:
    """从原图补跑缺的产物。返回补不了的册 {book: 原因}（册定义缺失、原图缺失等）。"""
    from .._cv import load_book
    from .._cv import ImageCache
    from .._cv import ProductStore
    from .._cv import ensure_products

    pstore, cache = ProductStore(), ImageCache()
    broken: dict[str, str] = {}
    for book_id, pages in missing.items():
        try:
            ensure_products(load_book(book_id), pages, store=pstore, cache=cache)
        except (FileNotFoundError, KeyError, ValueError) as e:
            broken[book_id] = f"{type(e).__name__}: {str(e)[:120]}"
    return broken


# 三种写法都要认（实测）：
#   回归门：通过        多数
#   回归门：**失败**    失败态带星号包裹，通过态不带——不对称
#   回归门：31/31 通过  eval_normalize 独有，中间夹分数
_GATE = re.compile(r"回归门[:：]\s*(?:\*\*)?\s*(?:\d+\s*/\s*\d+\s*)?(通过|失败)")


def _gate_verdict(text: str) -> str:
    """抓「回归门：通过 / 失败」。这是评测结论，与脚本跑没跑起来无关。"""
    hits = _GATE.findall(text)
    return "失败" if "失败" in hits else ("通过" if hits else "")


def _fill_gold(rep: EvalReport, store, spec: EvalSpec) -> None:
    """金标状态由 GoldStore 报，评测脚本不知道 stale 这回事。"""
    try:
        items = store.list(spec.shard)
    except Exception:   # noqa: BLE001
        return
    if not items:
        return
    rep.n_gold = len(items)
    rep.stale_gold = sum(1 for i in items if i.status == "stale")
    rep.uncertain_skipped = sum(1 for i in items if i.status == "uncertain")


_NUM_KEYS = ("accuracy", "recall", "precision", "f1", "rate", "acc", "mean", "median",
             "pass", "ok", "match", "iou", "err", "diff", "score", "top")


def _merge_json_metrics(existing: list[Metric], data: dict, limit: int = 12) -> list[Metric]:
    """报告 JSON 里的数字指标并进来。

    有的脚本（normalize 等）把结果全写进 JSON、stdout 只印一行文件路径，
    这时 JSON 是唯一的指标来源，不能因为 stdout 没数就判失败。
    """
    if not isinstance(data, dict):
        return existing
    have = {m.name for m in existing}
    out = list(existing)

    def take(prefix: str, d: dict) -> None:
        for k, v in d.items():
            if len(out) >= limit:
                return
            name = f"{prefix}{k}"
            if name in have or isinstance(v, bool):
                continue
            if isinstance(v, (int, float)) and any(t in k.lower() for t in _NUM_KEYS):
                out.append(Metric(name=name, value=round(float(v), 4)))
                have.add(name)

    take("", data)
    # 常见嵌套：{"summary": {...}} / {"overall": {...}} / {"baseline": {...}}
    for key in ("summary", "overall", "totals", "baseline", "report"):
        if isinstance(data.get(key), dict):
            take("", data[key])
    # 分路结果：{"result": {"emb": {"top1": …, "top10": …}, "cls": {…}}}（eval_oov 等 5b 评测器），
    # 以前一条都抠不出来，脚本跑通了也判 failed（2026-11-04）
    for key in ("result", "results", "rows"):
        if isinstance(data.get(key), dict):
            for sub, d in data[key].items():
                if isinstance(d, dict):
                    take(f"{sub} ", d)
    for dk in ("n", "total", "n_samples", "count", "n_gold"):
        if isinstance(data.get(dk), int):
            for m in out:
                if m.denominator is None:
                    m.denominator = data[dk]
            break
    return out


