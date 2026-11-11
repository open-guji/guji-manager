"""列图＋格框墨账：逐格量 foreign（别格的墨进了本格框）、cut（本格字的墨落在框外）、line（细长直线进框）。"""
import json,glob,os,numpy as np,cv2
from PIL import Image
TH=128
def col_cells(prod,vol):
    out={}
    for f in sorted(glob.glob(f'{prod}/{vol}/cell_shrink/p*.json')):
        d=json.load(open(f))['char_index']; pg=d['page']
        for c in d['columns']:
            ch=[x for x in c['chars'] if x.get('cell_type')=='char' and x.get('bbox_col')]
            if ch: out[(pg,int(ch[0]['id'].split(':')[2]))]=ch
    return out

def slot_of(c):
    i=c['id'].split(':')[3]; return i.rstrip('ab'), i[-1] if i[-1] in 'ab' else ''

def analyze_col(img,cells,min_px=8):
    ink=(img<TH).astype(np.uint8); H,W=ink.shape
    # 先剥掉长直线（界行竖线、版框横线），否则它把一串字连成一块
    vl=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((200,1),np.uint8))
    hl=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((1,max(40,int(0.85*W))),np.uint8))
    lines=(vl|hl)>0
    ink=(ink>0)&~lines; ink=ink.astype(np.uint8)
    n,lab,st,_=cv2.connectedComponentsWithStats(ink,connectivity=8)
    boxes=[]
    for c in cells:
        x0,y0,x1,y1=[int(round(v)) for v in c['bbox_col']]
        boxes.append((max(0,x0),max(0,y0),min(W,x1),min(H,y1)))
    comp_in={}
    for k,(x0,y0,x1,y1) in enumerate(boxes):
        sub=lab[y0:y1,x0:x1]
        ids,cnt=np.unique(sub[sub>0],return_counts=True)
        for i,c in zip(ids,cnt): comp_in.setdefault(int(i),{})[k]=int(c)
    area=st[:,4]
    union=np.zeros_like(ink)
    for (x0,y0,x1,y1) in boxes: union[y0:y1,x0:x1]=1
    outside=np.bincount(lab[(union==0)&(ink>0)].ravel(),minlength=n)
    owner={}
    for i,ins in comp_in.items():
        k,c=max(ins.items(),key=lambda t:t[1]); owner[i]=k
    out=[]
    slots=[slot_of(c) for c in cells]
    for k,(x0,y0,x1,y1) in enumerate(boxes):
        own=foreign=cut=side=0; line=[]; frg=[]
        pieces=[(i,ins[k]) for i,ins in comp_in.items() if k in ins and area[i]>=min_px]
        box_ink=sum(c for i,c in pieces)
        for i,c in pieces:
            x,y,w,h,a=st[i]
            if owner[i]==k and (x<=1 or x+w>=W-1) and c<0.15*box_ink:
                side+=c; continue   # 贴列图左右边的小块：邻列字/界行残墨
            ok=owner[i]
            if ok==k or c>0.35*box_ink:
                own+=c
                if ok==k: cut+=int(outside[i])   # 本格字的墨落在所有格框外（半字）
                continue
            if slots[ok][0]==slots[k][0] and slots[ok][1]!=slots[k][1]: continue  # 夹注同号另半：发前抹白
            foreign+=c
            yy,xx=np.nonzero(lab[y0:y1,x0:x1]==i)
            pos='top' if yy.mean()<0.3*(y1-y0) else 'bot' if yy.mean()>0.7*(y1-y0) else 'left' if xx.mean()<0.5*(x1-x0) else 'right'
            frg.append((pos,int(c),cells[ok]['id']))
        lv=int(vl[y0:y1,x0:x1].sum()); lh=int(hl[y0:y1,x0:x1].sum())
        if lv>=20: line.append(('v',lv))
        if lh>=20: line.append(('h',lh))
        out.append(dict(id=cells[k]['id'],own=own,foreign=foreign,cut=cut,side=side,line=line,frg=frg,
                        fr=foreign/max(own,1),cr=cut/max(own,1)))
    return out

def run_vol(prod,cache,vol,pages=None):
    cc=col_cells(prod,vol); res=[]
    for (pg,col),cells in cc.items():
        if pages and pg not in pages: continue
        p=f'{cache}/{vol}/column_image/p{pg:04d}c{col:02d}.png'
        if not os.path.exists(p): continue
        img=np.asarray(Image.open(p).convert('L'))
        res+=analyze_col(img,cells)
    return res
