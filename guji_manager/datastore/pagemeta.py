"""页面范围（`guji-pagemeta/1`）：每页在**源扫描图**里的位置（`src`＋`H`）与版框内容区（`content`）。

设计：ai-team `domain/网站与运维/规范/书影页面范围统一规范.md`（A41，用户 2026-11-08 定）。
落法与理由：ai-team `domain/CV/图源迁移/页面范围pagemeta/落地说明.md`（A20）。

**为什么是旁车文件而不是往页表里加字段**：页表只增不改，改一次出新 rev，而 rev 号钉在册 yaml 的 `source_rev` 上、
进人裁事件的锚闸（`RevGate`）、进产物指纹；`content` 又是检测算法的输出，会调、会人工覆盖。要是写进页表本体，
每改一次就得换 rev、换钉、重 rebase 全部事件。所以放在页表旁边，按页表那一版的 sha256 认亲，自己可以出新版本::

    pack/source/pages/<书id>/<册>/r<NNN>.json              页表（只增不改，不动）
    pack/source/pages/<书id>/<册>/r<NNN>.page.v<K>.json    这一版页表的页面范围，只增不改，K 越大越新

`read_table(..., with_page=True)` 把最新一版旁车并进 `pages[i]["extent"]`，形状就是规范里的
`{src:{id,w,h}, H:[[..]×3], content:[x,y,w,h]}`。注意不叫 `page`：页表每行已有 `page`（cv 页号，整数），撞名。管线不读旁车，不改 sha、不让产物过期。

三个坐标系（像素、原点左上）：S 源图、P 页图（字框坐标系，永远不变）、C 内容区（P 里的矩形）。
`H` 是 3×3 矩阵，**P→S**。三种来源：

- 单页扫描（全唐文、北行日錄、页图＝源图）：`H` 单位阵，`src` 取页图本身（`sha256:<页图 sha>`，宽高取页表）；
- `ops.crop`（拆页，a–d 共用一叶）：`H` 是平移 `(x, y)`，`src` 取页表 `src`（叶文件），宽高要调用方给；
- `wyg-frame`（文淵閣，DjVu 页摆正切半叶）：`H` ＝ A20 `commons_warp.page_matrix` 的逆，`src` 取 `<源件文件>#<DjVu页>`，
  左右半叶共用，宽高要调用方给（DjVu 页大小页表里没有）。

`content`：wyg-frame 与 crop 的页图本来就裁在版框上，由页表 `frame`/`pad` 直接算（版框矩形外扩 1.5% 短边）；
单页扫描用 `detect_content` 离线算（长横线定上下、竖线定左右，缩到 600 宽，无框线取整幅），可 `manual` 覆盖。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from typing import Callable, Iterable

import numpy as np

SCHEMA = "guji-pagemeta/1"
MARGIN = 0.015                  # 内容区在版框外再留的边，占页图短边
CORNER_TOL = 3.0                # H 把页图四角映到源图内的容差（像素）
DETECT_W = 600                  # 检测前缩到这个宽
LINE_RUN = 0.35                 # 长横线：连续暗像素 ≥ 宽的 35%
COL_FILL = 0.25                 # 竖线：上下两线之间列暗像素占比 ≥ 25%
EDGE_SKIP = 0.01                # 图缘 1% 不算
DARK = 128

_PM_RE = re.compile(r"r(\d{3,})\.page\.v(\d+)\.json")


# ─── R2 键 ───────────────────────────────────────────────────────────────

def pagemeta_prefix(book_id: str, vol: str) -> str:
    from .sources import table_prefix
    return table_prefix(book_id, vol)


def pagemeta_key(book_id: str, vol: str, rev: int, v: int) -> str:
    return f"{pagemeta_prefix(book_id, vol)}r{rev:03d}.page.v{v}.json"


def versions(src, book_id: str, vol: str, rev: int) -> list[int]:
    """这一版页表已有的旁车版本号。"""
    from .sources import _list
    out = []
    for k in _list(src, pagemeta_prefix(book_id, vol)):
        m = _PM_RE.fullmatch(k.rsplit("/", 1)[-1])
        if m and int(m.group(1)) == rev:
            out.append(int(m.group(2)))
    return sorted(out)


def read_pagemeta(src, book_id: str, vol: str, rev: int, v: int | None = None) -> dict | None:
    """取旁车（缺省最新版）；这一版页表还没有旁车就返回 None。"""
    from .sources import _get
    vs = versions(src, book_id, vol, rev)
    if not vs:
        return None
    v = vs[-1] if v is None else v
    return json.loads(_get(src, pagemeta_key(book_id, vol, rev, v)))


def table_sha(table: dict) -> str:
    """页表内容的指纹（页的 seq+sha256，按页序）。不用整份文件字节：同一版页表被重新读出来排版不同也不该变。"""
    h = hashlib.sha256()
    for p in table["pages"]:
        h.update(f"{p['seq']}:{p['sha256']}\n".encode())
    return h.hexdigest()


def publish_pagemeta(src, table: dict, pages: dict[str, dict], *, by: str, why: str, algo: dict | None = None) -> dict:
    """发一版旁车。`table` 是它描述的那版页表；发之前过 `validate_pagemeta`，不过不发。"""
    from .sources import _put
    meta = make_pagemeta(table, pages, by=by, why=why, algo=algo)
    errs = validate_pagemeta(table, meta)
    if errs:
        raise ValueError(f"页面范围没过校验（{len(errs)} 处），例：{errs[:3]}")
    vs = versions(src, table["book_id"], table["vol"], int(table["rev"]))
    meta["v"] = (vs[-1] if vs else 0) + 1
    meta["prev_v"] = vs[-1] if vs else None
    _put(src, pagemeta_key(table["book_id"], table["vol"], int(table["rev"]), meta["v"]),
         json.dumps(meta, ensure_ascii=False, indent=1).encode("utf-8"))
    return meta


def make_pagemeta(table: dict, pages: dict[str, dict], *, by: str, why: str, algo: dict | None = None) -> dict:
    return {"schema": SCHEMA, "book_id": table["book_id"], "vol": table["vol"], "rev": int(table["rev"]),
            "table_sha256": table_sha(table), "created": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "by": by, "why": why, "algo": algo or {}, "pages": pages}


def merge_into_table(table: dict, meta: dict | None) -> dict:
    """把旁车并进 `pages[i]["extent"]`（原地改并返回）。旁车和页表对不上（页表指纹不同）就报错，不静默并。"""
    if meta is None:
        return table
    if meta.get("table_sha256") != table_sha(table):
        raise ValueError(f"旁车 v{meta.get('v')} 不是这版页表的（table_sha256 对不上）")
    for p in table["pages"]:
        if p["seq"] in meta["pages"]:
            p["extent"] = {k: v for k, v in meta["pages"][p["seq"]].items() if k in ("src", "H", "content")}
    return table


# ─── 几何 ────────────────────────────────────────────────────────────────

def homography(src_pts, dst_pts) -> np.ndarray:
    """四点求 3×3 透视矩阵（src→dst），与 `cv2.getPerspectiveTransform` 同解（h33=1）。"""
    A, b = [], []
    for (x, y), (u, v) in zip(src_pts, dst_pts):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); b.append(v)
    h = np.linalg.solve(np.array(A, float), np.array(b, float))
    return np.append(h, 1.0).reshape(3, 3)


def apply_h(H, x: float, y: float) -> tuple[float, float]:
    v = np.asarray(H, float) @ np.array([x, y, 1.0])
    return float(v[0] / v[2]), float(v[1] / v[2])


def _quad(pts: dict, half: str) -> list[np.ndarray]:
    """各半叶四角（左上、右上、右下、左下）；中分：版心两线中线分（同 commons_warp.quad）。"""
    P = lambda k: np.array(pts[k], float)
    mt, mb = (P("t_xl") + P("t_xr")) / 2, (P("b_xl") + P("b_xr")) / 2
    return [mt, P("t_R"), P("b_R"), mb] if half == "右" else [P("t_L"), mt, mb, P("b_L")]


def wyg_geometry(row: dict) -> tuple[np.ndarray, tuple[int, int], list[float]]:
    """文淵閣一页：返回 (T 源图→页图, (W, H) 页图尺寸（按 frame 算）, 版框矩形 [x,y,w,h]（页图坐标）)。"""
    q = _quad(row["frame"]["pts"], row["half"])
    pad = row["frame"]["pad"]
    l, r = (pad["o"], 0) if row["half"] == "左" else (0, pad["o"])
    w0 = int(round(float(np.hypot(*(q[1] - q[0])))))
    h0 = int(round(float(np.hypot(*(q[3] - q[0])))))
    Hm = homography(q, [(0, 0), (w0, 0), (w0, h0), (0, h0)])
    T = np.array([[1, 0, l], [0, 1, pad["t"]], [0, 0, 1.0]]) @ Hm
    return T, (w0 + l + r, h0 + pad["t"] + pad["b"]), [float(l), float(pad["t"]), float(w0), float(h0)]


def pad_rect(rect: list[float], w: int, h: int, margin: float = MARGIN) -> list[int]:
    """版框矩形外扩 `margin`×短边，夹在页图内，取整（向外取整）。"""
    m = margin * min(w, h)
    x0, y0 = max(0.0, rect[0] - m), max(0.0, rect[1] - m)
    x1, y1 = min(float(w), rect[0] + rect[2] + m), min(float(h), rect[1] + rect[3] + m)
    x0, y0 = int(np.floor(x0)), int(np.floor(y0))
    x1, y1 = int(np.ceil(x1)), int(np.ceil(y1))
    return [x0, y0, x1 - x0, y1 - y0]


# ─── content 检测（单页扫描）──────────────────────────────────────────────

def _longest_run(mask_row: np.ndarray) -> int:
    best = cur = 0
    for v in mask_row:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def detect_content(gray: np.ndarray) -> list[int]:
    """灰度页图 → 版框内容区 `[x, y, w, h]`（页图坐标，已含 `MARGIN` 外扩）。

    缩到 600 宽；暗像素 < `DARK`。长横线（连续暗像素 ≥ 宽 35%）的第一条与最后一条定上下；其间各列暗像素占比 ≥ 25% 的
    第一列与最后一列定左右（稀疏页放宽到 12.5%、6%），再并上竖框线（连续暗 ≥ 带高一半）；图缘 1% 不算。
    找不到两条横线或两条竖线（无框线、残页）→ 取整幅。
    参考实现：book-index-manager `ui/src/components/Reader/frame-detect.ts`（0.66.3）。"""
    h0, w0 = gray.shape[:2]
    if w0 > DETECT_W:
        from PIL import Image
        im = Image.fromarray(gray).resize((DETECT_W, max(1, round(h0 * DETECT_W / w0))), Image.BILINEAR)
        g = np.asarray(im)
    else:
        g = gray
    h, w = g.shape[:2]
    full = [0, 0, w0, h0]
    dark = g < DARK
    ey, ex = int(h * EDGE_SKIP), int(w * EDGE_SKIP)
    need = LINE_RUN * w
    rows = [y for y in range(ey, h - ey) if _longest_run(dark[y, ex:w - ex]) >= need]
    if len(rows) < 2:
        return full
    top, bot = rows[0], rows[-1]
    if bot - top < 0.2 * h:
        return full
    band = dark[top:bot + 1, :]
    frac = band.mean(axis=0)
    left = right = None
    for fill in (COL_FILL, COL_FILL / 2, COL_FILL / 4):          # 稀疏小字的页，25% 够不着，逐级放宽
        cols = [x for x in range(ex, w - ex) if frac[x] >= fill]
        if len(cols) >= 2 and cols[-1] - cols[0] >= 0.2 * w:
            left, right = cols[0], cols[-1]
            break
    if left is None:
        return full
    # 框线本身（上下两线之间连续暗 ≥ 一半高）比文字更靠外：有就把范围拉到框线上（扫描里常只有一边的竖线清楚）
    need_v = 0.5 * (bot - top + 1)
    strong = [x for x in range(ex, w - ex) if _longest_run(band[:, x]) >= need_v]
    if strong:
        left, right = min(left, strong[0]), max(right, strong[-1])
    sx, sy = w0 / w, h0 / h
    rect = [left * sx, top * sy, (right - left + 1) * sx, (bot - top + 1) * sy]
    return pad_rect(rect, w0, h0)


# ─── 逐页生成 ────────────────────────────────────────────────────────────

SizeOf = Callable[[str], tuple[int, int] | None]


def build_page(row: dict, table: dict, *, src_size: SizeOf | None = None,
               gray_of: Callable[[dict], np.ndarray] | None = None) -> dict:
    """一页的旁车记录 `{src, H, content, how}`。

    - `src_size(src_id)`：crop、wyg-frame 的源图宽高（页表里没有）；
    - `gray_of(row)`：单页扫描要读页图灰度来检测 `content`（缺省不检测、`content` 取整幅，`how: whole`）。"""
    w, h = int(row["w"]), int(row["h"])
    ops = row.get("ops") or []
    crop = next((o["crop"] for o in ops if "crop" in o), None)
    if row.get("frame") and row.get("half"):
        key = {s["key"]: s for s in table.get("sources", [])}.get(row["src"], {})
        sid = f"{key.get('file', row['src'])}#{row['djvu_page']}"
        size = src_size(sid) if src_size else None
        if not size:
            raise ValueError(f"{row['seq']}：文淵閣源图宽高没给（{sid}）")
        T, (fw, fh), rect = wyg_geometry(row)
        if abs(fw - w) > 2 or abs(fh - h) > 2:
            raise ValueError(f"{row['seq']}：frame 算出的页图尺寸 {fw}×{fh} 与页表 {w}×{h} 差超过 2 像素")
        H = np.linalg.inv(T)
        # 版框贴着扫描边时，外扩的 pad 会越出源图几十像素（那几圈是补白），所以容差放宽到 2×pad（实测 99 册 1.6 万页只有 3 页越出，最多 35 像素）
        return {"src": {"id": sid, "w": int(size[0]), "h": int(size[1])}, "H": _round(H),
                "content": pad_rect(rect, w, h), "how": "wyg-frame", "tol": 2 * max(row["frame"]["pad"].values())}
    if crop:
        sid = row.get("src") or ""
        size = src_size(sid) if src_size else None
        if not size:
            raise ValueError(f"{row['seq']}：拆页源图宽高没给（{sid}）")
        x, y = crop[0], crop[1]
        return {"src": {"id": sid, "w": int(size[0]), "h": int(size[1])},
                "H": [[1, 0, x], [0, 1, y], [0, 0, 1]], "content": [0, 0, w, h], "how": "crop"}
    content, how = [0, 0, w, h], "whole"
    if gray_of is not None:
        content, how = detect_content(gray_of(row)), "detect"
    return {"src": {"id": f"sha256:{row['sha256']}", "w": w, "h": h}, "H": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "content": content, "how": how}


def _round(H: np.ndarray) -> list[list[float]]:
    return [[float(f"{v:.10g}") for v in r] for r in np.asarray(H, float)]


def build_pages(table: dict, **kw) -> dict[str, dict]:
    return {p["seq"]: build_page(p, table, **kw) for p in table["pages"]}


# ─── 校验 ────────────────────────────────────────────────────────────────

def validate_page(row: dict, meta: dict, *, boxes: Iterable[tuple[float, float, float, float]] | None = None) -> list[str]:
    """一页的不变量：H 把 P 四角映到 S 内（容差 `CORNER_TOL`，记录里有 `tol` 用它）；content 在页图内；content ⊇ 字框外接矩形（给了字框才查）。"""
    errs: list[str] = []
    seq = row["seq"]
    w, h = int(row["w"]), int(row["h"])
    s = meta.get("src") or {}
    H = meta.get("H")
    if not (isinstance(H, list) and len(H) == 3 and all(len(r) == 3 for r in H)):
        return [f"{seq}：H 不是 3×3"]
    sw, sh = s.get("w", 0), s.get("h", 0)
    tol = float(meta.get("tol", CORNER_TOL))
    if not (sw > 0 and sh > 0):
        errs.append(f"{seq}：src 宽高缺")
    else:
        for name, (x, y) in (("TL", (0, 0)), ("TR", (w, 0)), ("BR", (w, h)), ("BL", (0, h))):
            u, v = apply_h(H, x, y)
            if not (-tol <= u <= sw + tol and -tol <= v <= sh + tol):
                errs.append(f"{seq}：页图 {name} 角经 H 落到源图外（{u:.1f},{v:.1f} 不在 0..{sw}×0..{sh}）")
    c = meta.get("content")
    if not (isinstance(c, list) and len(c) == 4):
        errs.append(f"{seq}：content 不是 [x,y,w,h]")
    else:
        x, y, cw, ch = c
        if cw <= 0 or ch <= 0 or x < 0 or y < 0 or x + cw > w + 1e-6 or y + ch > h + 1e-6:
            errs.append(f"{seq}：content {c} 越出页图 {w}×{h}")
        elif boxes:
            bs = list(boxes)
            if bs:
                bx0, by0 = min(b[0] for b in bs), min(b[1] for b in bs)
                bx1, by1 = max(b[0] + b[2] for b in bs), max(b[1] + b[3] for b in bs)
                if bx0 < x - 1 or by0 < y - 1 or bx1 > x + cw + 1 or by1 > y + ch + 1:
                    errs.append(f"{seq}：content {c} 没罩住字框外接矩形 [{bx0:.0f},{by0:.0f},{bx1 - bx0:.0f},{by1 - by0:.0f}]")
    return errs


def validate_pagemeta(table: dict, meta: dict, *, boxes_of: Callable[[str], Iterable] | None = None) -> list[str]:
    """整册：schema、与页表对得上、每页都有且过 `validate_page`。返回问题清单，空＝通过。"""
    errs: list[str] = []
    if meta.get("schema") != SCHEMA:
        errs.append(f"schema 应为 {SCHEMA}")
    if (meta.get("book_id"), meta.get("vol"), meta.get("rev")) != (table["book_id"], table["vol"], int(table["rev"])):
        errs.append("书/册/rev 与页表不符")
    if meta.get("table_sha256") != table_sha(table):
        errs.append("table_sha256 与页表不符")
    pages = meta.get("pages") or {}
    for row in table["pages"]:
        m = pages.get(row["seq"])
        if m is None:
            errs.append(f"{row['seq']}：没有页面范围记录")
            continue
        errs += validate_page(row, m, boxes=boxes_of(row["seq"]) if boxes_of else None)
    extra = set(pages) - {r["seq"] for r in table["pages"]}
    if extra:
        errs.append(f"旁车里有页表没有的页：{sorted(extra)[:3]}")
    return errs


def ink_iou(page_gray: np.ndarray, src_gray: np.ndarray, H) -> float:
    """墨迹对齐：把页图按 H（P→S）取样到源图上，和源图墨迹的 IoU。只在页图覆盖到的区域里比，需要 cv2。"""
    import cv2
    h, w = page_gray.shape[:2]
    warped = cv2.warpPerspective(page_gray, np.linalg.inv(np.asarray(H, float)), (src_gray.shape[1], src_gray.shape[0]),
                                 flags=cv2.INTER_LINEAR, borderValue=255)
    cover = cv2.warpPerspective(np.full((h, w), 255, np.uint8), np.linalg.inv(np.asarray(H, float)),
                                (src_gray.shape[1], src_gray.shape[0]), flags=cv2.INTER_NEAREST, borderValue=0) > 0
    a, b = (warped < DARK) & cover, (src_gray < DARK) & cover
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 1.0
