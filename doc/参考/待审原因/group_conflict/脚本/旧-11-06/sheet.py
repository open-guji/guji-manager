"""Z02 拼图：每格＝原图格 + 标签（序号、组、放行字、参、库首位、各解法给的字、前后文）。python sheet.py [per]"""
import json, os, sys, collections
from PIL import Image, ImageDraw, ImageFont
per=int(sys.argv[1]) if len(sys.argv)>1 else 12
rows=json.load(open('rows.json'))
fonts=[ImageFont.truetype('/home/user/open-guji-cv/fonts/jigmo/'+f,20) for f in ('Jigmo.ttf','Jigmo2.ttf','Jigmo3.ttf')]
cj=ImageFont.truetype('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',16)
def draw_text(d,xy,s,fill=0):
    x,y=xy
    for ch in s:
        f=cj
        try:
            if not cj.getmask(ch).getbbox() and ch!=' ':
                f=next((q for q in fonts if q.getmask(ch).getbbox()),cj)
        except Exception: pass
        d.text((x,y),ch,font=f,fill=fill); x+=f.getlength(ch)
def lab(r):
    g=r['group']; sv=[]
    for s in g['solvers']:
        n=s['solver'].split(':')[-1]; sv.append(f"{n}={s.get('char') or '-'}")
    return [f"{r['book'][:2]}{r['vol'][3:]}:{r['cell']} {g['id']} {g.get('mode')[0]}/{g.get('why')[:3]}/{(g.get('decision') or '')[:3]}",
            f"放{r['char'] or '∅'} 参{r['ref'] or '∅'} 库{r['top'] or '∅'} " + ' '.join(sv),
            f"{r['left'][-6:]}[{r['char'] or ''}]{r['right'][:6]}"]
os.makedirs('sheets',exist_ok=True)
items=sorted(rows,key=lambda r:(r['group']['id'],r['group'].get('mode'),r['char'] or '',r['vol'],r['cell']))
json.dump(items,open('items.json','w'),ensure_ascii=False)
T=110; cols=2; W=560; H=T+78
for s in range(0,len(items),per):
    ch=items[s:s+per]; nr=(len(ch)+cols-1)//cols
    sh=Image.new('L',(cols*W,nr*H),255); d=ImageDraw.Draw(sh)
    for i,r in enumerate(ch):
        x0=(i%cols)*W; y0=(i//cols)*H
        cp=f"crops/{r['book']}/{r['vol']}_{r['cell'].replace(':','_')}.png"
        if os.path.exists(cp):
            t=Image.open(cp).convert('L'); t.thumbnail((T*2,T)); sh.paste(t,(x0+4,y0+2)); d.rectangle([x0+3,y0+1,x0+4+t.width,y0+2+t.height],outline=0)
        d.text((x0+4+T*2-80,y0+4),f"#{s+i}",font=cj,fill=0)
        for k,l in enumerate(lab(r)): draw_text(d,(x0+4,y0+T+4+k*22),l)
    sh.save(f'sheets/s{s//per:02d}.png')
print(len(items),(len(items)+per-1)//per)
