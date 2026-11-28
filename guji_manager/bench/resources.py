"""按书备齐 bench 要的资源，填进 `BenchCtx.res`／`env`（GM2 审；与任务库预检 `jobs/precheck` 共用钉子读法）。

缓存根 `$GUJI_DATA_HOME/bench-cache/`（`--cache` 可改）：
- `books/<书id>/`：书仓检出（`code/`、`workspace.yaml`、`.central.json`），中心库数据由 `guji db pull` 拉到
  `datahome/`（缓存自己的 GUJI_DATA_HOME，组配置在 `datahome/main/.borrowed/group-*`）；
- `products/<书id>/<标签>/<册>/`：产物包，按标签复用。
取不到就抛 `Missing`（说明怎么补），不出半截结果；不回退到本机别处的字形库或产物。
"""
from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

#: needs 里由 cv 运行时自己按钉子取回（模型表、语料表）的，只核取回令牌在不在
_SELF_FETCH = {"models": "GUJI_DATA_TOKEN_READ", "corpus": "GUJI_DATA_TOKEN_READ"}


class Missing(Exception):
    def __init__(self, kind: str, why: str, how: str = ""):
        super().__init__(f"缺资源 {kind}：{why}" + (f"（{how}）" if how else ""))
        self.kind, self.why, self.how = kind, why, how


def guji_exe() -> str:
    """`guji` 总入口（带 manager 插件；`python -m open_guji_cv` 不载插件）。"""
    import shutil
    p = Path(sys.executable).with_name("guji")
    return str(p) if p.exists() else (shutil.which("guji") or "guji")


def cache_root(opt: str | None = None) -> Path:
    if opt:
        return Path(opt).expanduser().resolve()
    from .._cv import data_home
    return data_home() / "bench-cache"


def _git(*a, cwd=None) -> str:
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def git_head(p: Path) -> str | None:
    try:
        return _git("rev-parse", "HEAD", cwd=p) + ("+dirty" if _git("status", "--porcelain", cwd=p) else "")
    except Exception:                                     # noqa: BLE001
        return None


@contextmanager
def env(**kv):
    old = {k: os.environ.get(k) for k in kv}
    os.environ.update({k: str(v) for k, v in kv.items()})
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ------------------------------------------------------------------ 金标
def dataset_root(opt: str | None = None) -> Path:
    from .._cv import default_dataset_root
    p = Path(opt).expanduser() if opt else default_dataset_root()
    if not p.exists():
        raise Missing("gold", f"找不到测试集仓 {p}",
                      "克隆 open-guji/open-guji-dataset 到 open-guji-cv 旁边，或设 GUJI_DATASET_DIR，或 --dataset")
    return p.resolve()


def gold_dir(spec, book: str, vols: list[str], ds: Path) -> Path | None:
    """这本书的金标目录；没有返回 None（→ no_gold）。册一级显式表按第一个给的册取。"""
    rel = spec.gold_rel(book, vols[0] if vols else None)
    if rel is None:
        return None
    p = ds / rel
    return p if p.exists() else None


# ------------------------------------------------------------------ 书仓与中心库
def _local_repo(book: str) -> Path | None:
    """本机已有的书仓（`GUJI_BOOKS_DIR`，缺省 `~/guji-workspace`）：从它克隆，省一次网络。"""
    root = Path(os.environ.get("GUJI_BOOKS_DIR") or Path.home() / "guji-workspace").expanduser()
    hit = [p for p in root.glob(f"{book}-*") if (p / ".git").exists()] + \
        ([root / book] if (root / book / ".git").exists() else [])
    return hit[0] if len(hit) == 1 else None


def _find_repo(book: str) -> str:
    names: list[str] = []
    for cmd in (["gh", "api", f"search/repositories?q=org:guji-workspace+{book}+in:name", "-q", ".items[].name"],
                ["gh", "api", "--paginate", "orgs/guji-workspace/repos", "-q", ".[].name"]):
        try:
            names = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.split()
        except Exception:                                  # noqa: BLE001
            continue
        if names:
            break
    hit = [n for n in names if n == book or n.startswith(f"{book}-")]
    if len(hit) != 1:
        raise Missing("code", f"guji-workspace 下书仓 {book}-* 找到 {len(hit)} 个", "用 --ws 指本机书仓目录")
    return hit[0]


