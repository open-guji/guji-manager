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


def _nearform(data: dict) -> list[Metric]:
    r = data.get("result") or {}
    out: list[Metric] = []
    for key, label in (("全部|全部", ""), ("全部|test", "test "), ("文意三对|全部", "文意三对 ")):
        x = r.get(key)
        if not x:
            continue
        n = x.get("n")
        out += [_m(f"{label}对家误认", x.get("pair_confuse"), "格", den=n,
                   note=("护栏：不增" if not label else "")),
                _m(f"{label}首位对", x.get("top1"), "%", den=n),
                _m(f"{label}两字间", x.get("two_way"), "%", den=n)]
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
    # 其他分层（如首次字头格的 firstseen／extB+）照报
    for k, v in sorted(r.items()):
        if k.startswith("emb_") and k not in ("emb_unseen", "emb_oov") and isinstance(v, dict):
            out += [_m(f"{k[4:]} top1", v.get("top1"), "%", den=v.get("n")),
                    _m(f"{k[4:]} top10", v.get("top10"), "%", den=v.get("n"))]
    out = [m for m in out if m.value is not None]
    err = ""
    if n and not emb.get("top10"):
        err = ("emb top10 为 0：多半没有向量包（静默假数，判失败）。先跑 "
               "`guji cache pull-rare-index --charset unicode-cjk-ab`")
    return out, err


def _advset(data: dict) -> list[Metric]:
    h = data.get("headline") or {}
    res = (data.get("result") or {}).get(h.get("way"), {})
    near, var = res.get("形近") or {}, res.get("异体") or {}
    return [
        _m("形近误认", h.get("near_false_same"), den=near.get("n_query"), note=f"判官 {h.get('way')}；护栏：不增"),
        _m("形近误认率", _pct(h.get("near_false_same_rate")), "%", den=near.get("n_query")),
        _m("其中对家", near.get("partner_false_same"), den=near.get("n_query")),
        _m("异体下 same", h.get("variant_false_same"), den=var.get("n_query")),
    ]


def _match_pool(data: dict) -> list[Metric]:
    h = data.get("headline") or {}
    res = (data.get("result") or {}).get(h.get("way"), {})
    out = [_m("误放", h.get("false_same"), den=(res.get("全部") or {}).get("n"), note=f"判官 {h.get('way')}；护栏：不增")]
    for k in ["全部"] + sorted(x for x in res if x != "全部"):
        v = res[k]
        out += [_m(f"{k} 首位", _pct(v.get("rank1_rate")), "%", den=v.get("n")),
                _m(f"{k} 放行", _pct(v.get("accept_rate")), "%", den=v.get("n"))]
    return out


def _near(data: dict) -> list[Metric]:
    """3b 形近字组整体（eval_near.py）：每书 test 册每个「方法:组」的触发、覆盖、准确率、弃权、ECE、耗时。"""
    out: list[Metric] = []
    for h in data.get("headline") or []:
        pre = f"{h['book']} {h['method']}:{h['group']} "
        cov = h.get("coverage") or {}
        out += [_m(pre + "触发", h.get("triggered"), "格", den=h.get("cells")),
                _m(pre + "准确率", _pct(h.get("acc")), "%", den=h.get("decided"), num=h.get("right"),
                   note=f"错 {h.get('wrong')} 格"),
                _m(pre + "弃权率", _pct(h.get("abstain_rate")), "%", den=h.get("scored")),
                _m(pre + "每格耗时", h.get("ms_per_cell"), "ms")]
        if cov.get("n"):
            out.append(_m(pre + "覆盖率", _pct(cov.get("rate")), "%", den=cov.get("n"), num=cov.get("covered")))
        if h.get("ece") is not None:
            out.append(_m(pre + "ECE", h.get("ece"), "", den=h.get("ece_n"), note=str(h.get("calib_version") or "")))
    return out


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
    if eval_id.startswith("advset"):
        return _advset(data), ""
    if eval_id.startswith("nearform"):
        return _nearform(data), ""
    if eval_id.startswith("match_pool"):
        return _match_pool(data), ""
    if eval_id.startswith("rare_") and eval_id != "rare_char":
        return _rare(data)
    if eval_id == "near":
        return _near(data), ""
    return None, ""


READ_EVALS_PREFIX = ("near", "advset", "nearform", "match_pool", "match_bench", "match_pairs", "sim_bench", "rare_", "db_match", "match_triplets",
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


def bench_lock(eval_id: str, cv_root: Path, dataset_root: Path, data: dict | None = None) -> dict:
    """识字评测的钉版记录：库、代码、数据集各是哪一版。库一变数就漂，不同 lock 的数不能直接比。"""
    if not eval_id.startswith(READ_EVALS_PREFIX):
        return {}
    lock = {"cv": _git_head(cv_root), "dataset": _git_head(dataset_root)}
    if eval_id.startswith(("advset", "match_pool")):
        return lock
    if eval_id == "near":
        # 3b 不碰字形库：钉的是各书方法指纹（模型文件、校准表）
        lock["methods_sha"] = (data or {}).get("methods_sha") or {}
        return lock
    if eval_id.startswith("rare_"):
        # 5b 检索的是字表向量包，不碰字形库：钉字表与模型（模型随 cv 提交）
        d = data or {}
        if d.get("charset"):
            lock["charset"] = d["charset"]
        if d.get("ckpt"):
            lock["model"] = Path(str(d["ckpt"])).parent.name
        return lock     # 分片自带图块，不碰字形库；模型随 cv 提交钉住
    db = os.environ.get("GUJI_GLYPH_DB") or ""
    if not db and os.environ.get("GUJI_WORKSPACE"):
        db = str(Path(os.environ["GUJI_WORKSPACE"]) / "output" / "glyph.db")
    if db and Path(db).is_file():
        lock["glyph_db"] = Path(db).name
        lock["glyph_db_sha16"] = _sha16(Path(db))
    else:
        lock["glyph_db"] = "未指定（GUJI_GLYPH_DB）"
    return lock
