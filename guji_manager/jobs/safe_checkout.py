"""git checkout 遇「未跟踪文件会被覆盖」时自动让路（CV0 11-27 采纳的执行方建议）。

执行机的 cv 检出（/opt/guji-cv-seed）里常有未跟踪文件：比如 v0.7 起 models/、fonts/ 不进仓、从 R2 取回，
切到仍跟踪这些路径的版本（或新提交开始跟踪某个文件）时 checkout 报
「The following untracked working tree files would be overwritten by checkout」，整张单准备失败。

做法（三条，各有测试）：
1. 只处理 checkout 报出的那几个冲突文件：先按原样 checkout，失败时从报错里取文件清单；
   清单里每条都得是仓内、确实未跟踪、确实存在的路径，否则一个都不动、照原错失败。不整仓 clean。
2. 先带时间戳备份到工作区外（缺省 ~/.guji-jobs/checkout-bak/<UTC 时间>-<pid>/<仓名>/<原相对路径>），再从仓里移走，然后重试 checkout。
3. 日志里记下备份路径（返回值和 say 回调都带）。

runner 自更新（执行方 cv 检出 `merge --ff-only origin/dev`、退一步 `checkout --detach origin/dev`）也走 `run`，
同一套规则（11-27 worker-24 被未跟踪 config/groups/wu/rules.yaml 挡住自更新、每 10 分钟退出一次）。

命令行（准备脚本 rerun_prep.sh 也用同一套规则，见 cv scripts/rerun_prep.sh 的 safe_checkout）：
    python -m guji_manager.jobs.safe_checkout <仓目录> <ref>
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

#: git 的说法：文件挡路（overwritten）、目录里的未跟踪文件会被删（removed）；checkout 和 merge（runner 自更新的 ff）各一套
_HEADS = tuple(f"untracked working tree files would be {how} by {op}"
               for op in ("checkout", "merge") for how in ("overwritten", "removed"))


def backup_root() -> Path:
    """备份根目录：工作区外。可用 GUJI_CHECKOUT_BAK 改。"""
    env = os.environ.get("GUJI_CHECKOUT_BAK")
    if env:
        return Path(env)
    home = Path(os.environ.get("GUJI_JOBS_HOME", str(Path.home() / ".guji-jobs")))
    return home / "checkout-bak"


def conflict_paths(err: str) -> list[str]:
    """从 checkout 报错里取「未跟踪文件会被覆盖／删除」那几条路径（git 用 tab 缩进逐行列出）。没有这类报错回空。"""
    out: list[str] = []
    grab = False
    for line in err.splitlines():
        low = line.lower()
        if any(h in low for h in _HEADS):
            grab = True
            continue
        if grab:
            if line.startswith("\t"):
                p = line.strip()
                if p and p not in out:
                    out.append(p)
            else:
                grab = False
    return out


def _git(repo: Path, *args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    env = {**os.environ, "LC_ALL": "C", "LANG": "C", "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(["git", "-c", "core.quotePath=false", "-C", str(repo), *args],
                          capture_output=True, text=True, timeout=timeout, env=env)


def _is_tracked(repo: Path, rel: str) -> bool:
    return _git(repo, "ls-files", "--error-unmatch", "--", rel).returncode == 0


def _safe_rel(repo: Path, rel: str) -> bool:
    """仓内的相对路径（不带 ..、不是绝对路径、带引号的怪名字不认），且实际存在。"""
    if not rel or rel.startswith(("/", '"')) or ".." in Path(rel).parts or rel == ".git" or rel.startswith(".git/"):
        return False
    p = repo / rel
    try:
        p.resolve().relative_to(repo.resolve())
    except ValueError:
        return False
    return p.exists() or p.is_symlink()


class CheckoutError(RuntimeError):
    pass


def run(repo: str | Path, args: list[str] | tuple[str, ...], *, label: str | None = None, say=print,
        timeout: int = 600) -> list[Path]:
    """git <args>（checkout 或 merge）；遇未跟踪文件冲突时备份、移走报出的那几个文件后重试一次。
    返回备份到的路径（没冲突回空）。最终失败抛 CheckoutError（带 git 原话）。"""
    repo = Path(repo)
    args = list(args)
    label = label or " ".join(a for a in args if a != "-q")
    r = _git(repo, *args, timeout=timeout)
    if r.returncode == 0:
        return []
    err = (r.stderr or "") + (r.stdout or "")
    rels = conflict_paths(err)
    if not rels:
        raise CheckoutError(err.strip()[-800:])
    bad = [x for x in rels if not _safe_rel(repo, x) or _is_tracked(repo, x)]
    if bad:     # 清单里有说不清的路径：一个都不动，照原错失败
        raise CheckoutError(f"未跟踪文件冲突里有不能自动处理的路径 {bad[:5]}，未动任何文件：{err.strip()[-600:]}")
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + f"-{os.getpid()}"
    dest_root = backup_root() / stamp / repo.resolve().name
    if dest_root.resolve().is_relative_to(repo.resolve()):
        raise CheckoutError(f"备份目录 {dest_root} 在仓 {repo} 里面，不处理")
    moved: list[Path] = []
    for rel in rels:
        dst = dest_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(repo / rel), str(dst))      # 备份即移走：原文件留在工作区外，可原样放回
        moved.append(dst)
    say(f"[safe_checkout] {repo} {label} 遇 {len(rels)} 个未跟踪文件冲突，已备份到 {dest_root} 后移走："
        + "，".join(rels[:10]) + ("…" if len(rels) > 10 else ""))
    r = _git(repo, *args, timeout=timeout)
    if r.returncode != 0:
        raise CheckoutError(f"移走冲突文件（备份在 {dest_root}）后 {label} 仍失败："
                            + ((r.stderr or "") + (r.stdout or "")).strip()[-600:])
    return moved


def checkout(repo: str | Path, ref: str, *, extra: tuple[str, ...] = ("-q",), say=print, timeout: int = 600) -> list[Path]:
    """git checkout <extra> <ref>，未跟踪文件冲突自动让路（见 `run`）。"""
    return run(repo, ["checkout", *extra, ref], label=f"切 {ref}", say=say, timeout=timeout)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("用法：python -m guji_manager.jobs.safe_checkout <仓目录> <ref>", file=sys.stderr)
        return 2
    try:
        checkout(argv[0], argv[1], say=lambda m: print(m, file=sys.stderr))
    except CheckoutError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
