# 借殿本字形库到本地（分页 PAGE=100 避开 2000 行 500 错误）并重建 glyph.db。用法：GUJI_WORKSPACE=<工作区> .venv/bin/python borrow.py；重建后要重新导入字体域 font:jigmo、font:iming。
#
import sys, json
import os; from open_guji_cv.datastore import client as _C; _C.PAGE=int(os.environ.get("PAGE","100"))
from pathlib import Path
from open_guji_cv.datastore.client import BlobCache, WorkerSource
from open_guji_cv.datastore.workcopy import borrow_stores, data_dir, GS
from open_guji_cv.ops.central_glyph import glyph_hooks
ws = Path(sys.argv[1])
src = WorkerSource(branch="main")
extras, sig = borrow_stores(src, ws, cache=BlobCache(), bucket="main")
print("borrowed", sig, extras)
g = glyph_hooks(ws)
res = g.rebuild(ws, data_dir(ws) / GS.rstrip("/"), g.db_path, extras)
print(json.dumps(res, ensure_ascii=False)[:600])
