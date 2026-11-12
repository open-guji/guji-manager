"""列端版框：首/末格框伸到列图的上/下版框线附近，且格内贴该边有一条覆盖≥半宽的墨行。"""
import json,glob,os,numpy as np
from PIL import Image
TH=128
def run(prod,cache,vol,d=4,cov=0.45,band=12):
    out={}
    for f in sorted(glob.glob(f'{prod}/{vol}/cell_shrink/p*.json')):
        ci=json.load(open(f))['char_index']; pg=ci['page']
        cwf=f'{prod}/{vol}/column_warp/p{pg:04d}.json'
        if not os.path.exists(cwf): continue
        cws={c['col']:c for c in json.load(open(cwf))['column_windows']['columns']}
        for col in ci['columns']:
            ch=[x for x in col['chars'] if x.get('cell_type')=='char' and x.get('bbox_col')]
            if not ch: continue
            cn=int(ch[0]['id'].split(':')[2]); cw=cws.get(cn)
            if not cw: continue
            bt=cw.get('border_top_in_column') or 0.0; bb=cw.get('border_bottom_in_column')
            H=cw['warped_size'][1]
            if bb is None: bb=H
            p=f'{cache}/{vol}/column_image/p{pg:04d}c{cn:02d}.png'
            if not os.path.exists(p): continue
            img=None
            for c in ch:
                x0,y0,x1,y1=c['bbox_col']; hit=[]
                if y0<=bt+d: hit.append('top')
                if y1>=bb-d: hit.append('bot')
                if not hit: continue
                if img is None: img=np.asarray(Image.open(p).convert('L'))<TH
                sub=img[int(y0):int(y1),int(x0):int(x1)]
                if sub.size==0: continue
                w=sub.shape[1]; r=sub.mean(1)
                for s in hit:
                    rr=r[:band] if s=='top' else r[-band:]
                    if len(rr) and rr.max()>=cov: out.setdefault(c['id'],[]).append((s,float(rr.max())))
    return out
