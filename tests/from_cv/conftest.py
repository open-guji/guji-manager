"""从 open-guji-cv `tests/` 搬来的测试（拆分 P2 第四批起）共用 cv 的测试环境。

cv 的 `tests/conftest.py`（每条测试清空 GUJI_* 环境变量、工作区夹具 `ws` 等）原样借来用，
cv 的 `tests/helpers.py` 也放进 sys.path（`from helpers import make_book`）。
cv 不是可编辑安装（没有 tests/ 目录）时，本目录整个跳过，并提示怎么装。
"""
from __future__ import annotations

import importlib.util
import sys
import warnings

from cv_paths import CV_TESTS, HAVE_CV_TESTS

if HAVE_CV_TESTS:
    for _d in [CV_TESTS, *(p for p in CV_TESTS.iterdir() if p.is_dir() and any(p.glob("test_*.py")))]:
        if str(_d) not in sys.path:
            sys.path.append(str(_d))      # 排在本目录之后：同名的测试模块先用搬来的这份
    _spec = importlib.util.spec_from_file_location("cv_tests_conftest", CV_TESTS / "conftest.py")
    _cv_conftest = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_cv_conftest)
    globals().update({k: v for k, v in vars(_cv_conftest).items() if not k.startswith("__")})
else:
    warnings.warn("tests/from_cv 跳过：cv 不是可编辑安装，找不到 cv 的 tests/（pip install -e <open-guji-cv 检出>）")
    collect_ignore_glob = ["*"]