def book_ws(book: str, cache: Path, ws_opt: str | None = None, update: bool = True) -> Path:
    """书仓：给了 `--ws` 用它（不改它），否则克隆／更新到缓存。"""
    if ws_opt:
        p = Path(ws_opt).expanduser().resolve()
        if not (p / "workspace.yaml").exists():
            raise Missing("code", f"{p} 不是工作区（没有 workspace.yaml）")
        return p
    p = cache / "books" / book
    if (p / ".git").exists():
        if update:
            subprocess.run(["git", "pull", "-q", "--ff-only"], cwd=p, check=False)
        return p
    local = _local_repo(book)
    url = str(local) if local else f"https://github.com/guji-workspace/{_find_repo(book)}"
    p.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["git", "clone", "-q", url, str(p)], capture_output=True, text=True)
    if r.returncode:
        raise Missing("code", f"克隆书仓 {url} 失败：{r.stderr.strip()[-200:]}")
    if local:                                          # 远端仍指 GitHub，以后 pull 拿正式版本
        o = _git("remote", "get-url", "origin", cwd=local)
        _git("remote", "set-url", "origin", o, cwd=p)
    return p


def data_home_for(ws: Path, cache: Path, ws_opt: str | None) -> Path:
    """给了 --ws 用本机现成的 GUJI_DATA_HOME；缓存里的书用缓存自己的 datahome。"""
    if ws_opt:
        from .._cv import data_home
        return data_home()
    return cache / "datahome"


#: 不要字形库的 bench 拉的时候跳过这些大头（史記整拉 ~900 MB、跳过后 ~130 MB、25 秒）：事件、身份账、待审单、审阅、产物派生
LIGHT_EXCLUDE = ("feedback/events/", "feedback/uid/", "feedback/consumed/", "feedback/anchor_patches/",
                 "feedback/lists/", "review/", "output/")


