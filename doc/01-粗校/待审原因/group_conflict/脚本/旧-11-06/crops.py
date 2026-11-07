import json, os, sys, shutil, subprocess, glob, collections
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,'/home/user/guji-manager')
from guji_manager.review_pages.crop import to_image_box
from PIL import Image
Image.MAX_IMAGE_PIXELS=None
G="/home/user/venv/bin/guji"
WS={"siku":"/home/user/ws/siku","sj":"/home/user/ws/sj","qtw":"/home/user/ws/qtw"}
rows=json.load(open('rows.json'))
by=collections.defaultdict(list)
for r in rows: by[(r['book'],r['vol'])].append(r)
def run(*a,**k): return subprocess.run(a,capture_output=True,text=True,**k)
def one(key):
    b,v=key; w=WS[b]; out=Path(f"crops/{b}"); out.mkdir(parents=True,exist_ok=True)
    todo=[r for r in by[key] if not (out/f"{v}_{r['cell'].replace(':','_')}.png").exists()]
    if not todo: return
    img=Path(f"img/{b}-{v}"); 
    run(G,"source","pull",v,"-w",w,"--to",str(img),env={**os.environ,"GUJI_WORKSPACE":w})
    for r in todo:
        pg=int(r['page'][1:5]); bx=(r['box'] or {}).get('bbox_page')
        p=img/f"{pg}.png"
        if not bx or not p.exists(): print('miss',key,r['cell'],bool(bx),p.exists()); continue
        im=Image.open(p).convert('L')
        im.crop(to_image_box(bx,im.width,4)).save(out/f"{v}_{r['cell'].replace(':','_')}.png")
    shutil.rmtree(img,ignore_errors=True)
with ThreadPoolExecutor(5) as ex: list(ex.map(one,sorted(by)))
print('done')
