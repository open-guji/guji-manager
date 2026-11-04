"""模型、字体、底库语料文件往 R2 上传（拆分 P5，2026-11-04 从 cv `ops/model_blobs.py` 拆来）。

取件（`fetch`、`fetch_registry`、`ensure_*`）留在 cv `open_guji_cv.ops.model_blobs`：它是 pipeline 的输入，
cv 测试开跑也要用；本模块只管往 R2 传，按同一套清单与键（sha256 + `EXT`）。
"""
from __future__ import annotations

from pathlib import Path

from .._cv import ops_model_blobs as _mb
from ..datastore.r2 import upload_files

EXT = _mb.EXT
_paths = _mb._paths
_registry = _mb._registry
_repo_root = _mb._repo_root


def upload(ws: Path, version: int | None = None, execute: bool = False) -> dict:
    from .._cv import core_model_pack as mp
    v = version or (mp.versions(ws) or [None])[-1]
    if not v:
        raise FileNotFoundError("还没有模型清单（先 guji model build）")
    man = mp.load_manifest(ws, v)
    have, missing, stale = {}, [], []
    for it, p in _paths(ws, man):
        if not p.is_file():
            missing.append(it["path"])
        elif mp._sha256(p) != it["sha256"]:
            stale.append(it["path"])
        else:
            have[it["sha256"]] = p
    if stale:
        raise ValueError(f"本机文件内容与 m{v} 清单不符，不上传：{stale[:3]}（先 guji model verify）")
    plan = {"version": v, "files": len(man.get("items") or []), "local": len(have),
            "bytes": sum(p.stat().st_size for p in have.values()), "missing_local": missing, "executed": False}
    if execute:
        plan["upload"] = upload_files(have, bucket="main", ext=EXT)
        plan["executed"] = True
    return plan


def upload_registry(execute: bool = False, kind: str = "model") -> dict:
    """cv 自带表里的文件传进 R2（已有跳过）；本机文件 sha 与表不符拒传。"""
    from .._cv import core_model_pack as mp
    reg, _ = _registry(kind)
    have, missing, stale = {}, [], []
    for i in reg:
        p = _repo_root() / i["path"]
        if not p.is_file():
            missing.append(i["path"])
        elif mp._sha256(p) != i["sha256"]:
            stale.append(i["path"])
        else:
            have[i["sha256"]] = p
    if stale:
        raise ValueError(f"本机文件与{kind}表不符，不上传：{stale[:3]}（先 guji {kind} registry）")
    plan = {"kind": kind, "registry": len(reg), "local": len(have), "missing_local": missing,
            "bytes": sum(p.stat().st_size for p in have.values()), "executed": False}
    if execute:
        plan["upload"] = upload_files(have, bucket="main", ext=EXT)
        plan["executed"] = True
    return plan
