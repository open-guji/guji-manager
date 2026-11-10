"""单页扫描的版框：**按册两遍**——先逐页量框线，再给全册定一个统一框尺寸，逐页用这个尺寸去对准框线。

为什么不逐页各找各的（`pagemeta.detect_content`，旧法）：全唐文扫描的版框线常微斜，一条线摊在十几行像素上，
「整行连续暗像素」过不了阈值，11,238 页里 775 页找不到框退回整幅，找到的框宽也忽大忽小（只有 57% 在中位 ±3% 内）。
新法：线段按连通块取（不怕斜），框尺寸全册统一（同一副版片印的，版框本来一样大），只用框线定位置；
全唐文 0 页退整幅、宽高 99.8% 在中位 ±3% 内。看图与数字：ai-team `domain/CV/图源迁移/页面范围pagemeta/全唐文版框重做/`。

坐标：检测在缩到 `W` 宽的图上做，结果按比例放回原图。需要 opencv（`pip install opencv-python-headless`）。
"""
from __future__ import annotations

import statistics as st
from dataclasses import dataclass, field

import numpy as np

W = 1000                 # 检测宽
DARK = 150               # 框线二值化
INK = 120                # 牌记撑高判墨
H_KERNEL, V_KERNEL = 40, 60
H_MIN, V_MIN = 0.30, 0.40          # 横线 ≥ 宽 30%，竖线 ≥ 高 40%
LINE_THICK = 0.035                 # 线段粗不过高（宽）的 3.5%：再粗是墨团（扫描黑角、黑块），不是框线
PAIR_TOL = 0.035                   # 一对线与统一尺寸的相对误差
SIZE_KEEP = 0.05                   # 定全册尺寸时只用实测在中位 ±5% 内的页
MARGIN = 0.015                     # 与 pagemeta.MARGIN 同


@dataclass
class Lines:
    w: int
    h: int
    H: list = field(default_factory=list)       # [x0,x1,y0,y1]，按 y0 排
    V: list = field(default_factory=list)       # [x0,x1,y0,y1]，按 x0 排
    ink: np.ndarray | None = None               # packbits 的墨迹（牌记撑高用）
    scale: float = 1.0                          # 原图 / 检测图
    flat: bool = False                          # 整幅一色（缺页灰图）


def measure(gray: np.ndarray) -> Lines:
    """一页灰度 → 框线段。"""
    import cv2
    h0, w0 = gray.shape[:2]
    g = cv2.resize(gray, (W, max(1, round(h0 * W / w0))), interpolation=cv2.INTER_AREA) if w0 != W else gray
    h, w = g.shape[:2]
    b = (g < DARK).astype(np.uint8)
    out = Lines(w=w, h=h, scale=w0 / w, flat=bool(g.std() < 4))
    hk = cv2.morphologyEx(b, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (H_KERNEL, 1)))
    hk = cv2.dilate(hk, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 3)))
    n, _, s, _ = cv2.connectedComponentsWithStats(hk, 8)
    out.H = sorted(([int(s[i, 0]), int(s[i, 0] + s[i, 2]), int(s[i, 1]), int(s[i, 1] + s[i, 3])]
                    for i in range(1, n) if s[i, 2] >= H_MIN * w and s[i, 3] <= LINE_THICK * h), key=lambda l: l[2])
    vk = cv2.morphologyEx(b, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, V_KERNEL)))
    vk = cv2.dilate(vk, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 9)))
    n, _, s, _ = cv2.connectedComponentsWithStats(vk, 8)
    out.V = sorted(([int(s[i, 0]), int(s[i, 0] + s[i, 2]), int(s[i, 1]), int(s[i, 1] + s[i, 3])]
                    for i in range(1, n) if s[i, 3] >= V_MIN * h and s[i, 2] <= LINE_THICK * w), key=lambda l: l[0])
    out.ink = np.packbits(g < INK, axis=1)
    return out


def _raw(L: Lines):
    if len(L.H) < 2 or blank(L):
        return None
    top, bot = L.H[0], L.H[-1]
    return bot[3] - top[2], max(top[1], bot[1]) - min(top[0], bot[0])


def blank(L: Lines) -> bool:
    """整幅一色的占位页（缺页灰图）。"""
    return L.flat


