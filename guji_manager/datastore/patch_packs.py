"""字块随包存 R2（2026-11-25，CV0；用户 11-25 定「可以打包上传」）：一页的 `char_patch` 打成一个 tar 存 R2，
新容器单跑识字、定字时缓存没有就整页取回，不再从原图冷算（近 7 天这块占 glyph_match 约 35%、seed_admit 约 50%）。

键 ``derived/patch/<ws>/<册>/<页>.<链指纹>.<UTC 日>.tar``（正式桶，经 guji-data Worker `/v1/packs`）：

- **链指纹**（cv `RunContext.chain_fingerprint("cell_shrink", 页)`）＝ cell_shrink 及它全部上游这一页 manifest 指纹的合哈希。
  指纹含各步版本、参数、代码、册配置、上游产物 sha，最上游吃原图 sha；所以键相同即内容相同，
  切分（任一上游）变了这一页换新键，只重打这些页，没变的页不动。
- 一页一个对象（一次 PUT、一次 GET，请求费在免费额度内）；日期只给清理用。
- 包里 ``manifest.json``（册、页、链指纹、cell_shrink 该页产物 sha＝缓存戳、每个文件的 sha256）＋该页全部字块 PNG（不再压）。

取（``fetcher``，manager 启动时注册给 cv 的 ``core.derived.PAGE_FETCHER``）：每个进程每册列一次前缀（一次 LIST），
命中链指纹就取、逐文件核 sha256、戳对得上才写进缓存；任何一步不对就返回 False，cv 照旧现算。
`GUJI_PATCH_FETCH=0` 关（cv 那边查）；没有读令牌不取。

存（``push_book``）：只存 cell_shrink 该页 ok、缓存戳与产物 sha 一致、R2 上还没有这个链指纹的页。
执行机切字单 push 阶段在存产物包之后自动跑（``guji cache push-patches``；`GUJI_PATCH_PUSH=0` 关），要正式令牌。

清（``gc_plan``／``gc_apply``，``guji cache gc-patches``）：每页留最新那天的包，另留 ``keep_days`` 天内的；其余可删。
缺省只列清单，``--apply`` 才删。
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tarfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

PREFIX = "derived/patch"
KIND = "char_patch"
PRODUCER = "cell_shrink"
KEY_RE = re.compile(r"^derived/patch/(?P<ws>[^/]+)/(?P<book>[^/]+)/(?P<page>p\d{4,})\.(?P<fp>[0-9a-f]{16})\.(?P<day>\d{8})\.tar$")
_NAME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.~+-]*\.png$")


def _pk(page: int) -> str:
    from .._cv import page_key
    return page_key(page)


def object_key(ws: str, book: str, page: int, fp: str, day: str | None = None) -> str:
    day = day or time.strftime("%Y%m%d", time.gmtime())
    return f"{PREFIX}/{ws}/{book}/{_pk(page)}.{fp}.{day}.tar"


@dataclass
class Obj:
    key: str
    ws: str
    book: str
    page: str
    fp: str
    day: str
    bytes: int = 0


def parse_key(key: str, size: int = 0) -> Obj | None:
    m = KEY_RE.match(key)
    return Obj(key, m["ws"], m["book"], m["page"], m["fp"], m["day"], int(size or 0)) if m else None


def _page_files(cache, book: str, page: int) -> list:
    """缓存里这一页的字块图（含换过备选切法的列的键）。页号后紧跟非数字，免得 p0024 吃进 p00241。"""
    pk = _pk(page)
    d = cache.root / book / KIND
    if not d.is_dir():
        return []
    out = []
    for q in d.glob(f"{pk}*.png"):
        rest = q.name[len(pk):]
        if q.is_file() and not q.name.startswith(".") and rest and not rest[0].isdigit():
            out.append(q)
    return sorted(out)


def build_tar(cache, book: str, page: int, fp: str, stamp: str) -> bytes | None:
    files = _page_files(cache, book, page)
    if not files:
        return None
    blobs = {f.name: f.read_bytes() for f in files}
    man = {"v": 1, "book": book, "page": _pk(page), "fp": fp, "stamp": stamp,
           "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "files": {n: hashlib.sha256(b).hexdigest() for n, b in blobs.items()}}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        def add(name: str, data: bytes) -> None:
            ti = tarfile.TarInfo(name)
            ti.size, ti.mtime, ti.mode = len(data), 0, 0o644
            tf.addfile(ti, io.BytesIO(data))
        add("manifest.json", json.dumps(man, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        for n in sorted(blobs):
            add(n, blobs[n])
    return buf.getvalue()


def unpack(data: bytes, cache, book: str, page: int, fp: str, stamp: str | None) -> int:
    """核对后把包里的字块写进缓存，返回张数。册、页、链指纹、戳、任一文件 sha 对不上就抛，一张都不写。"""
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tf:
        got: dict[str, bytes] = {}
        man = None
        for m in tf.getmembers():
            if not m.isfile():
                raise ValueError(f"包里有非文件项：{m.name}")
            b = tf.extractfile(m).read()
            if m.name == "manifest.json":
                man = json.loads(b)
            elif _NAME_OK.match(m.name):
                got[m.name] = b
            else:
                raise ValueError(f"包里有不合规的名字：{m.name}")
    if not man:
        raise ValueError("包里没有 manifest.json")
    if man.get("book") != book or man.get("page") != _pk(page) or man.get("fp") != fp:
        raise ValueError(f"包对不上：{man.get('book')}/{man.get('page')}/{man.get('fp')}")
    if stamp and man.get("stamp") != stamp:
        raise ValueError(f"包的戳 {man.get('stamp')} 与 cell_shrink 该页产物 {stamp} 对不上")
    want = man.get("files") or {}
    if set(want) != set(got):
        raise ValueError("包里的文件与清单对不上")
    for n, b in got.items():
        if hashlib.sha256(b).hexdigest() != want[n]:
            raise ValueError(f"{n} sha256 对不上")
    for n in sorted(got):
        _put(cache, book, n[:-len(".png")], got[n], stamp)
    return len(got)


def _put(cache, book: str, key: str, data: bytes, stamp: str | None) -> None:
    """cv 的 `ImageCache.put_bytes`（cv #1899 起）；旧 cv 没有就照它的写法落盘（临时文件＋换上、记页戳）。"""
    if hasattr(cache, "put_bytes"):
        cache.put_bytes(book, KIND, key, data, stamp=stamp)
        return
    path = cache.path(book, KIND, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.stem}.tmp{os.getpid()}{path.suffix}")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    cache.set_page_stamp(book, KIND, key, stamp)


