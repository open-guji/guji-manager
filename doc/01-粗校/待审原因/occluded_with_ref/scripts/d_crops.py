"""D01/D02 取图：按按码现算出的逐格表（ai-team 待审清单-*/按码-逐格.tsv，reason 以 occluded 开头）逐册拉 ★main 的 cell_shrink、拉书影，裁格图到 d2/crops/。
路径写死在脚本头（G、WS、tsv、OUT），换环境先改；要 GUJI_DATA_TOKEN=$GUJI_DATA_TOKEN_READ GUJI_DATA_HOME=<目录>，WS 是已 `guji db pull` 过的假工作区。
`bbox_page` 的 x 从页右量，裁图用 manager 的 to_image_box 换算。每册约 1 分钟（拉书影为主），5 路并行。"""
import csv, json, os, sys, shutil, subprocess, collections, glob
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image
Image.MAX_IMAGE_PIXELS=None
sys.path.insert(0,'/home/user/guji-manager')
from guji_manager.review_pages.crop import to_image_box
G="/home/user/venv/bin/guji"; WS="/home/user/ws/siku"
rows=[r for r in csv.DictReader(open('/home/user/ai-team/domain/CV/质检/待审清单-2026-11-07-r7/按码-逐格.tsv'),delimiter='\t') if r['reason'].startswith('occluded')]
by=collections.defaultdict(list)
for r in rows: by[r['vol']].append(r)
OUT=Path('/home/user/d2/crops'); OUT.mkdir(exist_ok=True)
env={**os.environ,'GUJI_WORKSPACE':WS}
def run(*a): return subprocess.run(a,capture_output=True,text=True,env=env)
def one(v):
    rs=by[v]
    if all((OUT/f"{v}_{r['cell'].replace(':','_')}.png").exists() for r in rs): return
    L=[l.split('\t') for l in run(G,'products','pack','list',v,'-w',WS).stdout.splitlines() if l.lstrip().startswith('★')]
    lab=L[0][0].split('/')[-1].strip()
    tmp=Path(f'/home/user/d2/tmp/{v}'); shutil.rmtree(tmp,ignore_errors=True)
    run(G,'products','pack','fetch',v,'-w',WS,'--label',lab,'--steps','cell_shrink','--to',str(tmp))
    root=tmp if (tmp/v/'cell_shrink').is_dir() else tmp.parent
    img=Path(f'/home/user/d2/img/{v}'); 
    run(G,'source','pull',v,'-w',WS,'--to',str(img))
    for r in rs:
        page,col,idx=r['cell'].split(':')
        f=root/v/'cell_shrink'/f"p{int(page):04d}.json"
        if not f.exists(): print('nof',v,r['cell'],f); continue
        d=json.load(open(f)); d=d.get('char_index',d)
        bx=None
        for key in ('columns','alt_columns'):
            for c in d.get(key,[]) or []:
                for ch in c.get('chars',[]):
                    if ch['id']==f"{v}:{r['cell']}" or ch['id'].split(':',1)[1]==r['cell']: bx=ch.get('bbox_page')
        p=next(iter(glob.glob(str(img/f"{int(page)}.*"))),None)
        if not bx or not p: print('miss',v,r['cell'],bool(bx),p); continue
        im=Image.open(p).convert('L')
        im.crop(to_image_box(bx,im.width,6)).save(OUT/f"{v}_{r['cell'].replace(':','_')}.png")
    shutil.rmtree(tmp,ignore_errors=True); shutil.rmtree(img,ignore_errors=True)
    print('ok',v,flush=True)
with ThreadPoolExecutor(5) as ex: list(ex.map(one,sorted(by)))