def vol_size(lines: list[Lines]) -> tuple[float, float] | None:
    """全册统一框尺寸 (高, 宽)（检测图坐标）：上下两线距、左右端宽的中位，去掉离中位 >5% 的页再取一次中位。"""
    raws = [r for r in (_raw(L) for L in lines) if r]
    if not raws:
        return None
    h0, w0 = st.median(r[0] for r in raws), st.median(r[1] for r in raws)
    keep = [r for r in raws if abs(r[0] - h0) < SIZE_KEEP * h0 and abs(r[1] - w0) < SIZE_KEEP * w0]
    if not keep:
        return h0, w0
    return st.median(r[0] for r in keep), st.median(r[1] for r in keep)


def _pair(starts, ends, L):
    """一个「起沿」a 配一个「止沿」b（上框线的上沿配下框线的下沿；左端配右端），b−a 与 L 差在 `PAIR_TOL` 内的最外一对。"""
    best = None
    for a in set(starts):
        for b in set(ends):
            if b <= a:
                continue
            e = abs((b - a) - L) / L
            if e <= PAIR_TOL and (best is None or b - a > best[1] - best[0]):
                best = (a, b, e)                 # 容差内取最外的一对：框线常是外粗内细两道，外道才是版框
    return best


def place(L: Lines, H0: float, W0: float) -> tuple[list[float] | None, str]:
    """把 W0×H0 的框对到这页的框线上 → ([x,y,w,h] 检测图坐标, 定法)。无框线／占位页／框不像版框（书名签）
    → (None, 'none'/'blank'/'unsure')，content 取整幅。"""
    w, h, Hs, Vs = L.w, L.h, L.H, L.V
    if blank(L):
        return None, "blank"
    if not Hs and not Vs:
        return None, "none"
    s = 1.0
    longV = [l for l in Vs if l[3] - l[2] >= 0.6 * H0]
    pv = _pair([l[2] for l in Hs], [l[3] for l in Hs], H0)
    if pv:
        y0, vhow = (pv[0] + pv[1] - H0) / 2, "pair"
    else:
        mH = [l for l in Hs if l[1] - l[0] >= 0.3 * w]
        top = [l for l in mH if l[2] < 0.35 * h]
        bot = [l for l in mH if l[3] > 0.65 * h]
        if top and bot and 0.85 < (bot[-1][3] - top[0][2]) / H0 < 1.2:
            # 这页拍得大／小：按实测两条横线等比放大；横线宽也得跟着对得上，否则是书名签之类的小框，不认
            s, y0, vhow = (bot[-1][3] - top[0][2]) / H0, top[0][2], "scaled"
            ext = max(top[0][1], bot[-1][1]) - min(top[0][0], bot[-1][0])
            if abs(ext - W0 * s) > 0.08 * W0 * s:
                return None, "unsure"
        elif longV and abs((max(l[3] for l in longV) - min(l[2] for l in longV)) - H0) < 0.06 * H0:
            y0, vhow = min(l[2] for l in longV), "vline"
            near = [l for l in Hs if abs(l[2] - y0) < 0.04 * h]       # 竖线上端常短一点：附近有横线就贴到横线上
            if near:
                y0 = min(l[2] for l in near)
        elif Hs:
            l = max(Hs, key=lambda l: l[1] - l[0])
            if (l[2] + l[3]) / 2 > h / 2:
                y0, vhow = l[3] - H0, "bottom"          # 只剩一条横线：在下半就是下框
            else:
                y0, vhow = l[2], "top"
        else:
            return None, "unsure"               # 一条横线也没有（封面、只有竖线的页）：不猜
    H1, W1 = H0 * s, W0 * s
    ph = _pair([l[0] for l in Hs + longV], [l[1] for l in Hs + longV], W1)
    midH = [l for l in Hs if l[1] - l[0] >= 0.3 * w]
    lefts, rights = [l[0] for l in midH], [l[1] for l in midH]
    vxs = [(l[0] + l[1]) / 2 for l in longV]
    # 线会因褪淡变短、不会变长：取最外端；另有一条线端或长竖线与之相合才算可靠
    Lx = min(lefts) if lefts else None
    Rx = max(rights) if rights else None

    def ok(ends, e):
        return e is not None and (sum(abs(v - e) <= 0.015 * w for v in ends) >= 2 or any(abs(v - e) < 0.02 * w for v in vxs))
    lok, rok = ok(lefts, Lx), ok(rights, Rx)
    if ph:
        x0, hhow = (ph[0] + ph[1] - W1) / 2, "pair"
    elif lok and rok and abs((Rx - Lx) - W1) < 0.08 * W1:
        x0, hhow = (Lx + Rx - W1) / 2, "hline"
    elif rok and not lok:
        x0, hhow = Rx - W1, "right"           # 只有右端可靠（左边是版心一侧，线淡或被切）
    elif lok and not rok:
        x0, hhow = Lx, "left"
    elif lok and rok:
        if longV:
            v = max(longV, key=lambda l: (l[1] - l[0]) * (l[3] - l[2]))
            vx = (v[0] + v[1]) / 2
            x0 = Lx if abs(vx - Lx) < abs(vx - Rx) else Rx - W1
            hhow = "outer"
        else:
            x0, hhow = (Lx + Rx - W1) / 2, "hline~"
    elif longV:
        v = max(longV, key=lambda l: (l[1] - l[0]) * (l[3] - l[2]))
        x0 = v[0] if (v[0] + v[1]) / 2 < w / 2 else v[1] - W1
        hhow = "outer"
    elif Lx is not None:
        x0, hhow = (Lx + Rx - W1) / 2, "hline~"
    else:
        return None, "unsure"
    x0 = min(max(x0, 0.0), max(w - W1, 0.0))
    y0 = min(max(y0, 0.0), max(h - H1, 0.0))
    x1, y1 = x0 + W1, y0 + H1
    # 配上对的框线若比统一尺寸略大（版片各页本有 1–2% 出入），框撑到包住框线，不切线
    if pv:
        y0, y1 = min(y0, pv[0]), max(y1, pv[1])
    if ph:
        x0, x1 = min(x0, ph[0]), max(x1, ph[1])
    return [x0, y0, x1 - x0, y1 - y0], f"{vhow}/{hhow}"


