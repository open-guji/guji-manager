"""crop.py <vol> <anchor_start> <anchor_end> <out.png> [label]：取该格所在列（含前后各一列）整条，框出目标格。"""
import json,sys,os,urllib.request,io,re
from PIL import Image, ImageDraw, ImageFont
B=os.environ.get('BOOK_DEFAULT_DIR','/home/user/book-text/Book/g/z/k/96mid1ogzk/default')  # book-text 某书 default 目录
_cord={}
def cord(v):
    if v not in _cord: _cord[v]=json.load(open(f'{B}/{v}.cord.json'))
    return _cord[v]
def page_img(v,page):
    fn=f'img/{v}-{page:04d}.png'
    if not os.path.exists(fn):
        u=f'https://data.openguji.com/iiif/96mid1ogzk/{v[-2:]}/wyg/{page:04d}/full/max/0/default.webp'
        try: data=urllib.request.urlopen(u,timeout=60).read()
        except Exception:
            info=json.load(urllib.request.urlopen(f'https://data.openguji.com/iiif/96mid1ogzk/{v[-2:]}/wyg/{page:04d}/info.json'))
            w=info['sizes'][-1]['width']
            data=urllib.request.urlopen(f'https://data.openguji.com/iiif/96mid1ogzk/{v[-2:]}/wyg/{page:04d}/full/{w},/0/default.webp',timeout=60).read()
        Image.open(io.BytesIO(data)).convert('RGB').save(fn)
    return Image.open(fn)
def key(a):
    m=re.match(r'(\d+):(\d+):(-?\d+)([ab]?)',a); return int(m[1]),int(m[2]),int(m[3]),m[4]
def crop(v,a0,a1,out,label=''):
    pg,col,_,_=key(a0)
    d=cord(v); P=next(p for p in d['pages'] if p['page']==pg)
    img=page_img(v,pg)
    sx=img.width/P['canvas']['width']; sy=img.height/P['canvas']['height']
    cols={c['col']:c['box'] for c in P['columns']}
    k0,k1=key(a0),key(a1)
    targets=[c for c in P['cells'] if key(c['a'])[1]==col and (k0[1],k0[2])<=(key(c['a'])[1],key(c['a'])[2])<=(k1[1],k1[2]) and c.get('box')] if k0[0]==k1[0] else [c for c in P['cells'] if c['a'] in (a0,) and c.get('box')]
    if not targets: targets=[c for c in P['cells'] if c['a']==a0 and c.get('box')]
    cs=[cols.get(c) for c in (col-1,col,col+1) if cols.get(c)]
    x0=min(b[0] for b in cs); x1=max(b[0]+b[2] for b in cs)
    y0=min(b[1] for b in cs); y1=max(b[1]+b[3] for b in cs)
    if targets:
        ty0=min(t['box'][1] for t in targets); ty1=max(t['box'][1]+t['box'][3] for t in targets)
        y0=max(y0,ty0-700); y1=min(y1,ty1+700)
    im=img.crop((int(x0*sx)-10,int(y0*sy)-10,int(x1*sx)+10,int(y1*sy)+10)).copy()
    dr=ImageDraw.Draw(im)
    for t in targets:
        bx,by,bw,bh=t['box']
        dr.rectangle(((bx-x0)*sx+10-3,(by-y0)*sy+10-3,(bx-x0+bw)*sx+10+3,(by-y0+bh)*sy+10+3),outline=(230,30,30),width=4)
    if label:
        try: f=ImageFont.truetype('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',28)
        except Exception: f=None
        can=Image.new('RGB',(max(im.width,520),im.height+44),'white'); can.paste(im,(0,44)); ImageDraw.Draw(can).text((6,4),label,fill=(0,0,0),font=f); im=can
    im.save(out)
if __name__=='__main__':
    crop(sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],sys.argv[5] if len(sys.argv)>5 else '')
