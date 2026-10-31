# 按格 id 列表拼图看。用法：python3 sheet_ids.py ids.json out.png
#
import json,sys
from PIL import Image,ImageDraw
from volcfg import WS as W
ids=json.load(open(sys.argv[1])); out=sys.argv[2]
tiles=[]
for k in ids:
    vol,pg,col,sl=k.split(':'); pg,col=int(pg),int(col)
    s=json.load(open(f'{W}/products/{vol}/cell_shrink/p{pg:04d}.json'))['char_index']
    x=[x for c in s['columns'] for x in c['chars'] if x['id']==k]
    if not x: continue
    x=x[0]
    im=Image.open(f'{W}/cache/{vol}/column_image/p{pg:04d}c{col:02d}.png').convert('RGB')
    x0,y0,x1,y1=x['bbox_col']; pad=90
    t=im.crop((0,max(0,y0-pad),im.width,min(im.height,y1+pad))).copy(); oy=max(0,y0-pad)
    d=ImageDraw.Draw(t); d.rectangle([x0,y0-oy,x1,y1-oy],outline=(255,0,0),width=5)
    t=t.resize((t.width//3,t.height//3)); ImageDraw.Draw(t).text((2,2),k[3:],fill=(0,0,255)); tiles.append(t)
cols=10; tw=max(t.width for t in tiles); th=max(t.height for t in tiles)
m=Image.new('RGB',(cols*(tw+4),((len(tiles)+cols-1)//cols)*(th+4)),'gray')
for i,t in enumerate(tiles): m.paste(t,((i%cols)*(tw+4),(i//cols)*(th+4)))
m.save(out)