# ── 取 ────────────────────────────────────────────────────────────────

def _read_token() -> str | None:
    return os.environ.get("GUJI_DATA_TOKEN_READ") or os.environ.get("GUJI_DATA_TOKEN")


def _src(write: bool = False):
    from .._cv import WorkerSource
    if write:
        tok = os.environ.get("GUJI_DATA_TOKEN_PROD") or os.environ.get("GUJI_DATA_TOKEN")
    else:
        tok = _read_token()
    if not tok:
        return None
    return WorkerSource(token=tok, branch="main")


def list_objects(src, ws: str | None = None, book: str | None = None) -> list[Obj]:
    pre = f"{PREFIX}/" + (f"{ws}/" if ws else "") + (f"{book}/" if ws and book else "")
    rows = src._call("GET", "/v1/packs", query={"bucket": "main", "prefix": pre})["packs"]
    return [o for o in (parse_key(r["key"], r.get("bytes", 0)) for r in rows) if o is not None]


_LOCK = threading.Lock()
_INDEX: dict[tuple[str, str], dict[tuple[str, str], str]] = {}
_SRC = {}
STATS = {"fetched": 0, "missed": 0, "failed": 0, "files": 0, "bytes": 0}


def _index(src, ws: str, book: str) -> dict[tuple[str, str], str]:
    with _LOCK:
        hit = _INDEX.get((ws, book))
        if hit is None:
            hit = {}
            for o in list_objects(src, ws, book):
                prev = hit.get((o.page, o.fp))
                if prev is None or prev < o.key:          # 同指纹重传过：取最新那天的
                    hit[(o.page, o.fp)] = o.key
            _INDEX[(ws, book)] = hit
        return hit


