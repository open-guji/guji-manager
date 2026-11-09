"""cv 仓根：本目录的测试从 open-guji-cv `tests/` 搬来，还要用 cv 仓里的脚本、冻结数据与夹具。

要求 cv 以可编辑方式装（`pip install -e <cv 检出>`），这样 `open_guji_cv.__file__` 落在检出里。
本仓 CI（`.github/workflows/test.yml`）检出 cv dev 后可编辑安装。
"""
from pathlib import Path

import open_guji_cv

CV_REPO = Path(open_guji_cv.__file__).resolve().parents[1]
CV_TESTS = CV_REPO / "tests"
HAVE_CV_TESTS = (CV_TESTS / "conftest.py").is_file()

#: 刻本缺省实现的包名：cv 0.7.0 起 `impl.keben`，以前叫 `books.siku_zongmu`（2026-11-09 改名）。
KEBEN = ("open_guji_cv.impl.keben" if (Path(open_guji_cv.__file__).parent / "impl" / "keben").is_dir()
         else "open_guji_cv.books.siku_zongmu")


def keben(mod: str):
    import importlib
    return importlib.import_module(f"{KEBEN}.{mod}")
