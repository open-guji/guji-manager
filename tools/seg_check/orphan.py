"""漏切：列图里整块墨不在任何格框里（剥掉界行/版框长线后），面积≥本列格中位墨量的 25%。"""
import sys,os,json,numpy as np,cv2
from PIL import Image
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from ctx2 import col_cells
TH=128
def orphans(img,cells,frac=0.25,edge=6):
    ink=(img<TH).astype(np.uint8); H,W=ink.shape
    vl=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((200,1),np.uint8))
    hl=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((1,max(40,int(0.85*W))),np.uint8))
    ink=((ink>0)&~((vl|hl)>0)).astype(np.uint8)
    # 墨块按字距合并：竖向闭运算 9px，把一个字的散笔画连起来
    blob=cv2.morphologyEx(ink,cv2.MORPH_CLOSE,np.ones((9,9),np.uint8))
    n,lab,st,_=cv2.connectedComponentsWithStats(blob,connectivity=8)
    union=np.zeros_like(ink)
    inks=[]
    for c in cells:
        x0,y0,x1,y1=[int(round(v)) for v in c['bbox_col']]
        union[max(0,y0):y1,max(0,x0):x1]=1; inks.append(int(ink[max(0,y0):y1,max(0,x0):x1].sum()))
    med=float(np.median(inks)) if inks else 0
    ytop=min(c['bbox_col'][1] for c in cells); ybot=max(c['bbox_col'][3] for c in cells)
    out=[]
    for i in range(1,n):
        x,y,w,h,a=st[i]
        m=lab[y:y+h,x:x+w]==i
        realink=int((ink[y:y+h,x:x+w]*m).sum())
        if realink<frac*med or realink<150: continue
        inside=int((union[y:y+h,x:x+w]*m*ink[y:y+h,x:x+w]).sum())
        if inside>0.2*realink: continue
        if h<=30 and (w>=0.5*W or w>=4*h): continue   # 版框残带
        fill=realink/(w*h)
        if w>=0.8*W and h<=60 and fill>=0.25: continue   # 粗版框带（列尾整宽黑带，r41 05:50:7、02:171:5）
        ys_,xs_=np.nonzero(ink[y:y+h,x:x+w]*m); cx=x+xs_.mean()
        if (cx>=0.85*W or cx<=0.15*W) and fill<0.3: continue   # 版框折角（墨心贴列边、稀疏，r41 05:93:2）
        if w<=0.3*h and w<=25: continue                 # 界行竖线残段
        if realink/(w*h)<0.10: continue      # 稀疏框形：界行/版框的折角残线
        sub=(ink[y:y+h,x:x+w]*m).astype(np.uint8)
        k,_,s2,_=cv2.connectedComponentsWithStats(sub,connectivity=8)
        if k-1>=15 and np.median(s2[1:,4])<40: continue   # 网点/霉斑碎点
        if x<=1 and x+w<=0.25*W or x+w>=W-1 and x>=0.75*W: continue   # 邻列字边
        where='head' if y+h<=ytop+5 else 'tail' if y>=ybot-5 else 'mid'
        out.append(dict(bbox=[int(x),int(y),int(x+w),int(y+h)],ink=realink,med=med,where=where))
    return out
if __name__=='__main__':
    prod,cache,vols,outp=sys.argv[1],sys.argv[2],sys.argv[3].split(','),sys.argv[4]
    rows=[]
    for v in vols:
        for (pg,col),cells in col_cells(prod,v).items():
            p=f'{cache}/{v}/column_image/p{pg:04d}c{col:02d}.png'
            if not os.path.exists(p): continue
            for o in orphans(np.asarray(Image.open(p).convert('L')),cells):
                rows.append(f"{v}:{pg}:{col}\t{o['where']}\t{o['ink']}\t{round(o['ink']/max(o['med'],1),2)}\t{o['bbox']}")
        print(v,sum(1 for r in rows if r.startswith(v+':')),file=sys.stderr)
    open(outp,'w').write('列\t位置\t墨\t占中位\tbbox\n'+'\n'.join(rows)+'\n')
