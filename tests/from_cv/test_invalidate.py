"""人裁落定 → 该页产物显式失效（ManifestEntry.invalidated）→ 引擎标 stale → 下次跑批重算。

指纹只认代码 / 参数 / 上游产物，裁决不在里面；不加这条，Step3 按裁决表收敛候选
（feedback/lookup.py）就永远等不到那一页重跑。2026-09-13。
"""

from __future__ import annotations

from open_guji_cv.core.engine import FRESH, STALE
from open_guji_cv.core.spec import page_key
from open_guji_cv.core.step import STEPS
from guji_manager.feedback.consumers import product_invalidate
from open_guji_cv.feedback.events import EventTarget, make_event
from guji_manager.feedback.routes import Destination, RouteTable
from open_guji_cv.products.manifest import Manifest, ManifestEntry
from test_core_v2 import make_engine, world  # noqa: F401  —— 复用合成两步管线


def _cutline(book, page, col, slot, seq=1):
    return make_event(f"{book}-cutline", seq, "cutline",
                      EventTarget(step="row_segment", unit="boundary", key=f"{book}:{page}:{col}:{slot}",
                                  book=book, page=page, col=col, slot=slot),
                      {"y": 100, "y_old": 100, "verdict": "ok"})


def test_product_invalidate_consumer_marks_the_routed_step_for_that_page(world):  # noqa: F811
    eng = make_engine(world)
    eng.run(pages=[1, 2])
    dest = Destination(consumer="product_invalidate", extra={"step": "t_step_a"})
    res = product_invalidate([(_cutline("tb", 1, 3, 5), dest), (_cutline("tb", 1, 4, 7, seq=2), dest)],
                             product_store=eng.store)
    assert res.added == 1 and not res.errors                # 同页两条裁决只失效一次
    assert eng.page_status(STEPS["t_step_a"], 1)[0] == STALE
    assert eng.page_status(STEPS["t_step_a"], 2)[0] == FRESH
    # 没跑过的页：skipped 不是错
    res2 = product_invalidate([(_cutline("tb", 3, 1, 1, seq=3), dest)], product_store=eng.store)
    assert res2.skipped == 1 and not res2.errors
    # 路由没给 step：报错不静默
    res3 = product_invalidate([(_cutline("tb", 1, 1, 1, seq=4), Destination(consumer="product_invalidate"))],
                              product_store=eng.store)
    assert res3.errors


def test_default_routes_send_cutline_to_product_invalidate_row_segment():
    dests = RouteTable.load(None).destinations(_cutline("vol02", 5, 8, 14))
    inv = [d for d in dests if d.consumer == "product_invalidate"]
    assert inv and inv[0].extra == {"step": "row_segment"}
    assert any(d.consumer == "gold_add" and d.shard == "char-segmentation/touching-cuts" for d in dests)


