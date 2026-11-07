"""Z02 看图拼图：每格＝原图格 | 候选字库刻例×2 每个候选。python sheet2.py <name> <idx,idx,...> [cands...]"""
import json,sqlite3,io,sys,os
from PIL import Image,ImageDraw,ImageFont
name=sys.argv[1]; idxs=[int(x) for x in sys.argv[2].split(',')]
it=json.load(open('items.json'))
fonts=[ImageFont.truetype('/home/user/open-guji-cv/fonts/jigmo/'+f,22) for f in ('Jigmo.ttf','Jigmo2.ttf','Jigmo3.ttf')]
cj=ImageFont.truetype('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',15)
def dt(d,xy,s):
    x,y=xy
    for ch in s:
        f=cj
        try:
            if not cj.getmask(ch).getbbox() and ch!=' ': f=next((q for q in fonts if q.getmask(ch).getbbox()),cj)
        except Exception: pass
        d.text((x,y),ch,font=f,fill=0); x+=f.getlength(ch)
dbs={}
def db(b):
    p=f'/home/user/ws/{b}/output/glyph.db'
    if b not in dbs: dbs[b]=sqlite3.connect(p) if os.path.exists(p) else None
    return dbs[b]
def ex(b,ch,k=2):
    if not ch: return []
    if db(b) is None: return []
    q=db(b).execute("select i.patch_png from glyphs g join exemplars e using(glyph_id) join instances i using(instance_id) where g.char=? limit ?",(ch,k)).fetchall()
    return [Image.open(io.BytesIO(x[0])).convert('L') for x in q]
T=96
def cands(r):
    g=r['group']; s=[]
    for c in [r['char'],r['ref']]+[x.get('char') for x in g['solvers']]:
        if c and c not in s: s.append(c)
    return s[:3]
rows=[it[i] for i in idxs]
W=T*7+30; H=T+34
sh=Image.new('L',(2*W,((len(rows)+1)//2)*H),255); d=ImageDraw.Draw(sh)
for k,(i,r) in enumerate(zip(idxs,rows)):
    x0=(k%2)*W; y0=(k//2)*H
    cp=f"crops/{r['book']}/{r['vol']}_{r['cell'].replace(':','_')}.png"
    t=Image.open(cp).convert('L'); t.thumbnail((T,T)); sh.paste(t,(x0+2,y0+2)); d.rectangle([x0+1,y0+1,x0+2+t.width,y0+3+t.height],outline=0)
    x=x0+T+10
    for c in cands(r):
        for e in ex(r['book'],c):
            e=e.copy(); e.thumbnail((T-20,T-20)); sh.paste(e,(x,y0+2)); x+=T-18
        dt(d,(x,y0+30),c); x+=26
    g=r['group']
    dt(d,(x0+2,y0+T+4),f"#{i} M{r['char']} R{r['ref']} "+' '.join(f"{s['solver'].split(':')[-1]}={s.get('char') or '-'}" for s in g['solvers'])+" "+r['left'][-4:]+'['+r['char']+']'+r['right'][:4])
os.makedirs('sheets2',exist_ok=True); sh.save(f'sheets2/{name}.png'); print(sh.size)
