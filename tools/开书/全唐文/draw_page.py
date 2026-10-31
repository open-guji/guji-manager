# 把一页现行切分画在原图上（绿＝放行、红＝未放行）。用法：VOL=05 python3 draw_page.py <out.png> 3,48,103
#
"""把一页现行切分画在原图上：红框＝字块（cell_shrink bbox_page），绿＝已放行、红＝未放行。"""
import json,sys
from PIL import Image,ImageDraw
from volcfg import WS as W, VOL
def draw(pg,scale=4):
    im=Image.open(f'{W}/data_full/{VOL}/{pg}.png').convert('RGB'); w=im.width
    s=json.load(open(f'{W}/products/{VOL}/cell_shrink/p{pg:04d}.json'))['char_index']
    adm={x['id']:x['admit'] for c in json.load(open(f'{W}/products/{VOL}/seed_admit/p{pg:04d}.json'))['seed_admit']['columns'] for x in c['chars']}
    d=ImageDraw.Draw(im)
    for c in (s or {}).get('columns',[]):
        for x in c['chars']:
            x0,y0,x1,y1=x['bbox_page']  # 右上原点
            col=(0,170,0) if adm.get(x['id']) else (230,0,0)
            d.rectangle([w-1-x1,y0,w-1-x0,y1],outline=col,width=9)
    return im.resize((im.width//scale,im.height//scale))
pages=[int(p) for p in sys.argv[2].split(',')]
ims=[draw(p) for p in pages]
m=Image.new('RGB',(sum(i.width+10 for i in ims),max(i.height for i in ims)),'gray');x=0
for i in ims: m.paste(i,(x,0)); x+=i.width+10
m.save(sys.argv[1]); print(m.size)
