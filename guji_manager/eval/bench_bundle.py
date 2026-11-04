"""5b 评测集（`cache/glyph_bench`、`cache/oov_bench`）缺了就从冻结包解出来。

这两份集是 2026-09 从当时的殿本字形库长出来的，**不进数据集仓**（glyph_bench 有
15,482 张图、62 MB）；冻结版打在 `guji-workspace/_shared/train_bundle.zip`
（`scripts/export_train_bundle.py` 打的，README 记着 sha256）。

以前缺了就让 oov / degradation / zero_shot 这批评测器一跑就挂（2026-11-04 查评测链
时一半跑不起来，这是原因之一）。现在评测器声明 `needs=("bench",)`，注册表现查：
cache 里已有就用；没有就按钉死的 sha 核对冻结包再解开；包不在或 sha 对不上就照旧
报「需要 5b 评测集」，**不拿别的东西凑**——集一变，前后的数就不能比了。

包的位置：环境变量 `GUJI_TRAIN_BUNDLE`，否则 `<cv 仓>/../guji-workspace/_shared/train_bundle.zip`。
本机重打了包，要同时改下面的 `BUNDLE_SHA256`，并在评测报告里注明集换了版。
"""
from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import Path

BUNDLE_SHA256 = "a1012b50a006e8e225c534e231b1c84f7a850f69b1363182c9bf47e73a483b45"   # 2026-10-14 版
BENCH_DIRS = ("glyph_bench", "oov_bench")


def _repo() -> Path:
    """cv 仓根：cache/ 与评测脚本都在 cv 检出目录下（本模块 11-04 随 eval 搬来 manager）。"""
    from .. import _cv
    return _cv.cv_repo()


def bundle_path() -> Path:
    env = os.environ.get("GUJI_TRAIN_BUNDLE")
    return Path(env) if env else _repo().parent / "guji-workspace" / "_shared" / "train_bundle.zip"


def bench_present(cache: Path | None = None) -> bool:
    cache = cache or _repo() / "cache"
    return all((cache / d / "items.jsonl").exists() for d in BENCH_DIRS)


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_bench(cache: Path | None = None, bundle: Path | None = None,
                 sha256: str = BUNDLE_SHA256) -> tuple[bool, str]:
    """返回 (齐了没有, 说明)。只解 `cache/glyph_bench/`、`cache/oov_bench/` 下的条目。"""
    cache = cache or _repo() / "cache"
    if bench_present(cache):
        return True, "已有"
    bundle = bundle or bundle_path()
    if not bundle.exists():
        return False, f"冻结包不在 {bundle}"
    got = _sha256(bundle)
    if got != sha256:
        return False, f"冻结包 sha256 {got[:12]}… 与钉死的 {sha256[:12]}… 不符"
    root = cache.resolve()
    with zipfile.ZipFile(bundle) as z:
        for info in z.infolist():
            # 包里多套了一层 cache/（cloud_eval.md 记过），去掉它再落到 cache/ 下
            parts = Path(info.filename).parts
            if parts and parts[0] == "cache":
                parts = parts[1:]
            if not parts or parts[0] not in BENCH_DIRS or info.is_dir():
                continue
            dest = (root / Path(*parts)).resolve()
            if root not in dest.parents:        # 防 zip 里的 ../ 越界
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, dest.open("wb") as out:
                out.write(src.read())
    return bench_present(cache), f"已从 {bundle.name} 解出"
