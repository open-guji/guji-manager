"""国内书影（COS `srcbw`）：每张源图出一版 1-bit 无损 WebP，过闸才传，传完在页表旁边记账。

规格：ai-team `全书整理/二十四史/国内COS书影压缩规格与接入.md`（A20 方案，用户 11-18 定；宽度 11-26 定为书级配置）。
原先是网站仓 `ops/iiif/src_bw_tier.py`／`pages_bw_tier.py`／`wyg_src_tier.py --bw` 三支脚本，宽度写死 3840；
11-27 起（GM2，WYG 请求）进本包，成为新书启动 1a 的一小步 `guji start source cos-tier`，出口由 `cos-check` 与
close-check 第 15 项核。

- **一张源图一个对象**：合扫页（同一张源图的几个半叶）共用；单页扫描（源图＝页图，H 单位阵）每页一个。
  路径 `iiif/<书>/<册>/srcbw/<slug>/full/<宽>,/0/default.webp`，slug 与网站仓 `pagemeta.src_slug`／`page_slug` 逐字相同。
- **宽度**（`src_w`）：`--width` ＞ 书配置 `src_w`（工作区 `config/book_defaults.yaml`，cv 不认这个键、不进指纹）
  ＞ 缺省：文淵閣四庫全書的源件 1600，其他 3840。源图更窄不放大。
- **压法**：灰度后缩（LANCZOS），黑白源图按 160 二值（偏深，细笔画不丢），彩色／灰度源图按 Otsu；WebP 无损 method 4。
- **闸**（`gate`）：RIFF／WEBP／`VP8L`（无损）、像素只有 0/255、宽 ≤ 本册宽度；不合格不传。
- **账**（`r<NNN>.cos.v<K>.json`，只增不改，K 大的新）：实际宽度、每个对象的 key／宽高／字节／md5、
  每页现成的 `bim:cos`（`key`、`width`、`height`、`matrix`＝COS 整页图像素 → 页图像素）。网站出 manifest 照抄，
  `url` 由网站按自己的数据域名拼。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

SCHEMA = "guji-cos/1"
FORMAT = "webp-lossless"
KIND = "bilevel"
DEFAULT_W = 3840                  # 与 Commons 缩略图同宽（殿本、全唐文等已传的都是这档）
WYG_W = 1600                      # 文淵閣整套（用户 11-26 定：实测均 55 KB／页，小注仍清楚）
WYG_MARK = "文淵閣四庫全書"         # 源件 Commons 标题里有这几个字就按文淵閣
BW_THRESHOLD = 160                # 黑白源图缩小后的二值阈（同网站仓 wyg_src_tier）
METHOD = 4                        # method 6 体积一样、慢 25 倍
IOU_MIN = 0.9
PUBLIC_BASE = os.environ.get("GUJI_COS_PUBLIC_BASE", "https://data.openguji.com")
IMAGE_CACHE = "public, max-age=2592000"
_LEDGER_RE = re.compile(r"r(\d{3,})\.cos\.v(\d+)\.json$")
_LEAF_RE = re.compile(r"_(\d+)\.\w+$")


class GateError(ValueError):
    """不合规格的对象：不传、不记账。"""


# ─── 路径与命名（与网站仓 ops/iiif/pagemeta.py 逐字相同）──────────────────────

def src_slug(src_id: str) -> str:
    """源图 id → 路径段：`WYG-SKQS-0001.djvu#235` → `WYG-SKQS-0001-235`，`s1:0243_0006.tif` → `s1-0243-0006-tif`。"""
    stem, _, page = src_id.partition("#")
    stem = re.sub(r"\.djvu$", "", stem, flags=re.IGNORECASE)
    return re.sub(r"[^A-Za-z0-9]+", "-", stem + ("-" + page if page else "")).strip("-")


def page_slug(seq: str) -> str:
    return f"p{seq}"


def cos_key(book_id: str, vol: str, slug: str, width: int) -> str:
    return f"iiif/{book_id}/{vol}/srcbw/{slug}/full/{width},/0/default.webp"


def ledger_prefix(book_id: str, vol: str) -> str:
    from .sources import table_prefix
    return table_prefix(book_id, vol)


def ledger_key(book_id: str, vol: str, rev: int, v: int) -> str:
    return f"{ledger_prefix(book_id, vol)}r{rev:03d}.cos.v{v}.json"


# ─── 宽度 ───────────────────────────────────────────────────────────────

def is_wyg(table: dict) -> bool:
    return any(WYG_MARK in (s.get("commons_title") or s.get("name") or "") for s in table.get("sources", []))


def resolve_width(table: dict, given: int | None = None, book_cfg: dict | None = None) -> tuple[int, str]:
    """(宽度, 来源)。来源：`--width`／`书配置 src_w`／`缺省（文淵閣）`／`缺省`。"""
    if given:
        return int(given), "--width"
    w = (book_cfg or {}).get("src_w")
    if w:
        return int(w), "书配置 src_w"
    if is_wyg(table):
        return WYG_W, "缺省（文淵閣）"
    return DEFAULT_W, "缺省"


# ─── 几何 ───────────────────────────────────────────────────────────────

def _identity(H) -> bool:
    flat = [float(v) for r in H for v in r]
    return all(abs(a - b) < 1e-9 for a, b in zip(flat, [1, 0, 0, 0, 1, 0, 0, 0, 1]))


def scaled_size(sw: int, sh: int, width: int) -> tuple[float, int, int]:
    """源图 → (缩放 s, COS 图宽, 高)；源图比 width 窄不放大。与网站仓 `pagemeta.cos_size` 同。"""
    s = min(1.0, width / sw)
    return s, round(sw * s), round(sh * s)


def _inv3(M):
    (a, b, c), (d, e, f), (g, h, i) = M
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        raise ValueError("矩阵不可逆")
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]


def cos_matrix(H, s: float) -> list[float]:
    """`bim:cos.matrix`：COS 整页图像素 → 页图像素 ＝ inv(S·H)，按 [2][2] 归一（与网站仓 `pagemeta.cos_matrix` 同）。
    `H` 是旁车的页图 → 源图。"""
    SH = [[s * float(v) for v in H[0]], [s * float(v) for v in H[1]], [float(v) for v in H[2]]]
    inv = _inv3(SH)
    z = inv[2][2]
    if abs(z) < 1e-12:
        raise ValueError("矩阵无法归一")
    return [float(f"{v / z:.10g}") for r in inv for v in r]


# ─── 计划：要出哪些对象、每页的 bim:cos ─────────────────────────────────────

def plan(table: dict, meta: dict, width: int) -> tuple[dict[str, dict], dict[str, dict]]:
    """页表＋旁车 → (objects {slug: {src_id, kind, w, h, src_w, src_h}}, pages {seq: bim:cos 记录})。

    `kind`：`page`（单页扫描，取页图）或 `src`（合扫页，取源件里的那一页）。旁车缺页直接报错。"""
    rows = {p["seq"]: p for p in table["pages"]}
    missing = [s for s in rows if s not in meta["pages"]]
    if missing:
        raise ValueError(f"旁车缺 {len(missing)} 页：{missing[:5]}")
    objects: dict[str, dict] = {}
    pages: dict[str, dict] = {}
    for seq, row in rows.items():
        e = meta["pages"][seq]
        H = e["H"]
        if _identity(H):
            slug, kind = page_slug(seq), "page"
            sw, sh = int(row["w"]), int(row["h"])
        else:
            slug, kind = src_slug(e["src"]["id"]), "src"
            sw, sh = int(e["src"]["w"]), int(e["src"]["h"])
        s, cw, ch = scaled_size(sw, sh, width)
        key = cos_key(table["book_id"], table["vol"], slug, width)
        o = objects.setdefault(slug, {"key": key, "src_id": e["src"]["id"], "kind": kind, "src_w": sw, "src_h": sh,
                                      "w": cw, "h": ch, "seqs": []})
        if (o["src_w"], o["src_h"]) != (sw, sh):
            raise ValueError(f"{slug}：同一张源图两页记的宽高不同（{o['src_w']}×{o['src_h']} ≠ {sw}×{sh}）")
        o["seqs"].append(seq)
        if kind == "page":
            o["sha256"] = row["sha256"]
        pages[seq] = {"slug": slug, "key": key, "width": cw, "height": ch, "matrix": cos_matrix(H, s),
                      "kind": KIND, "format": FORMAT}
    return objects, pages


# ─── 压图 ───────────────────────────────────────────────────────────────

def _otsu(gray) -> int:
    hist = gray.histogram()[:256]
    total = sum(hist)
    sum_all = sum(i * h for i, h in enumerate(hist))
    wb = sb = 0
    best, thr = -1.0, 128
    for t in range(256):
        wb += hist[t]
        if not wb:
            continue
        wf = total - wb
        if not wf:
            break
        sb += t * hist[t]
        mb, mf = sb / wb, (sum_all - sb) / wf
        var = wb * wf * (mb - mf) ** 2
        if var > best:
            best, thr = var, t
    return thr + 1


def to_bw(im, width: int):
    """源图 → 只有 0／255 的 L 图（≤ width 宽）。黑白源图（DjVu JB2、cv 页图）缩小后按 160 二值；其他按 Otsu。"""
    from PIL import Image
    g = im.convert("L")
    colors = g.getcolors(256) or []
    bilevel = bool(colors) and all(v in (0, 255) for _, v in colors)
    thr = 128 if bilevel else _otsu(g)
    if g.width > width:
        g = g.resize((width, round(g.height * width / g.width)), Image.LANCZOS)
        if bilevel:
            thr = BW_THRESHOLD
    return g.point(lambda v: 0 if v < thr else 255)


def encode(im) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "WEBP", lossless=True, quality=100, method=METHOD)
    return buf.getvalue()


def gate(data: bytes, width: int, size: tuple[int, int] | None = None) -> tuple[int, int]:
    """闸：WebP 无损（RIFF／WEBP／VP8L）、像素只有 0/255、宽 ≤ width（给了 size 就要正好）。返回 (宽, 高)。"""
    from PIL import Image
    if len(data) < 16 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise GateError("不是 WebP")
    if data[12:16] != b"VP8L":
        raise GateError(f"不是无损 WebP（块 {data[12:16]!r}，要 VP8L）")
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        w, h = im.size
        colors = im.convert("L").getcolors(256) or []
    if w > width:
        raise GateError(f"宽 {w} 超过本册宽度 {width}")
    if size and (w, h) != tuple(size):
        raise GateError(f"尺寸 {w}×{h} ≠ 应有的 {size[0]}×{size[1]}")
    bad = sorted(v for _, v in colors if v not in (0, 255))
    if not colors or bad:
        raise GateError(f"不是黑白两色（多出灰阶 {bad[:5]}）")
    return w, h


# ─── 取源 ───────────────────────────────────────────────────────────────

def _leaf_of(name: str) -> int:
    m = _LEAF_RE.search(name)
    if not m:
        raise ValueError(f"认不出叶号：{name}")
    return int(m.group(1))


def src_ref(table: dict, src_id: str) -> tuple[dict, int | str]:
    """旁车 src.id → (源件记录, 页号或 zip 里的叶名)。

    - `<文件>#<页>`（文淵閣 wyg-frame）：源件按 `file` 找，页号即 DjVu 页；
    - `<键>:<叶名>`（拆页，`build_from_zip` 记的）：源件按 `key` 找；DjVu／PDF 取叶名末尾的页号，zip 直接取叶名。"""
    by_key = {s["key"]: s for s in table.get("sources", []) if s.get("key")}
    by_file = {s["file"]: s for s in table.get("sources", []) if s.get("file")}
    if "#" in src_id:
        f, _, pg = src_id.rpartition("#")
        if f not in by_file:
            raise ValueError(f"{src_id}：页表 sources 里没有 {f}")
        return by_file[f], int(pg)
    key, sep, name = src_id.partition(":")
    if not sep or key not in by_key:
        raise ValueError(f"{src_id}：页表 sources 里没有键 {key}")
    s = by_key[key]
    if s["file"].lower().endswith(".zip"):
        return s, name
    return s, _leaf_of(name)


def fetch_source(src, rec: dict, dest: Path) -> Path:
    """源件落到 dest（核 sha256）：先 R2 存档（`r2`），没有再从 `commons_url`／`url` 下。"""
    from .sources import _MainBucket
    from .sources import sha256 as _sha
    if dest.exists() and _sha(dest.read_bytes()) == rec["sha256"]:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    err = None
    if rec.get("r2") and src is not None:
        try:
            from . import packs as PK
            PK.fetch_file(rec["r2"], dest, src=_MainBucket(src))
        except Exception as e:  # noqa: BLE001 —— R2 取不到再试 Commons
            err = e
    if not dest.exists():
        url = rec.get("commons_url")
        if not url:
            raise FileNotFoundError(f"{rec['file']}：R2 取不到（{err}），也没有 commons_url")
        req = urllib.request.Request(url, headers={"User-Agent": "guji-manager-cos/1 (open-guji)"})
        tmp = dest.with_suffix(dest.suffix + ".part")
        with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as fh:
            shutil.copyfileobj(r, fh, 1 << 20)
        tmp.replace(dest)
    if _sha(dest.read_bytes()) != rec["sha256"]:
        dest.unlink()
        raise ValueError(f"{rec['file']}：sha256 与页表记的不符")
    return dest


def render_src(path: Path, ref, w: int, h: int, width: int):
    """源件里的一页 → 黑白 L 图。DjVu 用 ddjvu 解 1-bit 前景；PDF 用 pdfimages 抽内嵌图；zip 直接读叶。核源图宽高。"""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    suf = path.suffix.lower()
    with tempfile.TemporaryDirectory() as td:
        if suf in (".djvu", ".djv"):
            out = Path(td) / "p.pbm"
            subprocess.run(["ddjvu", "-format=pbm", "-mode=black", f"-page={ref}", str(path), str(out)], check=True)
            im = Image.open(out)
        elif suf == ".pdf":
            subprocess.run(["pdfimages", "-all", "-f", str(ref), "-l", str(ref), str(path), str(Path(td) / "img")],
                           check=True)
            files = sorted(Path(td).glob("img-*"), key=lambda p: p.stat().st_size)
            if not files:
                raise ValueError(f"{path.name} 第 {ref} 页没抽出图")
            im = Image.open(files[-1])
        elif suf == ".zip":
            import zipfile
            with zipfile.ZipFile(path) as z:
                im = Image.open(io.BytesIO(z.read(str(ref))))
        else:
            raise ValueError(f"不认识的源件格式：{path.name}")
        im.load()
    if im.size != (w, h):
        raise ValueError(f"{path.name} 第 {ref} 页 {im.size[0]}×{im.size[1]} ≠ 旁车记的 {w}×{h}")
    return to_bw(im, width)


# ─── COS ────────────────────────────────────────────────────────────────

def _cos_auth(secret_id: str, secret_key: str, method: str, path: str, host: str, ttl: int = 900) -> str:
    import hmac
    start = int(time.time()) - 60
    key_time = f"{start};{start + ttl + 60}"
    sign_key = hmac.new(secret_key.encode(), key_time.encode(), hashlib.sha1).hexdigest()
    hs = [("host", urllib.parse.quote(host, safe="-_.~"))]
    http_string = f"{method.lower()}\n{path}\n\n" + "&".join(f"{k}={v}" for k, v in hs) + "\n"
    sts = f"sha1\n{key_time}\n{hashlib.sha1(http_string.encode()).hexdigest()}\n"
    sig = hmac.new(sign_key.encode(), sts.encode(), hashlib.sha1).hexdigest()
    return (f"q-sign-algorithm=sha1&q-ak={secret_id}&q-sign-time={key_time}&q-key-time={key_time}"
            f"&q-header-list=host&q-url-param-list=&q-signature={sig}")


class Cos:
    """腾讯云 COS 最小客户端（签名同网站仓 `siku_zongmu_iiif.Cos`）。令牌 `COS_SECRET_ID`／`COS_SECRET_KEY`
    （没有就认 `SH_COS_SECRET_ID`／`SH_COS_SECRET_KEY`）、`COS_BUCKET`，`COS_REGION` 缺省 ap-shanghai。"""

    def __init__(self):
        env = os.environ
        self.sid = env.get("COS_SECRET_ID") or env.get("SH_COS_SECRET_ID")
        self.skey = env.get("COS_SECRET_KEY") or env.get("SH_COS_SECRET_KEY")
        self.bucket = env.get("COS_BUCKET")
        if not (self.sid and self.skey and self.bucket):
            raise SystemExit("✗ 传 COS 要 COS_SECRET_ID、COS_SECRET_KEY、COS_BUCKET（见 doc/00-总览/环境与令牌.md）")
        self.host = f"{self.bucket}.cos.{env.get('COS_REGION', 'ap-shanghai')}.myqcloud.com"

    def _req(self, method: str, key: str, data: bytes | None = None, headers: dict | None = None, tries: int = 5):
        path, last = "/" + key, None
        for i in range(tries):
            hd = {"Host": self.host, **(headers or {}),
                  "Authorization": _cos_auth(self.sid, self.skey, method, path, self.host)}
            req = urllib.request.Request(f"https://{self.host}{urllib.parse.quote(path, safe='/,')}", data=data,
                                         method=method, headers=hd)
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    r.read()
                    return r.headers
            except urllib.error.HTTPError as e:
                if method == "HEAD" and e.code == 404:
                    return None
                last = e
                if not (e.code >= 500 or e.code in (408, 429, 403)):
                    raise
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = e
            time.sleep(0.5 * 2 ** i)
        raise last

    def etag(self, key: str) -> str | None:
        h = self._req("HEAD", key, tries=3)
        return (h.get("ETag", "").strip('"').lower() or None) if h is not None else None

    def put(self, key: str, body: bytes) -> None:
        if not key.startswith("iiif/") or "/srcbw/" not in key:
            raise GateError(f"{key} 不在 srcbw 路径下，不传")
        self._req("PUT", key, data=body, headers={"Content-Type": "image/webp", "Cache-Control": IMAGE_CACHE,
                                                  "Content-Length": str(len(body))})


def public_get(key: str, timeout: float = 120, tries: int = 4) -> bytes | None:
    """公开地址取对象（`GUJI_COS_PUBLIC_BASE`，缺省网站数据域名）；404 返回 None，断流重试。"""
    import http.client
    req = urllib.request.Request(f"{PUBLIC_BASE}/{urllib.parse.quote(key, safe='/,')}",
                                 headers={"User-Agent": "guji-manager-cos/1 (open-guji)"})
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code < 500 and e.code not in (408, 429):
                raise
            last = e
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, ConnectionError) as e:
            last = e
        time.sleep(1.5 * 2 ** i)
    raise last


# ─── 账 ────────────────────────────────────────────────────────────────

def ledgers(src, book_id: str, vol: str) -> list[tuple[int, int, str]]:
    from .sources import _list
    out = []
    for k in _list(src, ledger_prefix(book_id, vol)):
        m = _LEDGER_RE.search(k)
        if m:
            out.append((int(m.group(1)), int(m.group(2)), k))
    return sorted(out)


def read_ledger(src, book_id: str, vol: str, rev: int) -> dict | None:
    from .sources import _get
    mine = [x for x in ledgers(src, book_id, vol) if x[0] == rev]
    if not mine:
        return None
    return json.loads(_get(src, mine[-1][2]))


def make_ledger(table: dict, meta: dict, width: int, width_from: str, objects: dict, pages: dict,
                *, by: str, why: str, how: str) -> dict:
    from .pagemeta import table_sha
    return {"schema": SCHEMA, "book_id": table["book_id"], "vol": table["vol"], "rev": int(table["rev"]),
            "table_sha256": table_sha(table), "pagemeta_v": meta.get("v"),
            "width": width, "width_from": width_from, "format": FORMAT, "kind": KIND,
            "encode": {"method": METHOD, "bw_threshold": BW_THRESHOLD, "binarize": "otsu"},
            "how": how, "by": by, "why": why,
            "created": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "objects": {s: {k: o[k] for k in ("key", "src_id", "w", "h", "bytes", "md5")} for s, o in sorted(objects.items())},
            "pages": pages}


def publish_ledger(src, led: dict) -> dict:
    from .sources import _put
    have = [x for x in ledgers(src, led["book_id"], led["vol"]) if x[0] == led["rev"]]
    led = {**led, "v": (have[-1][1] + 1) if have else 1}
    _put(src, ledger_key(led["book_id"], led["vol"], led["rev"], led["v"]),
         (json.dumps(led, ensure_ascii=False, indent=1) + "\n").encode())
    return led


# ─── 出图、上传 ──────────────────────────────────────────────────────────

def build(src, table: dict, meta: dict, width: int, *, cache: Path, page_png: Callable[[str], bytes],
          out: Path | None = None, upload: Cos | None = None, force: bool = False,
          log: Callable[[str], None] = print) -> dict[str, dict]:
    """逐个出对象、过闸；给了 `out` 落盘，给了 `upload` 就传（桶里 md5 相同跳过）。返回 objects（带 bytes、md5、状态）。"""
    from PIL import Image
    objects, _ = plan(table, meta, width)
    local: dict[str, Path] = {}
    n_up = n_skip = 0
    try:
        for i, (slug, o) in enumerate(sorted(objects.items()), 1):
            if o["kind"] == "page":
                with Image.open(io.BytesIO(page_png(o["sha256"]))) as im:
                    im.load()
                    if im.size != (o["src_w"], o["src_h"]):
                        raise ValueError(f"{slug}：页图 {im.size} ≠ 页表 {o['src_w']}×{o['src_h']}")
                    bw = to_bw(im, width)
            else:
                rec, ref = src_ref(table, o["src_id"])
                if rec["file"] not in local:
                    local[rec["file"]] = fetch_source(src, rec, cache / rec["file"])
                bw = render_src(local[rec["file"]], ref, o["src_w"], o["src_h"], width)
            data = encode(bw)
            gate(data, width, (o["w"], o["h"]))
            o["bytes"], o["md5"] = len(data), hashlib.md5(data).hexdigest()
            if out is not None:
                p = out / o["key"]
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            if upload is not None:
                if not force and upload.etag(o["key"]) == o["md5"]:
                    n_skip += 1
                else:
                    upload.put(o["key"], data)
                    n_up += 1
            if i % 50 == 0 or i == len(objects):
                log(f"  {i}/{len(objects)}" + (f"（传 {n_up}，同内容跳过 {n_skip}）" if upload else ""))
    finally:
        for p in local.values():          # 源件一册用完就删，磁盘只留一册
            p.unlink(missing_ok=True)
    return objects


def adopt(table: dict, meta: dict, width: int, *, get: Callable[[str], bytes | None] = public_get,
          log: Callable[[str], None] = print) -> tuple[dict[str, dict], list[str]]:
    """已经传过的册（网站仓脚本传的）补账：逐个从公开地址取回、过闸。返回 (objects, 问题)。"""
    objects, _ = plan(table, meta, width)
    bad: list[str] = []
    for i, (slug, o) in enumerate(sorted(objects.items()), 1):
        data = get(o["key"])
        if data is None:
            bad.append(f"{slug}：线上没有 {o['key']}")
            continue
        try:
            gate(data, width, (o["w"], o["h"]))
        except GateError as e:
            bad.append(f"{slug}：{e}")
            continue
        o["bytes"], o["md5"] = len(data), hashlib.md5(data).hexdigest()
        if i % 100 == 0 or i == len(objects):
            log(f"  {i}/{len(objects)}")
    return objects, bad


# ─── 核 ────────────────────────────────────────────────────────────────

def ink_iou(page_png: bytes, cos_webp: bytes, matrix: list[float], scale_w: int = 200) -> float:
    """COS 整页图按 matrix 摆到页图坐标，与页图比墨迹 IoU（都缩到 scale_w 宽再比）。

    比的是摆位，不是笔画粗细：缩到 200 宽，史記 1600 宽实测摆对 0.92–0.96，错 25 像素（约 1% 页宽）就跌到 0.25。"""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    import numpy as np
    with Image.open(io.BytesIO(page_png)) as p:
        P = p.convert("L")
    with Image.open(io.BytesIO(cos_webp)) as c:
        C = c.convert("L")
    M = [matrix[0:3], matrix[3:6], matrix[6:9]]
    inv = _inv3(M)                               # 页图 → COS 图（PIL 要输出 → 输入）
    z = inv[2][2]
    coeffs = [v / z for r in inv for v in r][:8]
    W = C.transform(P.size, Image.PERSPECTIVE, coeffs, Image.BILINEAR, fillcolor=255)
    k = scale_w / P.width
    size = (scale_w, max(1, round(P.height * k)))
    a = np.asarray(P.resize(size, Image.BOX)) < 200
    b = np.asarray(W.resize(size, Image.BOX)) < 200
    union = int((a | b).sum())
    return 1.0 if union == 0 else float((a & b).sum()) / union


def check(table: dict, meta: dict | None, led: dict | None, *, online: int = 0, iou: int = 0,
          page_png: Callable[[str], bytes] | None = None, get: Callable[[str], bytes | None] = public_get,
          seed: int = 0) -> list[str]:
    """出口核：账在、对页表这一版、对象数＝旁车里的源图数、每页有 bim:cos；`online` 抽几个对象线上取回核 md5 与闸；
    `iou` 抽几页核墨迹 IoU ≥ 0.9。返回问题列表（空＝过）。"""
    import random

    from .pagemeta import table_sha
    tag = f"{table['book_id']}/{table['vol']} r{int(table['rev']):03d}"
    if meta is None:
        return [f"{tag} 没有页面范围旁车（先 guji start source pagemeta）"]
    if led is None:
        return [f"{tag} 没有国内书影账（先 guji start source cos-tier {table['book_id']} {table['vol']} --upload）"]
    errs = []
    if led.get("table_sha256") != table_sha(table):
        errs.append(f"{tag} 账的 table_sha256 与页表对不上")
    width = int(led["width"])
    want, want_pages = plan(table, meta, width)
    have = led.get("objects") or {}
    miss = sorted(set(want) - set(have))
    extra = sorted(set(have) - set(want))
    if miss or extra:
        errs.append(f"{tag} 对象数 {len(have)} ≠ 旁车源图数 {len(want)}（缺 {miss[:3]}，多 {extra[:3]}）")
    for slug in set(want) & set(have):
        if have[slug].get("key") != want[slug]["key"] or not have[slug].get("md5"):
            errs.append(f"{tag} {slug} 账记的 key／md5 不对")
            break
    lp = led.get("pages") or {}
    nopage = [s for s in want_pages if s not in lp]
    if nopage:
        errs.append(f"{tag} {len(nopage)} 页没有 bim:cos：{nopage[:5]}")
    for s in want_pages:
        if s in lp and [round(v, 6) for v in lp[s]["matrix"]] != [round(v, 6) for v in want_pages[s]["matrix"]]:
            errs.append(f"{tag} {s} 的 matrix 与旁车算出的不同（旁车出了新版？重跑 cos-tier）")
            break
    rnd = random.Random(seed)
    ok_slugs = sorted(set(want) & set(have))
    for slug in rnd.sample(ok_slugs, min(online, len(ok_slugs))):
        data = get(have[slug]["key"])
        if data is None:
            errs.append(f"{tag} {slug} 线上取不到")
            continue
        if hashlib.md5(data).hexdigest() != have[slug]["md5"]:
            errs.append(f"{tag} {slug} 线上内容与账记的 md5 不同")
            continue
        try:
            gate(data, width, (want[slug]["w"], want[slug]["h"]))
        except GateError as e:
            errs.append(f"{tag} {slug} 线上对象不合规格：{e}")
    if iou and page_png is not None:
        rows = {p["seq"]: p for p in table["pages"]}
        seqs = sorted(s for s in lp if s in rows)
        for s in rnd.sample(seqs, min(iou, len(seqs))):
            data = get(lp[s]["key"])
            if data is None:
                errs.append(f"{tag} {s} 线上取不到，没法核 IoU")
                continue
            v = ink_iou(page_png(rows[s]["sha256"]), data, lp[s]["matrix"])
            if v < IOU_MIN:
                errs.append(f"{tag} {s} 墨迹 IoU {v:.3f} < {IOU_MIN}")
    return errs
