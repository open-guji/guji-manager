# -*- coding: utf-8 -*-
"""cv P3 改名护栏：manager 包里不许再拿 cv 的 ADMIT_STEP 或字面 `seed_admit/` 拼产物路径。

cv 改名版（#2033）起 ADMIT_STEP == "char_decide"，没迁移的老册只有 `seed_admit/`，这样拼会静默读空；
写死 `seed_admit/` 则反过来读不到新册。读定字产物一律走 `guji_manager.products_io`（新目录优先、旧目录兜底）。"""
from __future__ import annotations

import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "guji_manager"
BAD = [
    (re.compile(r"from\s+\S*_cv\S*\s+import\s+[^\n]*\bADMIT_STEP\b"), "从 cv 取 ADMIT_STEP"),
    (re.compile(r"""["'/]seed_admit/p"""), "字面 seed_admit/ 路径"),
    (re.compile(r"""/\s*["']seed_admit["']\s*/"""), "Path / \"seed_admit\" /"),
]


def test_no_admit_step_path_building():
    hits = []
    for f in PKG.rglob("*.py"):
        if f.name == "products_io.py":
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for rx, why in BAD:
                if rx.search(line):
                    hits.append(f"{f.relative_to(PKG)}:{i} {why}: {line.strip()}")
    assert not hits, "定字产物改走 products_io（decide_dir/decide_pages/read_decide）：\n" + "\n".join(hits)


def test_char_review_reads_new_and_old_dir(tmp_path):
    """快审页 char_review.load：改名后的 char_decide/ 和没迁移的 seed_admit/ 都读得到。"""
    import json
    from guji_manager.review_pages.char_review import load
    for step in ("char_decide", "seed_admit"):
        prod = tmp_path / step / "01"
        (prod / step).mkdir(parents=True)
        doc = {step: {"columns": [{"col": 1, "chars": [{"id": "01:1:1:1", "char": "之", "admit": True}]}]}}
        (prod / step / "p0001.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        _gm, _ar, sa = load(prod)
        assert sa["01:1:1:1"]["char"] == "之", step
