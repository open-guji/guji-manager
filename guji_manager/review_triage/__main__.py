"""python -m guji_manager.review_triage <命令>（也挂在 `guji-manager triage`）。

  prepare  候选格 jsonl ＋ 裁图 → 每格特征（几何＋OCR）jsonl
  eval     特征 ＋ 人审标注 → 按页交叉验证的放行/误放表
  train    特征 ＋ 人审标注 → 模型 pkl
  route    特征 ＋ 模型 → 每格去向（skip/pass/withdraw/review）json
  sheet    候选格 ＋ route 结果 ＋ 裁图 → 快审页 HTML（只含 review 格，用 Artifact 发布，要 db 能力）

候选格 jsonl 每行至少有 {"id": 格号, "ref": 参校字}。
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path


def _rows(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def _write_rows(path, rows):
    Path(path).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def cmd_prepare(a):
    from .cells import patch_path
    from .geometry import features, read_gray
    rows, out, miss = _rows(a.cells), [], 0
    ocr = None
    if not a.no_ocr:
        from .ocr import OcrScorer, ocr_features
        ocr = OcrScorer()
    for n, r in enumerate(rows):
        p = patch_path(Path(a.patches), r["id"], a.layout)
        if not p.exists():
            miss += 1; continue
        g = read_gray(p)
        r["f"] = features(g)
        if ocr:
            o = ocr.score(g, r.get("ref")); r.update(o); r["f"].update(ocr_features(o, r.get("ref")))
        out.append(r)
        if n and n % 1000 == 0:
            print(n, file=sys.stderr)
    _write_rows(a.out, out)
    print(f"{len(out)} 格写入 {a.out}；缺裁图 {miss}")


def _labeled(a):
    from .labels import load_review_dir
    lab = load_review_dir(*map(Path, a.labels))
    return [r | {"label": lab[r["id"]]} for r in _rows(a.features) if r["id"] in lab]


def _in_review(r) -> bool:
    from .rules import route
    return route(r["id"], r.get("ref"), None, None)[0] != "skip"


def cmd_eval(a):
    import numpy as np
    from .cells import CellId
    from .model import cv_scores, table
    rows = _labeled(a)
    y = np.array([r["label"] == "bad" for r in rows])
    groups = [CellId.parse(r["id"]).page_key for r in rows]
    m = np.array([_in_review(r) for r in rows]) if a.body_only else np.ones(len(rows), bool)
    print(f"标注 {len(rows)} 格（拦下 {int(y.sum())}）全部参与训练；报告 {int(m.sum())} 格（拦下 {int(y[m].sum())}）")
    for name, use_ocr in (("几何", False), ("几何+OCR", True)):
        p = cv_scores(rows, groups, use_ocr)
        for t in table(p[m], y[m]):
            print(name, json.dumps(t, ensure_ascii=False))


def cmd_train(a):
    """训练用全部标注；阈值按交叉验证、在会进快审的格上取「拦下 ≥ --recall」的那一档（--threshold 可直接指定）。"""
    import numpy as np
    from .cells import CellId
    from .model import cv_scores, table, train
    rows = _labeled(a)
    th, info = a.threshold, None
    if th is None:
        y = np.array([r["label"] == "bad" for r in rows])
        m = np.array([_in_review(r) for r in rows])
        p = cv_scores(rows, [CellId.parse(r["id"]).page_key for r in rows], not a.no_ocr)
        info = table(p[m], y[m], (a.recall,))[0]
        th = info["threshold"]
    model = train(rows, not a.no_ocr, th, {"n": len(rows), "labels": a.labels, "cv": info})
    model.save(a.out)
    print(f"模型写入 {a.out}（{len(rows)} 格，阈值 {th}）" + (f"；交叉验证 {json.dumps(info, ensure_ascii=False)}" if info else ""))


def cmd_route(a):
    from .model import Model
    from .rules import route
    m = Model.load(a.model)
    th = a.threshold if a.threshold is not None else m.threshold
    rows = _rows(a.features)
    ps = m.score(rows) if rows else []
    out, cnt = {}, collections.Counter()
    for r, p in zip(rows, ps):
        dest, why = route(r["id"], r.get("ref"), float(p), r.get("ocr"), th, a.col_len)
        out[r["id"]] = {"route": dest, "why": why, "p_bad": round(float(p), 4),
                        "ocr": r.get("ocr"), "ocr_conf": round(float(r.get("ocr_conf", 0)), 3)}
        cnt[dest] += 1
    Path(a.out).write_text(json.dumps({"threshold": th, "counts": cnt, "cells": out}, ensure_ascii=False),
                           encoding="utf-8")
    print(dict(cnt))


def cmd_sheet(a):
    from .sheet import build
    routes = json.loads(Path(a.routes).read_text(encoding="utf-8"))["cells"]
    st = build(_rows(a.cells), routes, Path(a.patches), a.book, Path(a.out), a.layout, a.per_page, a.per_char)
    print(st)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="guji-manager triage", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("cells"); p.add_argument("patches"); p.add_argument("out")
    p.add_argument("--layout", choices=["cache", "flat"], default="cache",
                   help="cache＝工作区 cache 目录（<册>/char_patch/）；flat＝<册>/ 直接放图")
    p.add_argument("--no-ocr", action="store_true")
    for name in ("eval", "train"):
        p = sub.add_parser(name); p.add_argument("features")
        p.add_argument("labels", nargs="+", help="快审页 db 集合 review 导出的目录（可多个）")
        p.add_argument("--body-only", action="store_true", help="eval：训练仍用全部标注，只在会进快审的格（去掉列首尾、小注等）上报数")
        if name == "train":
            p.add_argument("out"); p.add_argument("--threshold", type=float)
            p.add_argument("--recall", type=float, default=0.9, help="要拦下的人拦格比例（缺省 0.9）")
            p.add_argument("--no-ocr", action="store_true")
    p = sub.add_parser("route"); p.add_argument("features"); p.add_argument("model"); p.add_argument("out")
    p.add_argument("--threshold", type=float); p.add_argument("--col-len", type=int, default=21)
    p = sub.add_parser("sheet"); p.add_argument("cells"); p.add_argument("routes"); p.add_argument("patches")
    p.add_argument("out"); p.add_argument("--book", required=True, help="页面与 db 文档里的批次名，如 01-10r3（每轮换新名）")
    p.add_argument("--layout", choices=["cache", "flat"], default="cache")
    p.add_argument("--per-page", type=int, default=40); p.add_argument("--per-char", type=int, default=3)
    a = ap.parse_args(argv)
    {"prepare": cmd_prepare, "eval": cmd_eval, "train": cmd_train, "route": cmd_route,
     "sheet": cmd_sheet}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
