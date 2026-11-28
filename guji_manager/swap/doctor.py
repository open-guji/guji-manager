"""换单开跑前自检：``guji swap doctor -w <工作区> --book-text <检出> [--cv <cv 检出>] [--books …] [--fix] [--env]``

ZM 11-18 换单提速第 3 项（A31）：殿本换单每次开新容器都要踩一遍同样的坑——PATH 上没有 guji、PYTHONPATH 指错 cv、
少令牌、``-w`` 写成工作区 id 而不是路径、book-text 稀疏检出没有本书目录或 scripts、cv 里没有 CNN 权重
（算相似字时才炸，已经跑了十几分钟）。这里一次查完，缺啥列啥；``--fix`` 只做不碰数据的补齐：
取 cv 缺的模型（``guji model fetch`` 同一个函数）、book-text 稀疏检出补上本书目录与 scripts。
2026-11-27：换单改走 ``guji land``，不再用 ``auto_cycle`` 与各册引擎 worktree，所以不再查引擎。
``--env`` 打印可 ``eval`` 的 export 行（PATH、PYTHONPATH、GUJI_CV、GUJI_WORKSPACE、PYTHONIOENCODING）。

令牌不在这里取：先按项目规矩 ``eval "$(python3 <guji-dev-secret>/gsecrets.py export)"``。
退出码：0 全过，1 有 ✗。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

TOKENS = (("GUJI_DATA_TOKEN", "中心库读写（db pull/sync、取包）", ("GUJI_DATA_TOKEN", "GUJI_DATA_TOKEN_PROD")),
          ("GH_TOKEN", "触发网站发布 proofing-sync、推 book-text", ("GH_TOKEN", "GITHUB_TOKEN")),
          )
# 可选：缺了只提示（0.5.0 起网站票缺省读中心库收件箱，用 GUJI_DATA_TOKEN_READ；CELLREVIEW_TOKEN 只在应急读旧 KV、
# `pending --kv` 直写待审单时用）
OPTIONAL_TOKENS = (("CELLREVIEW_TOKEN", "应急读旧 KV、pending --kv 直写待审单", ("CELLREVIEW_TOKEN",)),)
# 本机 manager／cv 低于这些版本时，换单与收单的行为与文档不符（见 COMPAT.md、CHANGELOG）
MIN_MANAGER = ((0, 5, 0), "读票缺省读 web_inbox、collect 落格修复（≥0.4.68）、--books 区间写法")
MIN_CV = ((0, 9, 0), "cv < 0.9.0 时 `guji pipeline <命令>` 前缀不可用，要写老写法 `guji <命令>`；其余照常（COMPAT.md）")
MIN_FREE_GB = 8.0
_MISSING_MODELS = ("import sys; from open_guji_cv.core import model_pack as mp; "
                   "print(len(mp.missing_repo_models()))")


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def ok(self, what: str, msg: str = "") -> None:
        self.rows.append(("✓", what, msg))

    def warn(self, what: str, msg: str) -> None:
        self.rows.append(("⚠", what, msg))

    def bad(self, what: str, msg: str) -> None:
        self.rows.append(("✗", what, msg))

    @property
    def failed(self) -> bool:
        return any(r[0] == "✗" for r in self.rows)

    def text(self) -> str:
        return "\n".join(f"{m} {w}" + (f"：{s}" if s else "") for m, w, s in self.rows)


def check_workspace(ws_arg: str, r: Report) -> Path | None:
    ws = Path(ws_arg).expanduser()
    if not ws.is_dir():
        hint = "（看着像工作区 id／书 id：-w 要给工作区目录的路径）" if "/" not in ws_arg and "\\" not in ws_arg else ""
        r.bad("工作区 -w", f"{ws_arg} 不是目录{hint}")
        return None
    ws = ws.resolve()
    if not (ws / "workspace.yaml").exists():
        r.bad("工作区 -w", f"{ws} 下没有 workspace.yaml（-w 要指到书的工作区根）")
        return None
    if not (ws / ".central.json").exists():
        r.bad("工作区 -w", f"{ws} 还没迁到中心库（没有 .central.json）：guji db migrate -w {ws}")
        return None
    r.ok("工作区 -w", str(ws))
    return ws


def check_cv(cv_arg: str | None, r: Report) -> Path | None:
    cv = Path(cv_arg).expanduser().resolve() if cv_arg else None
    if not cv or not (cv / "open_guji_cv" / "__init__.py").exists():
        r.bad("cv 检出", f"{cv} 下没有 open_guji_cv 包：--cv 或 GUJI_CV 指到 open-guji-cv 检出")
        return None
    try:
        from .._cv import cv_repo
        got = Path(cv_repo()).resolve()
    except Exception as e:  # noqa: BLE001
        r.bad("cv 包", f"import open_guji_cv 失败（{e}）：uv pip install -e {cv}，或 PYTHONPATH={cv}")
        return cv
    if got != cv:
        r.bad("cv 包", f"Python 用的 open_guji_cv 在 {got}，不是 --cv {cv}：land／cv 子命令会用错版本。"
                       f"PYTHONPATH={cv}（或在 {cv} 里 uv pip install -e .）")
    else:
        r.ok("cv 包", str(got))
    return cv


def _ver(s: str) -> tuple[int, ...] | None:
    import re
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", str(s or ""))
    return tuple(int(x) for x in m.groups()) if m else None


def check_versions(r: Report, manager: str | None = None, cv: str | None = None) -> None:
    """本机 manager、cv 版本太旧就提示（ZM 转 GM2 11-23：对方本机是 manager 0.4.35／cv 0.6.38，换单、收单的坑全踩一遍）。
    只提示不挡（cv 版本读不出就不报）；``manager``／``cv`` 给了就用给的（测试用）。"""
    if manager is None:
        from .. import __version__ as manager
    if cv is None:
        try:      # cv 自己的口径；importlib.metadata 在可编辑安装下报的是上次重装时的旧号
            from .._cv import core_cv_version as CVV
            cv = CVV.describe()[0]
        except Exception:  # noqa: BLE001
            cv = None
    for name, got, (low, why) in (("manager 版本", manager, MIN_MANAGER), ("cv 版本", cv, MIN_CV)):
        v = _ver(got)
        if v is None:
            continue
        if v < low:
            r.warn(name, f"{got} 低于 {'.'.join(map(str, low))}（{why}）：git pull 后 uv pip install --no-deps -e . 升级")
        else:
            r.ok(name, str(got))


def check_cli(r: Report) -> None:
    g = shutil.which("guji")
    if g:
        r.ok("guji 命令", g)
    else:
        r.warn("guji 命令", f"PATH 上没有 guji（脚本内部用 python -m open_guji_cv.cli_v2，不挡；手工命令要 PATH 加 {Path(sys.executable).parent}）")
    if not shutil.which("gh"):
        r.bad("gh 命令", "没有 gh：发站、核网站 workflow 要它")


def check_tokens(r: Report) -> None:
    for name, why, alts in TOKENS:
        if any(os.environ.get(a) for a in alts):
            r.ok(f"令牌 {name}")
        else:
            r.bad(f"令牌 {name}", f"没有（{why}）：先 eval \"$(python3 <guji-dev-secret>/gsecrets.py export)\"")
    for name, why, alts in OPTIONAL_TOKENS:
        if not any(os.environ.get(a) for a in alts):
            r.warn(f"令牌 {name}", f"没设（{why}；缺省读票不需要）")
    if not os.environ.get("GUJI_ACTOR"):
        r.bad("GUJI_ACTOR", "没设：推中心库要有操作人，export GUJI_ACTOR=<你的名字>")


def book_dir_rel(text_id: str) -> str:
    from ..online_lists import book_text_dir
    return Path(book_text_dir(".", text_id)).as_posix().lstrip("./")


def check_book_text(bt_arg: str, text_id: str, r: Report, fix: bool) -> Path | None:
    bt = Path(bt_arg).expanduser().resolve()
    if not (bt / ".git").exists():
        r.bad("book-text", f"{bt} 不是 git 检出")
        return None
    rel = book_dir_rel(text_id)
    need = [p for p in ("scripts", rel) if not (bt / p).exists()]
    if need and fix:
        sparse = subprocess.run(["git", "config", "core.sparseCheckout"], cwd=bt, capture_output=True, text=True).stdout.strip()
        if sparse == "true":
            subprocess.run(["git", "sparse-checkout", "add", *need], cwd=bt, capture_output=True, text=True)
            need = [p for p in need if not (bt / p).exists()]
    if need:
        r.bad("book-text", f"{bt} 缺 {'、'.join(need)}（稀疏检出要含 scripts 和本书目录：git sparse-checkout add {' '.join(need)}；--fix 代做）")
    else:
        r.ok("book-text 目录", f"{bt}（{rel}）")
    st = subprocess.run(["git", "status", "--porcelain", "--", "Book"], cwd=bt, capture_output=True, text=True).stdout.strip()
    if st:
        r.bad("book-text 工作区", f"Book/ 下有未提交改动 {len(st.splitlines())} 处（上一册失败留下的？）："
                                 f"git checkout -- . && git clean -qfd Book")
    br = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=bt, capture_output=True, text=True).stdout.strip()
    if br != "dev":
        r.warn("book-text 分支", f"现在在 {br}，换单提交推 dev，一般检出 dev")
    return bt


def missing_models(repo: Path) -> int | None:
    p = subprocess.run([sys.executable, "-c", _MISSING_MODELS], cwd=repo, capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(repo)})
    try:
        return int(p.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


def fetch_models(repo: Path) -> bool:
    p = subprocess.run([sys.executable, "-c", "from open_guji_cv.ops.model_blobs import fetch_registry as f; print(f('model'))"],
                       cwd=repo, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(repo)})
    return p.returncode == 0


def check_models(repo: Path, what: str, r: Report, fix: bool) -> None:
    n = missing_models(repo)
    if n and fix:
        fetch_models(repo)
        n = missing_models(repo)
    if n is None:
        r.warn(what, f"{repo} 读不了模型表（旧版 cv？）")
    elif n:
        r.bad(what, f"{repo} 缺 {n} 个模型文件（CNN 权重等，apply 的 CNN alt 要用）：cd {repo} && guji model fetch；--fix 代做")
    else:
        r.ok(what, str(repo))


def check_disk(ws: Path, r: Report) -> None:
    free = shutil.disk_usage(ws).free / 2 ** 30
    packs = ws / "_packs"
    used = sum(f.stat().st_size for f in packs.rglob("*") if f.is_file()) / 2 ** 30 if packs.exists() else 0.0
    msg = f"剩 {free:.1f}GB，_packs 占 {used:.1f}GB"
    if free < MIN_FREE_GB:
        r.bad("磁盘", msg + f"（一册沙箱 0.3–5.6GB，要 ≥ {MIN_FREE_GB:g}GB）：清 _packs／cache／旧 export")
    else:
        r.ok("磁盘", msg)


def env_lines(ws: Path | None, cv: Path | None) -> list[str]:
    out = [f'export PATH="{Path(sys.executable).parent}:$PATH"', "export PYTHONIOENCODING=utf-8"]
    if cv:
        out += [f'export PYTHONPATH="{cv}"', f'export GUJI_CV="{cv}"']
    if ws:
        out.append(f'export GUJI_WORKSPACE="{ws}"')
    return out


def cmd_doctor(a, books: list[str]) -> int:
    r = Report()
    fix = bool(getattr(a, "fix", False))
    ws = check_workspace(a.workspace, r)
    cv = check_cv(a.cv, r)
    check_cli(r)
    check_versions(r)
    check_tokens(r)
    if ws:
        from . import data_problem
        from ..datastore.workcopy import data_dir
        try:
            bad = data_problem(data_dir(ws))
        except SystemExit as e:
            bad = str(e)
        (r.warn if a.text_id != "96mid1ogzk" else r.bad)("数据目录", bad) if bad else r.ok("数据目录")
        check_disk(ws, r)
    check_book_text(a.book_text, a.text_id, r, fix)
    if cv:
        check_models(cv, "cv 模型", r, fix)
    print(r.text())
    if getattr(a, "env", False):
        print("\n# 开跑前 eval 下面几行（令牌另由 gsecrets.py export）：")
        print("\n".join(env_lines(ws, cv)))
    print("\n" + ("✗ 有问题，先处理上面的 ✗ 再开跑" if r.failed else "✓ 可以开跑"), file=sys.stderr)
    return 1 if r.failed else 0

