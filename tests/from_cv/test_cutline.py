"""拖切线（cutline）事件 → touching-cuts 金标 的链路回归。

2026-09-05：粘连格线（R2s）的理想切点金标。事件 kind=cutline，路由到
char-segmentation/touching-cuts；expected 只留切点相关字段。
"""

from __future__ import annotations

from guji_manager.eval.touching import pick_cases
from open_guji_cv.feedback.consumers import _expected_of
from open_guji_cv.feedback.events import EventTarget, make_event
from open_guji_cv.feedback.routes import RouteTable


def _evt(payload: dict):
    return make_event("vol01-cutline", 1, "cutline",
                      EventTarget(step="row_segment", unit="boundary", key="vol01:44:2:17",
                                  book="vol01", page=44, col=2, slot=17),
                      payload)


def test_pick_cases_spreads_over_pages_and_is_deterministic():
    cases = [dict(id=f"vol01:{p}:1:{s}", page=p) for p in (44, 71, 72) for s in range(1, 41)]
    cases += [dict(id=f"vol01:15:1:{s}", page=15) for s in range(1, 3)]
    a = pick_cases(cases, 30)
    b = pick_cases(cases, 30)
    assert [c["id"] for c in a] == [c["id"] for c in b]
    by_page = {}
    for c in a:
        by_page[c["page"]] = by_page.get(c["page"], 0) + 1
    # 轮转：只有 2 条的页全进；三个大页各拿到接近 1/3，而不是一页包场
    assert by_page[15] == 2
    assert all(8 <= by_page[p] <= 10 for p in (44, 71, 72)), by_page


def test_polyline_to_seam_interpolates_and_extends_ends():
    from guji_manager.eval.touching import polyline_to_seam, seam_deviation
    seam = polyline_to_seam([[10, 100], [20, 110], [30, 100]], x0=5, x1=36)
    assert len(seam) == 31
    assert seam[0] == 100 and seam[-1] == 100          # 两端水平延伸
    assert seam[20 - 5] == 110                          # 顶点 x=20
    assert seam[15 - 5] == 105                          # x=15：10→20 的中点线性插值
    mx, mean = seam_deviation(seam, [100] * 31)
    assert mx == 10 and 0 < mean < 10


# ── 2026-09-08：「切进字里」候选的绝对墨量判据（47 条人裁金标标定）──
def test_split_char_ink_mass_separates_flat_chars_from_split_halves():
    """矮格里装的是扁字（一/二）还是被劈的半个字——只有绝对墨量分得开。

    金标实测：格高比例两组几乎完全重合（moved 0.70~0.79 / ok 0.66~0.80），
    而绝对墨量（墨像素 ÷ 中位格高×格宽）ok 0.034~0.066、moved 0.105~0.195。
    """
    import numpy as np

    from guji_manager.eval.touching import _cell_ink_mass

    class _Cell:
        def __init__(self, y0, y1, x0, x1):
            self.y0, self.y1, self.x0, self.x1 = y0, y1, x0, x1

    class _Cache:
        def __init__(self, img): self.img = img
        def get(self, *a, **k): return self.img

    med, w = 115.0, 150
    # 扁字「一」：矮格 85px，墨只有中间一条横（约 12px 高、满宽）
    flat = np.full((300, w), 255, np.uint8)
    flat[40:52, 20:130] = 0
    # 被劈的半个字：同样 85px 的格，墨铺满大半格
    half = np.full((300, w), 255, np.uint8)
    half[8:80, 20:130] = 0
    import cv2, tempfile, os
    out = []
    for img in (flat, half):
        fd, path = tempfile.mkstemp(suffix='.png'); os.close(fd)
        cv2.imwrite(path, img)
        import open_guji_cv.products.cache as _c
        orig = _c.ImageCache
        _c.ImageCache = lambda: _Cache(path)
        try:
            out.append(_cell_ink_mass(None, 'vol01', 1, 1, _Cell(0, 85, 10, 140), med))
        finally:
            _c.ImageCache = orig
            os.unlink(path)
    flat_mass, half_mass = out
    assert flat_mass < 0.100, f"扁字墨量 {flat_mass:.3f} 不该超阈值"
    assert half_mass >= 0.100, f"半个字墨量 {half_mass:.3f} 该超阈值"


