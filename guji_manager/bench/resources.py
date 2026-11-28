"""按书备齐 bench 要的资源，填进 `BenchCtx.res`／`env`（GM2 审；与任务库预检 `jobs/precheck` 共用钉子读法）。

缓存根 `$GUJI_DATA_HOME/bench-cache/`（`--cache` 可改）：
- `books/<书id>/`：书仓检出（`code/`、`workspace.yaml`、`.central.json`），中心库数据由 `guji db pull` 拉到
  `datahome/`（缓存自己的 GUJI_DATA_HOME，组配置在 `datahome/main/.borrowed/group-*`）；
- `products/<书id>/<标签>/<册>/`：产物包，按标签复用。
取不到就抛 `Missing`（说明怎么补），不出半截结果；不回退到本机别处的字形库或产物。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

#: needs 里由 cv 运行时自己按钉子取回（模型表、语料表）的，只核取回令牌在不在
_SELF_FETCH = {"models": "GUJI_DATA_TOKEN_READ", "corpus": "GUJI_DATA_TOKEN_READ"}   # corpus 另由 `corpus()` 按钉子取齐


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


@contextmanager
def lock(cache: Path, book: str, timeout: float = 3600):
    """同机同书的备资源串行：书仓 git pull、`db pull`、钉版库建库都写缓存里同一个目录，执行机上同时领到两张 bench 单
    （或本机开两个终端）会互相踩。`fcntl.flock` 锁 `<cache>/locks/<书>.lock`，等不到报 Missing；没有 fcntl（Windows）就不锁。"""
    try:
        import fcntl
    except ImportError:                                    # pragma: no cover
        yield
        return
    import time
    d = cache / "locks"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{book}.lock", "w") as fh:
        t0 = time.time()
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() - t0 > timeout:
                    raise Missing("lock", f"等同书 {book} 的另一次备资源超过 {timeout:.0f} 秒") from None
                time.sleep(2)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


# ------------------------------------------------------------------ 模型
def models() -> dict:
    """按 cv 自带的模型表（config/model-registry.json）把 models/ 缺的文件从 R2 补齐，同 `guji model fetch`（不给 -w）。

    bench 跑 cv 走 `python -m open_guji_cv`，不载 manager 插件、不会自己取模型；干净会话里 models/ 是空的，
    册配置开了 5a 相似度 CNN 之类（全唐文 glyph_sim_qtw_v2）的书切字一跑就缺文件。返回取回统计，进结果 env。"""
    r = subprocess.run([guji_exe(), "model", "fetch", "--json"], capture_output=True, text=True, check=False)
    if r.returncode:
        raise Missing("models", f"guji model fetch 失败：{(r.stderr or r.stdout).strip()[-300:]}",
                      "要 GUJI_DATA_TOKEN_READ：eval \"$(python3 ~/guji-dev-secret/gsecrets.py export)\"")
    try:
        d = json.loads(r.stdout[r.stdout.index("{"):])
    except ValueError:
        return {}
    if d.get("not_in_r2"):
        raise Missing("models", f"R2 里没有 {d['not_in_r2'][:3]}", "找模型负责线补传（guji model upload --execute）")
    return {k: d[k] for k in ("registry", "missing", "placed") if k in d}


# ------------------------------------------------------------------ 金标
DATASET_REPO = "https://github.com/open-guji/open-guji-dataset"
LEGACY_WS_REPO = "https://github.com/open-guji/guji-workspace"   # 迁仓过渡期旧总仓（同 jobs.runner.LEGACY_WORKSPACE_REPOS）


def dataset_root(opt: str | None = None, *, cache: Path | None = None, rels: list[str] | None = None,
                 ref: str | None = None) -> Path:
    """测试集仓：`--dataset`、`GUJI_DATASET_DIR`、cv 旁边的 open-guji-dataset 依次找。

    都没有、又给了 `cache` 时（干净的云端会话、执行机），自动稀疏克隆到 `<cache>/dataset/`，只检出 `rels`（这次要的金标分片）
    与 `guards/`；以后同一缓存按需追加分片、`git pull` 到最新。`ref`（提交／分支／tag）钉了就检出那一版，
    且只在自动克隆的缓存里认（本机自己的测试集仓不替人切版本，钉了版却用本机仓报缺资源）。不给 `cache` 就照旧报缺资源。"""
    from .._cv import default_dataset_root
    p = Path(opt).expanduser() if opt else default_dataset_root()
    if p.exists():
        import re
        if ref and re.fullmatch(r"[0-9a-f]{7,40}", ref):   # 钉的是提交才核；分支名、tag 在本机仓上不核
            head = git_head(p) or ""
            if not head.startswith(ref):
                raise Missing("gold", f"钉了测试集仓 {ref}，本机 {p} 在 {head[:12] or '?'}",
                              f"git -C {p} checkout {ref}，或不设 GUJI_DATASET_DIR 让它自动取")
        return p.resolve()
    if opt or cache is None:
        raise Missing("gold", f"找不到测试集仓 {p}",
                      "克隆 open-guji/open-guji-dataset 到 open-guji-cv 旁边，或设 GUJI_DATASET_DIR，或 --dataset")
    return _sparse_dataset(cache, rels or [], ref)


def _sparse_dataset(cache: Path, rels: list[str], ref: str | None = None) -> Path:
    d = cache / "dataset"
    want = sorted({r.strip("/") for r in rels if r} | {"guards"})
    with lock(cache, "_dataset"):
        try:
            if not (d / ".git").exists():
                d.parent.mkdir(parents=True, exist_ok=True)
                _git("clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse", DATASET_REPO, str(d))
                _git("sparse-checkout", "set", *want, cwd=d)
            else:
                have = set(_git("sparse-checkout", "list", cwd=d).split())
                if set(want) - have:
                    _git("sparse-checkout", "add", *sorted(set(want) - have), cwd=d)
            # 钉了版本就取那一版（detached），否则跟到默认分支最新
            _git("fetch", "-q", "--depth", "1", "origin", ref or "HEAD", cwd=d)
            _git("checkout", "-q", "--detach", "FETCH_HEAD", cwd=d)
        except subprocess.CalledProcessError as e:
            raise Missing("gold", f"自动取测试集仓失败：{(e.stderr or '').strip()[-200:]}",
                          "要能读 open-guji/open-guji-dataset；或 --dataset 指本机副本") from e
    return d.resolve()


def gold_dir(spec, book: str, vols: list[str], ds: Path) -> Path | None:
    """这本书的金标目录；没有返回 None（→ no_gold）。册一级显式表按第一个给的册取。"""
    rel = spec.gold_rel(book, vols[0] if vols else None)
    if rel is None:
        return None
    p = ds / rel
    return p if p.exists() else None


# ------------------------------------------------------------------ 书仓与中心库
def _local_repo(book: str) -> Path | None:
    """本机已有的书仓：从它克隆，省一次网络、也不用另要凭据。

    找的地方与跑批准备（cv `scripts/rerun_prep.sh`）一致：`~/<书仓名>`（会话 add_repo 挂上的、或准备脚本克隆过的），
    再找 `GUJI_BOOKS_DIR`（缺省 `~/guji-workspace`）下的 `<书id>-*` 书仓。"""
    from ..jobs.spec import WS_REPOS
    home = Path.home()
    repo = WS_REPOS.get(book, "")
    if repo and (home / repo.rsplit("/", 1)[-1] / ".git").exists():
        return home / repo.rsplit("/", 1)[-1]
    hit = [p for p in home.glob(f"{book}-*") if (p / ".git").exists() and (p / "workspace.yaml").exists()]
    if len(hit) == 1:
        return hit[0]
    root = Path(os.environ.get("GUJI_BOOKS_DIR") or home / "guji-workspace").expanduser()
    hit = [p for p in root.glob(f"{book}-*") if (p / ".git").exists()] + \
        ([root / book] if (root / book / ".git").exists() else [])
    return hit[0] if len(hit) == 1 else None


def _legacy_ws(book: str) -> Path | None:
    """迁仓过渡期的旧总仓 open-guji/guji-workspace 里这部书的目录（准备脚本读不了书仓时也退回这里，内容相同）。

    本机没有旧总仓就克隆一份到 `~/guji-workspace`，与准备脚本同一路径；读不了返回 None。"""
    gw = Path(os.environ.get("GUJI_LEGACY_WS") or Path.home() / "guji-workspace").expanduser()
    if not (gw / ".git").exists():
        r = subprocess.run(["git", "clone", "-q", "--depth", "1", LEGACY_WS_REPO, str(gw)],
                           capture_output=True, text=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        if r.returncode:
            return None
    hit = [p for p in gw.glob(f"{book}-*") if (p / "workspace.yaml").exists() and not (p / ".git").exists()]
    return hit[0] if len(hit) == 1 else None


def _find_repo(book: str) -> str:
    from ..jobs.spec import WS_REPOS                       # 任务库登记的书仓先用（执行机上不一定有 gh 搜索权限）
    if WS_REPOS.get(book, "").startswith("guji-workspace/"):
        return WS_REPOS[book].split("/", 1)[1]
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


def _pull_cache(book: str, p: Path) -> subprocess.CompletedProcess:
    """更新缓存里的书仓。本机有 `~/<书仓名>` 就同准备脚本先 fetch 它（会话挂上的仓才有凭据），再从它快进；
    没有才直接 pull GitHub。"""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    src = _local_repo(book)
    if src is None:
        return subprocess.run(["git", "pull", "-q", "--ff-only"], cwd=p, capture_output=True, text=True, env=env)
    r = subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=src, capture_output=True, text=True, env=env)
    if r.returncode:
        return r
    r = subprocess.run(["git", "fetch", "-q", str(src), "refs/remotes/origin/main"], cwd=p,
                       capture_output=True, text=True, env=env)
    if r.returncode:
        return r
    return subprocess.run(["git", "merge", "-q", "--ff-only", "FETCH_HEAD"], cwd=p, capture_output=True, text=True, env=env)


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
            r = _pull_cache(book, p)
            if r.returncode:                               # 拉不动就别拿旧检出冒充最新（GM2 审 #1269）
                raise Missing("code", f"更新缓存里的书仓 {p} 失败：{(r.stderr or r.stdout).strip()[-200:]}",
                              "查网络／令牌；或 --offline 明说用缓存，或 --ws 指本机书仓")
        return p
    local = _local_repo(book)
    url = str(local) if local else f"https://github.com/guji-workspace/{_find_repo(book)}"
    p.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["git", "clone", "-q", url, str(p)], capture_output=True, text=True,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if r.returncode:
        shutil.rmtree(p, ignore_errors=True)
        legacy = None if local else _legacy_ws(book)
        if legacy:                                     # 同准备脚本：书仓读不了（会话没挂）退回旧总仓目录（不对它做 git 操作）
            print(f"⚠️ 读不了 {url}（会话里 add_repo 就走新仓），退回旧总仓目录 {legacy}", file=sys.stderr)
            return legacy
        raise Missing("code", f"克隆书仓 {url} 失败：{r.stderr.strip()[-200:]}",
                      "会话里 add_repo 这个书仓，或 --ws 指本机书仓")
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
    """`guji db pull` 拉册配置、语料、组配置等共享层；glyph 时整拉（连字形库与借库）**并重建 glyph.db**，否则跳过字形库与
    `LIGHT_EXCLUDE`（部分副本，push 会被拒；bench 不写库）。返回数据目录。

    glyph 时不带 `--no-rebuild`：没钉 glyph_pin 的册读的是工作区 `output/glyph.db`，带了它会拿缓存里的旧库（或空库）去量，
    正是 workcopy 缩水闸（11-18）防的那个洞（GM2 审 #1269）。钉了版的册另由 `glyph_pins` 建 `glyph-g<N>.db`。"""
    from .._cv import central_marker
    m = central_marker(ws)
    if not m:
        return ws                                          # 没迁中心库的旧工作区：数据就在工作区里
    cmd = [guji_exe(), "db", "pull", "-w", str(ws)]
    if not glyph:
        cmd += ["--no-rebuild", "--no-glyph"] + [x for p in LIGHT_EXCLUDE for x in ("--exclude", p)]
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