def content(L: Lines, box: list[float]) -> list[float]:
    """框外扩 `MARGIN`×短边；框上下若有贴着框线伸出去的墨块（序页「聖祖」「御定」抬头），撑到包住它。检测图坐标。"""
    import cv2
    w, h = L.w, L.h
    x, y, bw, bh = box
    m = MARGIN * min(w, h)
    x0, y0, x1, y1 = max(0.0, x - m), max(0.0, y - m), min(float(w), x + bw + m), min(float(h), y + bh + m)
    if L.ink is None:
        return [x0, y0, x1 - x0, y1 - y0]
    ink = np.unpackbits(L.ink, axis=1)[:, :w]
    X0, X1 = int(x0), int(x1)
    t = int(y0)
    if t > 5:
        n, _, s, _ = cv2.connectedComponentsWithStats(np.ascontiguousarray(ink[:t, X0:X1]), 8)
        for i in range(1, n):
            if s[i, 1] + s[i, 3] >= t - 3 and s[i, 3] >= 20 and s[i, 4] >= 150 and s[i, 1] > 2:   # 连到图边的是扫描黑边，不算
                y0 = min(y0, float(s[i, 1]))
    b = int(np.ceil(y1))
    if h - b > 5:
        n, _, s, _ = cv2.connectedComponentsWithStats(np.ascontiguousarray(ink[b:, X0:X1]), 8)
        for i in range(1, n):
            if s[i, 1] <= 3 and s[i, 3] >= 20 and s[i, 4] >= 150 and b + s[i, 1] + s[i, 3] < h - 2:
                y1 = max(y1, float(b + s[i, 1] + s[i, 3]))
    return [x0, y0, x1 - x0, y1 - y0]


def fit_volume(lines: dict[str, Lines]) -> dict[str, tuple[list[int] | None, str]]:
    """全册：seq → (content [x,y,w,h] 原图坐标、向外取整；无框 None, 定法)。"""
    size = vol_size(list(lines.values()))
    out: dict[str, tuple[list[int] | None, str]] = {}
    for seq, L in lines.items():
        if size is None:
            out[seq] = (None, "none")
            continue
        box, how = place(L, *size)
        if box is None:
            out[seq] = (None, how)
            continue
        c = content(L, box)
        k = L.scale
        x0, y0 = int(np.floor(c[0] * k)), int(np.floor(c[1] * k))
        x1, y1 = int(np.ceil((c[0] + c[2]) * k)), int(np.ceil((c[1] + c[3]) * k))
        W0, H0 = round(L.w * k), round(L.h * k)
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W0, x1), min(H0, y1)
        out[seq] = ([x0, y0, x1 - x0, y1 - y0], how)
    return out
