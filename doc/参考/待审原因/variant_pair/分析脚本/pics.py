import json,subprocess,shutil,random,sys,os
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
R=json.load(open('/home/user/v01/rows2.json'))
WS={'siku':'/home/user/ws/siku','shiji':'/home/user/ws/shiji','qtw':'/home/user/ws/qtw'}
LAB={}
for k in WS:
    pass
def run(*a): return subprocess.run(a,capture_output=True,text=True)
VOLS={('siku','vol09'),('siku','vol10'),('siku','vol48'),('siku','vol78'),('siku','vol79'),('siku','vol69'),('siku','vol45'),('siku','vol59'),('shiji','02'),('shiji','03'),('shiji','08'),('shiji','05'),('qtw','015'),('qtw','012')}
random.seed(3)
def cat3(r):
    c=r['cat']
    if c=='machine=ref': return 'E'
    if c.startswith('noedge'): return 'F'
    if c.startswith('edge to machine char'): return {'T1':'A','T2':'B','T3':'C'}[c[-2:]]
    return 'D1' if c.endswith('T1') else 'D2'
for r in R: r['c3']=cat3(r)
import collections
S={}
for c in ['A','B','C','D1','D2','E','F']:
    L=[r for r in R if r['c3']==c and (r['book'],r['vol']) in VOLS]
    if len(L)<12: L+= [r for r in R if r['c3']==c and (r['book'],r['vol']) not in VOLS][:12-len(L)]
    random.shuffle(L); S[c]=L[:16]
need=collections.defaultdict(set)
for c,L in S.items():
    for r in L: need[(r['book'],r['vol'])].add(r['cell'])
box={}
for (b,v),_ in need.items():
    img=Path(f'/home/user/img/{b}-{v}')
    if not img.exists() or not any(img.iterdir()):
        img.mkdir(parents=True,exist_ok=True); run('guji','source','pull',v,'-w',WS[b],'--to',str(img))
    L=[l.split('\t') for l in run('guji','products','pack','list',v,'-w',WS[b]).stdout.splitlines() if l.lstrip().startswith('★')]
    lab=L[0][0].split('/')[-1].strip(); tmp=Path(f'/home/user/v01/tmp/pc-{b}-{v}'); shutil.rmtree(tmp,ignore_errors=True)
    run('guji','products','pack','fetch',v,'-w',WS[b],'--label',lab,'--to',str(tmp))
    root=tmp/v if (tmp/v/'cell_shrink').is_dir() else tmp.parent/v
    for f in (root/'cell_shrink').glob('p*.json'):
        ci=json.load(open(f))['char_index']
        for key in ('columns','alt_columns'):
            for col in ci.get(key,[]) or []:
                for ch in col.get('chars',[]): box.setdefault(f'{b}:{ch["id"]}',ch.get('bbox_page'))
    print(b,v,flush=True)
font=ImageFont.truetype('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',13)
try: fu=ImageFont.truetype('/usr/share/fonts/opentype/unifont/unifont.otf',14)
except Exception: fu=font
def txt(dr,xy,s,**k):
    # per-char fallback to unifont for rare chars
    x,y=xy
    for ch in s:
        f=font
        try:
            if font.getmask(ch).getbbox() is None or font.getmask(ch).size==(0,0): f=fu
        except Exception: f=fu
        if f is font and ord(ch)>0x2A6DF: f=fu
        dr.text((x,y),ch,font=f,fill=0); x+=14
def crop(r):
    k=f"{r['book']}:{r['vol']}:{r['cell']}"; b=box.get(k)
    if not b: return None
    pg=int(r['cell'].split(':')[0]); p=Path(f"/home/user/img/{r['book']}-{r['vol']}/{pg}.png")
    if not p.exists(): return None
    im=Image.open(p).convert('L'); W=im.size[0]
    x0,y0,x1,y1=b; return im.crop((int(W-x1)-5,int(y0)-5,int(W-x0)+5,int(y1)+5))
out=Path('/home/user/v01/pics'); out.mkdir(exist_ok=True)
for c,L in S.items():
    cw,chh,cols=110,185,8; rows=(len(L)+cols-1)//cols
    can=Image.new('L',(cols*cw,rows*chh),255); dr=ImageDraw.Draw(can)
    for i,r in enumerate(L):
        im=crop(r); x,y=(i%cols)*cw,(i//cols)*chh
        if im: im.thumbnail((cw-8,chh-62)); can.paste(im,(x+4,y+3))
        top=r['cands'][0][0] if r['cands'] else '-'
        txt(dr,(x+3,chh*(i//cols)+chh-58),f"参{r['ref']} 机{r['char']}",)
        txt(dr,(x+3,chh*(i//cols)+chh-42),f"首{top} {r['book'][:2]}{r['vol'][-2:]}")
        txt(dr,(x+3,chh*(i//cols)+chh-26),r['left'][-3:]+'□'+r['right'][:3])
    can.save(out/f'V01-{c}.png'); print(c,len(L))
json.dump({c:[(r['book'],r['vol'],r['cell']) for r in L] for c,L in S.items()},open('/home/user/v01/pics/samples.json','w'),ensure_ascii=False)