def fetcher(book: str, kind_id: str, page: int, fp: str, cache, stamp: str | None) -> bool:
    """cv `core.derived.PAGE_FETCHER`：取到并写进缓存返回 True；没有这份、没令牌返回 False；出错抛（cv 记一行、现算）。"""
    if kind_id != KIND:
        return False
    src = _SRC.get("r")
    if src is None:
        src = _src(write=False)
        if src is None:
            return False
        _SRC["r"] = src
    ws = _SRC.get("ws")
    if ws is None:
        from .packs import _ws_name
        try:
            ws = _SRC["ws"] = _ws_name()
        except SystemExit:                         # 没设工作区：不取（不能让 SystemExit 穿过 cv 的兜底）
            return False
    key = _index(src, ws, book).get((_pk(page), fp))
    if not key:
        STATS["missed"] += 1
        return False
    try:
        data = src._call("GET", "/v1/packs/" + key, query={"bucket": "main"}, raw=True)
        n = unpack(data, cache, book, page, fp, stamp)
    except Exception:
        STATS["failed"] += 1
        raise
    STATS["fetched"] += 1
    STATS["files"] += n
    STATS["bytes"] += len(data)
    return True


def install() -> bool:
    """把取件器注册给 cv（cv 没有 PAGE_FETCHER 的旧版不注册）。"""
    from .._cv import core_derived as derived
    if not hasattr(derived, "PAGE_FETCHER"):
        return False
    derived.PAGE_FETCHER = fetcher
    return True


# ── 存 ────────────────────────────────────────────────────────────────

def push_book(ctx, pages, src=None, log=print, dry_run: bool = False) -> dict:
    """`ctx`：带管线的 cv RunContext。存这册给定页里 R2 还没有的字块包，返回计数。"""
    if not hasattr(ctx, "chain_fingerprint"):
        raise SystemExit("cv 太旧：没有 RunContext.chain_fingerprint（要 cv #1899 之后的版本）")
    from .packs import _ws_name
    src = src or _src(write=True)
    if src is None:
        raise SystemExit("存字块包要令牌 GUJI_DATA_TOKEN_PROD（或 GUJI_DATA_TOKEN）")
    ws, book = _ws_name(), ctx.book.id
    have = {(o.page, o.fp) for o in list_objects(src, ws, book)}
    man = ctx.store.manifest(book, PRODUCER)
    res = {"pages": 0, "pushed": 0, "already": 0, "no_product": 0, "stale_cache": 0, "no_files": 0, "bytes": 0}
    for page in pages:
        res["pages"] += 1
        pk = _pk(page)
        ent = man.get(pk)
        if ent is None or ent.status != "ok" or not ent.sha256:
            res["no_product"] += 1
            continue
        if ctx.cache.page_stamp(book, KIND, pk) != ent.sha256:
            res["stale_cache"] += 1                        # 缓存不是对着现行产物切的（或没戳），不存
            continue
        fp = ctx.chain_fingerprint(PRODUCER, page)
        if not fp:
            res["no_product"] += 1
            continue
        if (pk, fp) in have:
            res["already"] += 1
            continue
        data = build_tar(ctx.cache, book, page, fp, ent.sha256)
        if data is None:
            res["no_files"] += 1
            continue
        if not dry_run:
            src._call("PUT", "/v1/packs/" + object_key(ws, book, page, fp), query={"bucket": "main"},
                      data=data, content_type="application/octet-stream", tries=3)
        have.add((pk, fp))
        res["pushed"] += 1
        res["bytes"] += len(data)
    return res


# ── 清 ────────────────────────────────────────────────────────────────

def gc_plan(objs: list[Obj], keep_days: int = 7, now: datetime | None = None) -> list[Obj]:
    """每页（ws, 册, 页）留最新那天的包（同一天多个链指纹都留），另留 `keep_days` 天内的；返回可删的。"""
    now = now or datetime.now(timezone.utc)
    cut = (now - timedelta(days=keep_days)).strftime("%Y%m%d")
    newest: dict[tuple, str] = {}
    for o in objs:
        k = (o.ws, o.book, o.page)
        if o.day > newest.get(k, ""):
            newest[k] = o.day
    return sorted((o for o in objs if o.day != newest[(o.ws, o.book, o.page)] and o.day < cut),
                  key=lambda o: o.key)


def gc_apply(src, drop: list[Obj], workers: int = 8) -> int:
    from concurrent.futures import ThreadPoolExecutor

    def one(o: Obj) -> None:
        src._call("DELETE", "/v1/packs/" + o.key, query={"bucket": "main"})
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, drop))
    return len(drop)
