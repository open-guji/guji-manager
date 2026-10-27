"""调用 pipeline 的唯一入口：子进程跑 `guji-cv`（不 import open_guji_cv 的内部）。

pipeline 的二进制由环境变量 `GUJI_CV_BIN` 指定（执行机上是任务点名那版 cv 的 venv 里的 `guji-cv`），缺省找 PATH 上的 `guji-cv`。
子进程里会设 `GUJI_MANAGER_VERSION`，pipeline 把它记进 manifest（仅审计）。
"""

from __future__ import annotations

import json
import os
import subprocess

from . import SUPPORTED_CONTRACT, __version__


class IncompatiblePipeline(RuntimeError):
    pass


def cv_bin() -> str:
    return os.environ.get("GUJI_CV_BIN", "guji-cv")


def child_env(extra: dict | None = None) -> dict:
    return {**os.environ, "GUJI_MANAGER_VERSION": f"m{__version__}", **(extra or {})}


def run(args: list[str], *, capture: bool = False, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([cv_bin(), *args], env=child_env(extra_env), text=True, capture_output=capture)


def pipeline_version() -> dict:
    """`guji-cv version --json`。装的是契约成文前的老版本（没有 version 子命令）时按契约 0 处理。"""
    p = run(["version", "--json"], capture=True)
    if p.returncode != 0:
        return {"cv_version": None, "cv_commit": None, "contract_version": 0, "steps": []}
    return json.loads(p.stdout.strip().splitlines()[-1])


def check_compatible(info: dict | None = None) -> dict:
    """契约版本不在本 manager 支持范围就拒跑。"""
    info = info or pipeline_version()
    lo, hi = SUPPORTED_CONTRACT
    if not lo <= int(info.get("contract_version", 0)) <= hi:
        raise IncompatiblePipeline(
            f"pipeline {info.get('cv_version')} 讲契约 v{info.get('contract_version')}，"
            f"本 manager {__version__} 只支持 v{lo}–v{hi}（见 COMPAT.md）")
    return info