def test_blocking_gate_reads_all_event_batches(monkeypatch, tmp_path):
    """裁过的切线要**立刻**退出顺序闸，不必等 harvest 收进金标。

    2026-09-12 回归：原先 `blocking_cutline_cases` 里写的是无参
    `event_log().read()`，而 `EventLog.read(batch)` 是必填参数——
    抛的 `TypeError` 被裸 `except Exception: pass` 吞掉，事件去重从未生效。
    这里断言的是**行为**（事件里的 id 不再出现在待裁集合里），不是调用形式，
    所以换实现也不会误报。
    """
    from guji_manager.eval import touching as T
    from guji_manager.review import cards as C

    case = {"id": "volX:7:3:5", "page": 7, "col": 3, "bi": 5,
            "slot_above": 5, "slot_below": 6}

    monkeypatch.setattr(T, "r2s_boundaries", lambda *a, **k: [dict(case)])
    monkeypatch.setattr(T, "split_char_boundaries", lambda *a, **k: [])
    monkeypatch.setattr(T, "gold_ids", lambda *a, **k: set())

    class _CP:
        slot_above, chosen = 5, 0
        candidates = [object(), object()]          # 多候选 → 该挡
    class _Col:
        col, cut_candidates = 3, [_CP()]
    class _Cells:
        columns = [_Col()]
    class _St:
        def read(self, *a, **k): return _Cells()

    class _Log:
        def __init__(self, keys): self.keys = keys
        def iter_all(self):
            for k in self.keys:
                yield type("E", (), {"kind": "cutline",
                                     "target": type("T", (), {"key": k})()})()
        def read(self, batch):                      # 有 batch 才给，模拟真实签名
            raise AssertionError("不该按单批次读——要跨所有批次去重")

    monkeypatch.setattr(C, "_event_log", lambda: _Log([]))
    assert len(C.blocking_cutline_cases("volX", [7], _St())) == 1, "没裁过时应当挡住"

    monkeypatch.setattr(C, "_event_log", lambda: _Log(["volX:7:3:5"]))
    assert C.blocking_cutline_cases("volX", [7], _St()) == [], "裁过之后应立刻放行"


# ── 人裁回流：Step3 从 workspace 裁决表取已裁决的切点 ─────────────────

def _verdict(page, col, slot, verdict, cand, status="active", book="vol02", **extra):
    from open_guji_cv.gold.item import Anchor, GoldItem
    exp = {"verdict": verdict, **extra}
    if cand is not None:
        exp["cand"] = cand
    return GoldItem(id=f"{book}:{page}:{col}:{slot}",
                    anchor=Anchor(book=book, page=page, col=col, slot=slot),
                    expected=exp, status=status)


def _patch_verdicts(monkeypatch, items):
    from open_guji_cv.gold.store import GoldStore
    monkeypatch.setattr(GoldStore, "list", lambda self, shard, legacy=True: items)


def test_escalated_boundaries_reads_escalate_flag_from_products(tmp_path, monkeypatch):
    """`pages=escalated` 的数据源：直接读 Step3 产物里 `escalate=True` 的切点（含 L0′ split_suspect
    与 L3 扩池候选），不重新跑图像判据——升级切点多半不在金标里，`list:` 模式出不来（2026-09-15）。"""
    import numpy as np
    from guji_manager.eval import touching as T
    from open_guji_cv.products.kinds.cells import CellRec, ColumnCells, CutPointCandidates, PageCells, SeamCandidate

    cells = PageCells(page=3, period=100.0, ref_w=150.0, columns=[ColumnCells(
        col=1, ok=True, n_body_slots=3, content_x=(5.0, 155.0), boundaries=[0.0, 100.0, 200.0, 300.0],
        cells=[CellRec(slot=s, pos=s, y0=(s - 1) * 100.0, y1=s * 100.0, x0=5.0, x1=155.0,
                       kind="char", order=s, ink_ratio=0.2) for s in (1, 2, 3)],
        cut_candidates=[
            CutPointCandidates(k=1, y=100.0, slot_above=1, slot_below=2, chosen=0, escalate=False,
                               candidates=[SeamCandidate(kind="straight")]),
            CutPointCandidates(k=2, y=200.0, slot_above=2, slot_below=3, chosen=0, escalate=True,
                               escalate_reason="split_suspect dis_unet=983>=100 n_cand=1", origin="split_suspect",
                               candidates=[SeamCandidate(kind="straight"),
                                           SeamCandidate(kind="unet_seam", y=[210] * 150, dis_unet=5)]),
        ])])

    class _St:
        def read(self, book, step, key, kind):
            return cells if step == "row_segment" else None

    class _IC:
        def get(self, *a, **kw):
            return "x.png"

    monkeypatch.setattr(T, "_col_profile", lambda *a, **kw: np.zeros(400), raising=False)
    monkeypatch.setattr("open_guji_cv.products.cache.ImageCache", lambda *a, **kw: _IC())
    # 读图走 `utils.image_io.imread`（字节读入，不经 cv2.imread，overview#407），桩打在它的引用上
    import open_guji_cv.eval.rulers as R
    for mod in (T, R):
        monkeypatch.setattr(mod, "cv_imread", lambda *a, **kw: np.zeros((400, 160), np.uint8))
    out, skipped = T.escalated_boundaries("vol02", [3], _St())
    assert [c["id"] for c in out] == ["vol02:3:1:2"]          # 只出 escalate 的那条
    c = out[0]
    assert c["origin"] == "split_suspect" and c["kind"] == "escalated" and c["col_h"] == 400
    assert c["slot_above"] == 2 and c["slot_below"] == 3 and c["y"] == 200
