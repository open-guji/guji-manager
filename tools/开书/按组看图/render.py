"""按组看图定夺·第 2 步：把抽中的格渲成字块图（写进工作区 cache/<册>/char_patch/）。

用法：GUJI_WORKSPACE=<工作区> <cv 的 python> render.py <cells.jsonl> [册,册,…]
不给册就渲 cells.jsonl 里出现的所有册。需要能取原图（中心库读令牌）。
"""
import collections, json, sys
from open_guji_cv import steps as _s  # noqa: F401  注册各步
from open_guji_cv.core.book import load_book
from open_guji_cv.core.pipeline import default_pipeline_id, load_pipeline
from open_guji_cv.core.step import RunContext
from open_guji_cv.products.store import ProductStore
from open_guji_cv.products.cache import ImageCache
from open_guji_cv.feedback.anchor import patch_key

by = collections.defaultdict(list)
for l in open(sys.argv[1], encoding='utf-8'):
    b, p, c, s = json.loads(l)['id'].split(':')
    by[b].append((int(p), int(c), int(s)))
vols = sys.argv[2].split(',') if len(sys.argv) > 2 else sorted(by)
st, ca, fail = ProductStore(), ImageCache(), 0
for b in vols:
    bk = load_book(b)
    ctx = RunContext(bk, st, ca, log=lambda _: None, pipeline=load_pipeline(default_pipeline_id(bk)))
    for p, c, s in by[b]:
        try:
            if ctx.materialize('char_patch', patch_key(p, c, s)) is None:
                fail += 1
        except Exception:
            fail += 1
    print('册', b, len(by[b]), '格，累计失败', fail, flush=True)
