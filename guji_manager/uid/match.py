"""一页两份切分之间的 u 继承（纯函数，不碰文件、不碰 cv）。

规则（CV0 设计「字格永久编号 u」方案·拆并，guji-format spec 02 §4.10）按下面的顺序走，前一档配上的格后一档不再看：

0. **有字旧格不配给空格**（11-26）：旧格有字、新格是空格（``c == ""``，字块里没墨）的一对在第 1、2 档不配，拆时也不让空格沿用；
   空格只接空格或发新号。只影响以后的入账，已发出的 u 不改。
1. **框 IoU**：同页格框 IoU ≥ ``IOU_MIN``（0.5）一对一，按 IoU 从大到小贪心配（口径同 ``swap/booktext.cell_table``）。
2. **中心距**：剩下的细字（如「一」）框小、IoU 不够：中心距 < 0.6×较大边、且同字（两边都有字时；有一边没字则要同格号）的，
   按中心距从近到远配。比 ``swap/booktext.cell_table`` 严一点：两边有字时不认「同号异字」，补字后整列顺移会骗过它。
3. **拆**：一个旧格的框里落着两个以上新格（新格面积 ≥ ``CONTAIN`` 落在旧格里）——半格、夹注拆 a/b、一格重切成两格。
   读序在前的那格沿用旧 u，其余发新号、记 ``split_from``；例外：拆出的不是夹注半格、且几格里**恰有一格**与旧格同字，就由它沿用（漏切补字的
   典型：旧格「玄」其实压着「地玄」两字，重切成两格后「玄」该留原 u，「地」是新补的）。旧格已经和某新格 IoU ≥ ``IOU_SAME`` 配上的（框几乎没动，
   只是里面多切出一小块），那一对不动，多出来的格照样记 ``split_from``。
4. **并**：一个新格的框里落着两个以上旧格（旧格面积 ≥ ``CONTAIN`` 落在新格里）。留较小的 u，别的记 ``into``，不复用。
   新格已经和某旧格 IoU ≥ ``IOU_SAME`` 配上的，留那一格的 u。
5. **字序列兜底**：两边剩下的格按读序取字，``difflib`` 对齐，相同的字一对一配（□、〓、空字不参与）。两边都要有字。
6. 还剩的新格发新号（``new``）；还剩的旧格记消失（``gone``）。

输出的 ``lineage`` 只记 **不是一对一继承** 的事：``{u, new: true}``、``{u, split_from: U}``、``{u, into: U}``、``{u, gone: true}``。
"""
from __future__ import annotations

import difflib
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

IOU_MIN = 0.5        # 同 swap/booktext.IOU_MIN
IOU_SAME = 0.85      # 框几乎没动（同 cv feedback/bindings.IOU_SAME）
CONTAIN = 0.6        # 拆并：小格面积有这么多落在大格里才算「在里面」
NO_TEXT = frozenset({"", "□", "〓"})


@dataclass(frozen=True)
class Cell:
    """一格：完整格号、框（左上原点 ``[x0, y0, x1, y1]``，可无）、字（可无）。列表顺序＝读序。"""
    id: str
    box: tuple[float, float, float, float] | None = None
    c: str | None = None          # None＝不知道；""＝空格（切出了格、没有墨）


@dataclass
class PageMatch:
    map: dict[str, int]                         # 新格号 → u（按新格读序）
    lineage: list[dict] = field(default_factory=list)
    via: Counter = field(default_factory=Counter)   # 各档配上的格数：iou／center／split／merge／text／new／gone


def xywh_to_box(b) -> tuple[float, float, float, float] | None:
    if not b:
        return None
    x, y, w, h = b
    return (x, y, x + w, y + h)


def _area(a) -> float:
    return max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])


def _inter(a, b) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def iou(a, b) -> float:
    i = _inter(a, b)
    u = _area(a) + _area(b) - i
    return i / u if u > 0 else 0.0


def _inside(small, big) -> float:
    """small 有多大比例落在 big 里。"""
    s = _area(small)
    return _inter(small, big) / s if s > 0 else 0.0


def fresh(new: Sequence[Cell], next_u: Callable[[], int]) -> PageMatch:
    """一页头一次入账：按读序发新号。"""
    m = PageMatch(map={})
    for n in new:
        m.map[n.id] = next_u()
        m.lineage.append({"u": m.map[n.id], "new": True})
        m.via["new"] += 1
    return m