def pins(ws: Path, dh: Path, vols) -> dict[str, dict[str, list]]:
    """各册生效的钉子与来源层：{册: {键: [值, 层名]}}，与交单预检 `guji job precheck` 同一个读法（`jobs.precheck.pins_of`，
    含配置组层 `_group`）。整份记进结果 env，事后能原样复现、也能和正式跑批对上。"""
    from ..jobs.precheck import pins_of
    out: dict[str, dict[str, list]] = {}
    with env(GUJI_WORKSPACE=ws, GUJI_DATA_HOME=dh):
        for v in vols:
            try:
                out[v] = {k: [val, src] for k, (val, src) in pins_of(v).items()}
            except Exception as e:                         # noqa: BLE001
                raise Missing("config", f"读不了册 {v} 的钉子（{type(e).__name__}: {e}）") from e
    return out


def drift(ws: Path, dh: Path, pins_by_vol: dict, cv_version: str | None) -> tuple[list[str], list[str]]:
    """run 模式开跑前核钉子：返回（拦住的问题，只提醒的）。

    - 书仓 `code/` 与册钉的 `k<N>` 不一致、或没有那版清单：拦（pipeline 本身也会拒跑，早报省一趟）；
    - 册钉的 `cv_version` 与本机 cv 不同：只提醒、记进 env——bench 本来就常拿新 cv 量老书，不能拦。"""
    from ..jobs.precheck import code_problems
    bad, warn = [], []
    codes = sorted({p["code"][0] for p in pins_by_vol.values() if isinstance(p.get("code", [None])[0], int)})
    with env(GUJI_WORKSPACE=ws, GUJI_DATA_HOME=dh):
        for n in codes:
            bad += code_problems(n, ws)
    cvs = sorted({str(p["cv_version"][0]) for p in pins_by_vol.values() if p.get("cv_version", [None])[0]})
    if cv_version and cvs and cvs != [str(cv_version).lstrip("v")]:
        warn.append(f"册钉 cv_version {'、'.join(cvs)}，本机 cv {cv_version}：结果量的是本机 cv")
    return bad, warn