def central(ws: Path, dh: Path, glyph: bool) -> Path:
    """`guji db pull` 拉册配置、语料、组配置等共享层；glyph 时整拉（连字形库与借库），否则跳过字形库与 `LIGHT_EXCLUDE`
    （部分副本，push 会被拒；bench 不写库）。返回数据目录。"""
    from .._cv import central_marker
    m = central_marker(ws)
    if not m:
        return ws                                          # 没迁中心库的旧工作区：数据就在工作区里
    cmd = [guji_exe(), "db", "pull", "-w", str(ws), "--no-rebuild"]
    if not glyph:
        cmd += ["--no-glyph"] + [x for p in LIGHT_EXCLUDE for x in ("--exclude", p)]
    e = {**os.environ, "GUJI_DATA_HOME": str(dh), "GUJI_WORKSPACE": str(ws), "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run(cmd, env=e, capture_output=True, text=True)
    if r.returncode:
        raise Missing("config", f"guji db pull 失败：{(r.stderr or r.stdout).strip()[-300:]}",
                      "要中心库读令牌（gsecrets export）")
    return dh / str(m.get("branch") or "main") / str(m["ws"])


def central_rev(dh: Path, ws: Path, data: Path | None = None) -> str | None:
    with env(GUJI_DATA_HOME=dh):
        from .._cv import central_rev as rev
        try:
            return rev(ws)
        except Exception:                                  # noqa: BLE001
            return None


def glyph_pins(ws: Path, dh: Path, vols) -> dict[str, int | None]:
    """各册钉的字形库版本，缺的钉版库按 `guji glyph-db pin-build` 建到工作区 `output/glyph-g<N>.db`（同执行机）。"""
    from ..jobs.precheck import pins_of
    out: dict[str, int | None] = {}
    with env(GUJI_WORKSPACE=ws, GUJI_DATA_HOME=dh):
        for v in vols:
            try:
                n = pins_of(v)["glyph_pin"][0]
            except Exception as e:                         # noqa: BLE001
                raise Missing("glyph_lib", f"读不了册 {v} 的钉子（{type(e).__name__}: {e}）") from e
            out[v] = n
    for n in sorted({n for n in out.values() if isinstance(n, int)}):
        if (ws / "output" / f"glyph-g{n}.db").exists():
            continue
        e = {**os.environ, "GUJI_DATA_HOME": str(dh), "GUJI_WORKSPACE": str(ws), "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run([guji_exe(), "glyph-db", "pin-build", "-w", str(ws), "--pin", str(n)], env=e,
                           capture_output=True, text=True)
        if r.returncode:
            raise Missing("glyph_lib", f"建钉版字形库 g{n} 失败：{(r.stderr or r.stdout).strip()[-300:]}")
    return out


# ------------------------------------------------------------------ 原图、产物
def raw(ws: Path, dh: Path, vol: str, pages: list[int] | None) -> int:
    """取原图落到册 yaml 的原图目录（`raw_path`）：给了页只取这些页，None＝整册（按页表）。返回新写页数。"""
    from .._cv import load_book
    from .._cv import sources as S
    from ..cli_source import _locate, _src
    with env(GUJI_WORKSPACE=ws, GUJI_DATA_HOME=dh):
        bk = load_book(vol)
        if pages is not None and all(bk.raw_path(p).exists() for p in pages):
            return 0
        src = _src()
        book_id, v = _locate(src, S, vol)
        table = S.read_table(src, book_id, v, bk.source_rev)
        if pages is None:
            pages = [x["page"] for x in table["pages"]]
        need = [p for p in pages if not bk.raw_path(p).exists()]
        if not need:
            return 0
        want = set(need)
        table = {**table, "pages": [x for x in table["pages"] if x["page"] in want]}
        got = {x["page"] for x in table["pages"]}
        if got != want:
            raise Missing("raw", f"{vol} 页表 r{table['rev']:03d} 没有这些页：{sorted(want - got)}")
        return S.pull(src, table, bk.raw_path)["written"]


def products(ws: Path, book: str, vol: str, cache: Path, label: str | None = None) -> tuple[Path, str]:
    """取产物包到 `products/<书>/<标签>/<册>/`，返回（包根，标签）。缺省标签＝main 指针。"""
    from ..datastore import packs as P
    with env(GUJI_WORKSPACE=ws):                            # 包键按工作区标记取工作区名
        try:
            lab = label or P.main_label(vol)
        except Exception as e:                             # noqa: BLE001
            raise Missing("products", f"{book}/{vol} 读不到产物包登记（{type(e).__name__}: {e}）",
                          "要中心库读令牌") from e
        if not lab:
            raise Missing("products", f"{book}/{vol} 没有标过 main 的产物包", "用 --label 指一个包")
        root = cache / "products" / book / lab
        if not (root / vol).exists():
            P.fetch_products(vol, root, label=lab)
    return root, lab


# ------------------------------------------------------------------ 环境类
def check_env(needs) -> list[Missing]:
    out = []
    for n in needs:
        if n in _SELF_FETCH and not (os.environ.get(_SELF_FETCH[n]) or os.environ.get("GUJI_DATA_TOKEN")):
            out.append(Missing(n, f"没有 {_SELF_FETCH[n]}", "eval \"$(python3 ~/guji-dev-secret/gsecrets.py export)\""))
        if n in ("torch", "gpu"):
            try:
                import torch
                if n == "gpu" and not torch.cuda.is_available():
                    out.append(Missing("gpu", "没有 GPU"))
            except ImportError:
                out.append(Missing("torch", "没装 torch", "uv pip install -e \"open-guji-cv[torch]\""))
        if n == "ocr":
            try:
                import rapidocr_onnxruntime  # noqa: F401
            except ImportError:
                out.append(Missing("ocr", "没装 rapidocr-onnxruntime"))
    return out
