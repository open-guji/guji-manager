"""第三步识字（3a 库匹配、3b 生僻字候选）评测器的结构化指标与钉版记录（A23，2026-11-23）。

通用的 `parse_metrics` 是从 stdout 抠数，认不出这几个脚本的输出：
match_pairs*、sim_bench 脚本跑完、数都在 JSON 里，runner 却报「跑不起来」；
match_bench 只抠到一个「头条 n」；rare_* 的头条是 cls 路（生产用的是 emb 路），
没拉向量包时全 0% 还报 ok（静默假数）。这里按评测器 id 直接读脚本写的 JSON，
取方案里定的头条指标（护栏指标在前），并给出「数是在什么上量的」的钉版记录。
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from .report import Metric


def _m(name: str, v, unit: str = "", den: int | None = None, num: int | None = None, note: str = "") -> Metric:
    if isinstance(v, float):
        v = round(v, 4)
    return Metric(name=name, value=v, numerator=num, denominator=den, unit=unit, note=note)


def _pct(x):
    return None if x is None else round(100.0 * x, 2)


def _match_bench(data: dict) -> list[Metric]:
    books = [k for k in data if k != "protocol" and isinstance(data[k], dict) and "headline" in data[k]]
    out: list[Metric] = []
    for b in books:
        h = data[b]["headline"]
        n_ans, n_nov = h.get("n_ans"), h.get("n_novel")
        pre = f"{b} " if len(books) > 1 else ""
        n_same = round((h.get("same_cov") or 0) * (n_ans or 0))
        out += [
            _m(pre + "same 精度", _pct(h.get("same_prec")), "%", den=n_same or None,
               num=(n_same - h.get("same_err", 0)) if n_same else None, note=f"错 {h.get('same_err')} 格"),
            _m(pre + "novel 误放", h.get("novel_false_same_n"), "", den=n_nov),
            _m(pre + "same 覆盖", _pct(h.get("same_cov")), "%", den=n_ans),
            _m(pre + "rank1", _pct(h.get("rank1")), "%", den=n_ans),
            _m(pre + "rank5", _pct(h.get("rank5")), "%", den=n_ans),
            _m(pre + "auroc", h.get("auroc"), den=n_ans),
            _m(pre + "P0.999 召回", _pct((h.get("recall@P0.999") or {}).get("recall")), "%", den=n_ans),
            _m(pre + "ms/格 p50", h.get("ms_p50")),
        ]
        hp = data[b].get("hard_pair") or {}
        if hp:
            out.append(_m(pre + "hard_pair rank1", _pct(hp.get("rank1")), "%", den=hp.get("n_ans")))
    return out


def _match_pairs(data: dict) -> list[Metric]:
    k = data.get("knn") or {}
    bo = data.get("best_operating_point") or {}
    return [
        _m("knn 精度", _pct(k.get("precision")), "%", den=(k.get("tp") or 0) + (k.get("fp") or 0) or None,
           num=k.get("tp"), note=f"操作点 cov≥{data.get('cov_high')}"),
        _m("knn 召回", _pct(k.get("recall")), "%", den=k.get("n_same"), num=k.get("tp")),
        _m("P≥0.999 最大召回", _pct(bo.get("recall")), "%", den=bo.get("n_same"), num=bo.get("tp"),
           note=f"闸 {bo.get('cov_high')}"),
    ]


def _sim_bench(data: dict) -> list[Metric]:
    out: list[Metric] = []
    for algo, r in (data.get("strict") or {}).items():
        if not isinstance(r, dict):
            continue
        n = r.get("n")
        out += [_m(f"{algo} auroc", r.get("auroc"), den=n),
                _m(f"{algo} tpr@0.1%", _pct(r.get("tpr01")), "%", den=n),
                _m(f"{algo} rank1", _pct(r.get("rank1")), "%", den=n)]
    return out


def _rare(data: dict) -> tuple[list[Metric], str]:
    r = data.get("result") or {}
    emb = r.get("emb") or {}
    un, oov = r.get("emb_unseen") or {}, r.get("emb_oov") or {}
    n = data.get("n")
    out = [
        _m("unseen top10", un.get("top10"), "%", den=un.get("n"), note="护栏：不退步"),
        _m("emb top1", emb.get("top1"), "%", den=n),
        _m("emb top10", emb.get("top10"), "%", den=n),
        _m("oov top1", oov.get("top1"), "%", den=oov.get("n")),
        _m("oov top10", oov.get("top10"), "%", den=oov.get("n")),
    ]
    err = ""
    if n and not emb.get("top10"):
        err = ("emb top10 为 0：多半没有向量包（静默假数，判失败）。先跑 "
               "`guji cache pull-rare-index --charset unicode-cjk-ab`")
    return out, err


def extract(eval_id: str, data) -> tuple[list[Metric] | None, str]:
    """返回 (指标, 错误)。指标为 None 表示这个评测器不归这里管，照通用解析。"""
    if not isinstance(data, dict):
        return None, ""
    if eval_id.startswith("match_bench"):
        return _match_bench(data), ""
    if eval_id.startswith("match_pairs"):
        return _match_pairs(data), ""
    if eval_id == "sim_bench":
        return _sim_bench(data), ""
    if eval_id.startswith("rare_") and eval_id != "rare_char":
        return _rare(data)
    return None, ""


READ_EVALS_PREFIX = ("match_bench", "match_pairs", "sim_bench", "rare_", "db_match", "match_triplets",
                     "oov", "degradation", "zero_shot")


def _sha16(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _git_head(d: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(d), "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except Exception:   # noqa: BLE001
        return ""


def bench_lock(eval_id: str, cv_root: Path, dataset_root: Path) -> dict:
    """识字评测的钉版记录：库、代码、数据集各是哪一版。库一变数就漂，不同 lock 的数不能直接比。"""
    if not eval_id.startswith(READ_EVALS_PREFIX):
        return {}
    lock = {"cv": _git_head(cv_root), "dataset": _git_head(dataset_root)}
    db = os.environ.get("GUJI_GLYPH_DB") or ""
    if not db and os.environ.get("GUJI_WORKSPACE"):
        db = str(Path(os.environ["GUJI_WORKSPACE"]) / "output" / "glyph.db")
    if db and Path(db).is_file():
        lock["glyph_db"] = Path(db).name
        lock["glyph_db_sha16"] = _sha16(Path(db))
    else:
        lock["glyph_db"] = "未指定（GUJI_GLYPH_DB）"
    return lock