def glyph_pins(ws: Path, dh: Path, vols, pins_by_vol: dict | None = None) -> dict[str, int | None]:
    """各册钉的字形库版本，缺的钉版库按 `guji glyph-db pin-build` 建到工作区 `output/glyph-g<N>.db`（同执行机）。
    没钉的册（None）用 `central(glyph=True)` 重建过的现行 `output/glyph.db`。"""
    pv = pins_by_vol if pins_by_vol is not None else pins(ws, dh, vols)
    out: dict[str, int | None] = {v: pv[v]["glyph_pin"][0] for v in vols}
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
            # 先取到临时目录、取完整了再改名：中途断了不留半截目录给下次当完整的用（GM2 审 #1269）
            tmp = root.parent / f".tmp-{lab}-{os.getpid()}"
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
            try:
                P.fetch_products(vol, tmp, label=lab)
                root.mkdir(parents=True, exist_ok=True)
                os.replace(tmp / vol, root / vol)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    return root, lab


# ------------------------------------------------------------------ 语料
def corpus(ws: Path, dh: Path, vols, pins_by_vol: dict) -> tuple[dict, dict]:
    """按各册**生效的** `corpus:` 总号（`pins_of`，同交单预检：册 yaml／基础配置里写的那个，不看钉子账最后一行——
    W1 回滚后最后一行不是现行值）展开三层清单（cv `core.corpus_pin.load_manifest`），本机缺的按清单 sha 从 R2 取回
    （`guji corpus fetch` 同一实现 `ops.corpus_pack.fetch_blobs`）。没钉 corpus 的册不猜，报缺资源。

    返回（res，env）：res＝{pin, by_vol: {册: {pin, book_corpus, general_corpus}}, book_corpus, general_corpus}，
    book_corpus＝本书 reference 语料（工作区／中心库整理本），general_corpus＝引擎自带通用语料（`corpus/external/`）；
    env＝{册: {pin, items, digest}}，digest 是清单（root, path, sha256）的哈希。"""
    from .._cv import _base, _not_corpus
    from .._cv import core_corpus_pin_load_manifest as load_manifest
    from ..ops.corpus_pack import fetch_blobs
    by_vol, envv = {}, {}
    with env(GUJI_WORKSPACE=ws, GUJI_DATA_HOME=dh):
        for v in vols:
            n = (pins_by_vol.get(v) or {}).get("corpus", [None])[0]
            if not isinstance(n, int):
                raise Missing("corpus", f"册 {v} 没钉 corpus（生效值 {n!r}），不知道用哪版语料", "册配置写 corpus: N")
            try:
                got = fetch_blobs(ws, n, v)
                man = load_manifest(ws, n, v)
            except (FileNotFoundError, ValueError) as e:
                raise Missing("corpus", f"册 {v} 的语料 corpus {n} 清单读不了：{e}", "先 guji db pull（缓存里应已拉过）") from e
            if got["not_in_r2"] or got["differ_not_overwritten"]:
                raise Missing("corpus", f"册 {v} corpus {n}：R2 缺 {len(got['not_in_r2'])} 个、本机内容与清单不符 "
                              f"{len(got['differ_not_overwritten'])} 个（{(got['differ_not_overwritten'] or got['not_in_r2'])[:3]}）",
                              "R2 缺的找该书负责线 guji corpus upload；不符的删缓存重取")
            items = [i for i in man["items"] if not _not_corpus(i["root"], i["path"])]
            miss = [i["path"] for i in items if not (_base(i["root"], i["path"], ws) / i["path"]).exists()]
            if miss:
                raise Missing("corpus", f"册 {v} corpus {n} 取完仍缺 {len(miss)} 个文件：{miss[:3]}")

            def paths(root):
                return [str(_base(i["root"], i["path"], ws) / i["path"]) for i in items
                        if i["group"] == "reference" and i["root"] == root]
            by_vol[v] = {"pin": n, "book_corpus": paths("ws"), "general_corpus": paths("repo")}
            import hashlib
            dig = hashlib.sha256(json.dumps(sorted((i["root"], i["path"], i["sha256"]) for i in items),
                                            ensure_ascii=False).encode()).hexdigest()[:16]
            envv[v] = {"pin": n, "items": len(items), "digest": dig}     # 清单内容哈希：同号不同内容一眼看出
    uniq = lambda xs: list(dict.fromkeys(xs))                       # noqa: E731
    res = {"pin": sorted({x["pin"] for x in by_vol.values()}), "by_vol": by_vol,
           "book_corpus": uniq(p for x in by_vol.values() for p in x["book_corpus"]),
           "general_corpus": uniq(p for x in by_vol.values() for p in x["general_corpus"])}
    return res, envv


# ------------------------------------------------------------------ 5b 评测集（原 eval/bench_bundle，GM4 交来）
def bench5b() -> Path:
    """5b 评测集 `cache/glyph_bench`、`cache/oov_bench`（不进数据集仓）：已有就用，否则按钉死的 sha 核对冻结包
    `train_bundle.zip` 再解（`eval/bench_bundle.py`，P2 删老框架时搬进本模块）。包不在或 sha 不符报缺资源，不拿别的凑。
    返回 cv 仓的 `cache/` 目录（集落在那里，老评测器也读它）。"""
    from ..eval import bench_bundle as BB
    ok, why = BB.ensure_bench()
    if not ok:
        raise Missing("bench5b", why, f"把 guji-workspace/_shared/train_bundle.zip 放到 {BB.bundle_path()}，或设 GUJI_TRAIN_BUNDLE")
    return BB._repo() / "cache"


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
