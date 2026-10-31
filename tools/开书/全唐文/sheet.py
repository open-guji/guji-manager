# 按 cell_shrink 某个旗随机抽格拼图看。用法：SRC=<cell_shrink 目录> python3 sheet.py boundary_ink out.png 30
#
import json,sys,random
from PIL import Image,ImageDraw
import os,glob
from volcfg import WS as W, VOL
SRC=os.environ.get('SRC',f'{W}/products/{VOL}/cell_shrink')
flag=sys.argv[1]; out=sys.argv[2]; N=int(sys.argv[3]) if len(sys.argv)>3 else 40
items=[]
for f in sorted(glob.glob(f'{SRC}/p*.json')):
    pg=int(f[-9:-5]); s=json.load(open(f))['char_index']
    if not s: continue
    for c in s['columns']:
        for x in c['chars']:
            if any(f.startswith(flag) for f in x['flags']): items.append((pg,x))
random.seed(1); random.shuffle(items); items=items[:N]
tiles=[]
for pg,x in items:
    col=int(x['id'].split(':')[2])
    im=Image.open(f'{W}/cache/{VOL}/column_image/p{pg:04d}c{col:02d}.png').convert('RGB')
    x0,y0,x1,y1=x['bbox_col']; pad=110
    t=im.crop((0,max(0,y0-pad),im.width,min(im.height,y1+pad))).copy()
    d=ImageDraw.Draw(t); oy=max(0,y0-pad)
    d.rectangle([x0,y0-oy,x1,y1-oy],outline=(255,0,0),width=5)
    t=t.resize((t.width//3,t.height//3)); d=ImageDraw.Draw(t); d.text((2,2),x['id'][3:],fill=(0,0,255))
    tiles.append(t)
cols=10; tw=max(t.width for t in tiles); th=max(t.height for t in tiles)
m=Image.new('RGB',(cols*(tw+4),((len(tiles)+cols-1)//cols)*(th+4)),'gray')
for i,t in enumerate(tiles): m.paste(t,((i%cols)*(tw+4),(i//cols)*(th+4)))
m.save(out); print(len(items),m.size)