def match_page(prev: Sequence[Cell], prev_u: dict[str, int], new: Sequence[Cell],
               next_u: Callable[[], int]) -> PageMatch:
    """上一份切分 ``prev``（格号 → u 见 ``prev_u``）→ 这一份 ``new``。``next_u()`` 每调一次发一个新号。"""
    P = {p.id: p for p in prev}
    N = {n.id: n for n in new}
    order = {n.id: i for i, n in enumerate(new)}
    pair: dict[str, str] = {}           # new → prev（一对一继承）
    rev: dict[str, str] = {}            # prev → new
    via: dict[str, str] = {}
    pair_iou: dict[str, float] = {}

    def link(n: str, p: str, how: str, s: float = 0.0) -> None:
        pair[n], rev[p], via[n], pair_iou[n] = p, n, how, s

    def unlink(n: str) -> None:
        p = pair.pop(n)
        rev.pop(p, None)
        via.pop(n, None)
        pair_iou.pop(n, None)

    boxed_p = [p for p in prev if p.box]
    boxed_n = [n for n in new if n.box]
    # 有字旧格不配给空格（CV0 主线程 11-26，史記 18 p2：列首新切出空格，旧「唐」u33 按框配给了空格，挂在 u33 上的人裁跟到空格上）。
    # 「空格」＝新格 ``c == ""``：切出了格、字块里没有墨（cell_shrink 无这格或 cell_type empty，见 ``source.from_products``）。
    # ``c is None`` 是「不知道字」（识字不新鲜、待审没出字），照旧按框配——那些格有墨，是同一个字格。
    def text_to_blank(p: Cell, n: Cell) -> bool:
        return bool(p.c) and n.c == ""

    # 1. 框 IoU
    cand = sorted(((iou(p.box, n.box), p.id, n.id) for p in boxed_p for n in boxed_n
                   if _inter(p.box, n.box) > 0), reverse=True)
    for s, pid, nid in cand:
        if s < IOU_MIN:
            break
        if pid in rev or nid in pair or text_to_blank(P[pid], N[nid]):
            continue
        link(nid, pid, "iou", s)

    # 2. 中心距（细字）
    cand2 = []
    for p in boxed_p:
        if p.id in rev:
            continue
        for n in boxed_n:
            if n.id in pair or text_to_blank(p, n):
                continue
            if p.c and n.c:              # 两边都有字：要同字（同号不算——补字后整列顺移，同号的常常不是同一个字）
                if p.c != n.c:
                    continue
            elif p.id != n.id:           # 有一边没字：退回 booktext 的口径，要同号
                continue
            a, b = p.box, n.box
            d = (((a[0] + a[2]) - (b[0] + b[2])) ** 2 + ((a[1] + a[3]) - (b[1] + b[3])) ** 2) ** .5 / 2
            lim = 0.6 * max(a[2] - a[0], a[3] - a[1], b[2] - b[0], b[3] - b[1])
            if d < lim:
                cand2.append((d, p.id, n.id, iou(a, b)))
    for d, pid, nid, s in sorted(cand2):
        if pid in rev or nid in pair:
            continue
        link(nid, pid, "center", s)

    lineage: list[dict] = []
    split_kids: dict[str, str] = {}     # 新格 → 它是从哪个旧格拆出来的（发新号时记 split_from）
    merged: dict[str, str] = {}         # 旧格 → 并进了哪个新格

    # 3. 拆
    for p in boxed_p:
        kids = [n.id for n in boxed_n if _inside(n.box, p.box) >= CONTAIN
                and (n.id not in pair or pair[n.id] == p.id) and n.id not in split_kids]
        if len(kids) < 2:
            continue
        kids.sort(key=order.__getitem__)
        keep = rev.get(p.id)
        if keep is None or pair_iou.get(keep, 0.0) < IOU_SAME:
            if keep is not None:
                unlink(keep)
            halves = all(k[-1:].isalpha() for k in kids)     # 拆成夹注 a/b 半格：照规范，先读的一半沿用
            same = [] if halves else [k for k in kids if p.c and N[k].c == p.c and p.c not in NO_TEXT]
            inked = [k for k in kids if not text_to_blank(p, N[k])]    # 有字旧格拆开：沿用给有字的那半
            keep = same[0] if len(same) == 1 else (inked or kids)[0]
            link(keep, p.id, "split")
        for k in kids:
            if k != keep:
                split_kids[k] = p.id

    # 4. 并
    for n in boxed_n:
        if n.id in split_kids:
            continue
        parents = [p.id for p in boxed_p if _inside(p.box, n.box) >= CONTAIN
                   and (p.id not in rev or rev[p.id] == n.id) and p.id not in merged]
        if len(parents) < 2:
            continue
        cur = pair.get(n.id)
        if cur is not None and pair_iou.get(n.id, 0.0) >= IOU_SAME:
            keep = cur
        else:
            keep = min(parents, key=lambda x: prev_u[x])
            if cur is not None:
                unlink(n.id)
            link(n.id, keep, "merge")
        for x in parents:
            if x != keep:
                merged[x] = n.id

    # 5. 字序列兜底
    left_p = [p for p in prev if p.id not in rev and p.id not in merged and p.c not in NO_TEXT and p.c is not None]
    left_n = [n for n in new if n.id not in pair and n.id not in split_kids and n.c not in NO_TEXT and n.c is not None]
    if left_p and left_n:
        sm = difflib.SequenceMatcher(None, [p.c for p in left_p], [n.c for n in left_n], autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for k in range(i2 - i1):
                    link(left_n[j1 + k].id, left_p[i1 + k].id, "text")

    # 6. 发号、记谱系（按新格读序发新号）
    out: dict[str, int] = {}
    cnt: Counter = Counter()
    for n in new:
        if n.id in pair:
            out[n.id] = prev_u[pair[n.id]]
            cnt[via[n.id]] += 1
        else:
            out[n.id] = next_u()
            if n.id in split_kids:
                lineage.append({"u": out[n.id], "split_from": prev_u[split_kids[n.id]]})
                cnt["split"] += 1
            else:
                lineage.append({"u": out[n.id], "new": True})
                cnt["new"] += 1
    for p in prev:
        if p.id in rev:
            continue
        if p.id in merged:
            lineage.append({"u": prev_u[p.id], "into": out[merged[p.id]]})
            cnt["merge"] += 1
        else:
            lineage.append({"u": prev_u[p.id], "gone": True})
            cnt["gone"] += 1
    return PageMatch(map=out, lineage=lineage, via=cnt)
