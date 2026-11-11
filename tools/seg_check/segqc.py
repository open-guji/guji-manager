"""切分毛病几何检测：只看裁图（格图），各书通用。"""
import numpy as np
from PIL import Image
try:
    import cv2
except ImportError:
    cv2=None

TH=128
def load(path):
    a=np.asarray(Image.open(path).convert('L'))
    return a

def comps(ink):
    n,lab,st,_=cv2.connectedComponentsWithStats(ink.astype(np.uint8),connectivity=8)
    return n,lab,st

def runs_max(v):
    """最长连续 True 段长"""
    best=cur=0
    for x in v:
        cur=cur+1 if x else 0
        if cur>best: best=cur
    return best

def features(a):
    ink=a<TH
    h,w=ink.shape
    out={'h':h,'w':w,'aspect':w/max(h,1)}
    tot=int(ink.sum()); out['tot']=tot
    if tot==0: return out
    # ---- 长横线（版框/界栏）：近上/下边的行，最长连续墨段≥0.6W，带厚≤max(3,0.07H)
    def hline(rows):
        best=None
        for y in rows:
            r=runs_max(ink[y])
            if r>=0.6*w:
                best=y if best is None else best
        return best
    zone=max(3,int(0.22*h))
    lines={}
    for side,rows in (('top',range(0,zone)),('bot',range(h-1,h-1-zone,-1))):
        ys=[y for y in rows if runs_max(ink[y])>=0.6*w]
        if ys:
            # 带厚：连续行数
            ys=sorted(ys); thick=ys[-1]-ys[0]+1
            # 直度：这几行墨像素的上下边是否平（每列墨高方差）
            band=ink[min(ys):max(ys)+1]
            colh=band.sum(0); colh=colh[colh>0]
            lines[side]=dict(thick=thick,var=float(colh.std()) if len(colh) else 0,
                             pos=(ys[0] if side=='top' else h-1-ys[-1]))
    out['hl']=lines
    vl={}
    zw=max(3,int(0.2*w))
    for side,cols in (('left',range(0,zw)),('right',range(w-1,w-1-zw,-1))):
        xs=[x for x in cols if runs_max(ink[:,x])>=0.6*h]
        if xs: vl[side]=dict(thick=max(xs)-min(xs)+1,pos=(min(xs) if side=='left' else w-1-max(xs)))
    out['vl']=vl
    # ---- 连通域：主体 = 面积最大的若干块（累计 ≥80% 墨），其余为碎块
    n,lab,st=comps(ink)
    areas=st[1:,cv2.CC_STAT_AREA]
    order=np.argsort(-areas)
    acc=0;main=[]
    for i in order:
        main.append(i+1); acc+=areas[i]
        if acc>=0.8*tot: break
    mx0=min(st[i,0] for i in main); my0=min(st[i,1] for i in main)
    mx1=max(st[i,0]+st[i,2] for i in main); my1=max(st[i,1]+st[i,3] for i in main)
    out['main_bbox']=(int(mx0),int(my0),int(mx1),int(my1))
    # 贴边碎块：不在主体里、贴某边（≤2px）、与主体有空隙
    frag={'top':0,'bot':0,'left':0,'right':0}
    for i in range(1,n):
        if i in main: continue
        x,y,ww,hh,ar=st[i]
        if ar<max(4,0.002*tot): continue
        if y<=2 and y+hh<=my0+2: frag['top']+=ar
        elif y+hh>=h-2 and y>=my1-2: frag['bot']+=ar
        elif x<=2 and x+ww<=mx0+2: frag['left']+=ar
        elif x+ww>=w-2 and x>=mx1-2: frag['right']+=ar
    out['frag']={k:v/tot for k,v in frag.items()}
    # 边行墨占比（切掉字）：上下左右各取 2 行/列的墨占比
    out['edge']={'top':float(ink[:2].mean()),'bot':float(ink[-2:].mean()),
                 'left':float(ink[:,:2].mean()),'right':float(ink[:,-2:].mean())}
    # 内部空白缝（两字并格）：纵向/横向投影里，中段 25–75% 有连续 ≥6% 的全空行，两边各≥25%墨
    def gap(prof,L):
        best=0
        lo,hi=int(0.2*L),int(0.8*L)
        cur=0;start=0
        for i in range(lo,hi):
            if prof[i]==0:
                if cur==0:start=i
                cur+=1
                if cur>best:
                    s1=prof[:start].sum(); s2=prof[i+1:].sum()
                    if min(s1,s2)>=0.2*tot: best=cur
            else: cur=0
        return best/L
    out['gap_v']=gap(ink.sum(1),h)   # 上下两字
    out['gap_h']=gap(ink.sum(0),w)   # 左右两字
    return out

def edge_lines(a, frac_w=0.5, max_thick=0.08, min_gap=2, gap_ink=0.03):
    """上下边与字身隔开的薄横带 / 左右边与字身隔开的薄竖带。返回 {side: dict}"""
    ink=a<TH; h,w=ink.shape; res={}
    for side in ('top','bot','left','right'):
        b = ink if side in('top','bot') else ink.T
        if side in ('bot','right'): b=b[::-1]
        H,Wd=b.shape
        rowink=b.sum(1)/Wd
        occ=rowink>gap_ink
        if not occ.any(): continue
        y0=int(np.argmax(occ))
        if y0>0.1*H: continue
        y=y0
        while y<H and occ[y]: y+=1
        y1=y
        while y<H and not occ[y]: y+=1
        gap=y-y1
        if y>=H or gap<min_gap: continue
        thick=y1-y0
        if thick>max(3,max_thick*H): continue
        band=b[y0:y1]; span=runs_max(band.any(0))/Wd
        if span<frac_w: continue
        res[side]=dict(thick=thick,gap=gap,span=span,off=y0)
    return res

def stroke_w(ink):
    """竖向墨段长中位数≈横画粗细"""
    L=[]
    for x in range(0,ink.shape[1],2):
        col=ink[:,x]; d=np.diff(np.r_[0,col.astype(int),0]); s=np.flatnonzero(d==1); e=np.flatnonzero(d==-1)
        L+=list(e-s)
    return float(np.median(L)) if L else 0

def edge_hlines2(a, zone=0.15, min_cov=0.3, close=7):
    """贴上/下边的细横线（可虚线、可只半截、可粘着字）：
    闭运算连虚线 → 横向开运算留长横段 → 近边行里找覆盖≥min_cov·W 的薄带，且带厚明显小于字的笔画粗。"""
    ink=(a<TH).astype(np.uint8); h,w=ink.shape
    if ink.sum()==0: return {}
    cl=cv2.morphologyEx(ink,cv2.MORPH_CLOSE,np.ones((1,close),np.uint8))
    k=max(15,int(0.3*w))
    op=cv2.morphologyEx(cl,cv2.MORPH_OPEN,np.ones((1,k),np.uint8))
    sw=stroke_w(ink.astype(bool))
    res={}
    zh=max(4,int(zone*h))
    for side in ('top','bot'):
        rows=range(0,zh) if side=='top' else range(h-1,h-1-zh,-1)
        cov=[(y,op[y].sum()/w) for y in rows]
        ys=[y for y,c in cov if c>=min_cov]
        if not ys: continue
        # 取最靠边的一段连续行
        ys=sorted(ys,key=lambda y: y if side=='top' else -y)
        band=[ys[0]]
        for y in ys[1:]:
            if abs(y-band[-1])==1: band.append(y)
            else: break
        thick=len(band); off=band[0] if side=='top' else h-1-band[0]
        if off>0.08*h+2: continue
        # 带内墨的上下沿要平：带厚小于笔画粗的 0.75 或 ≤4px
        if thick>max(4,0.75*sw): continue
        res[side]=dict(thick=thick,off=off,cov=max(c for y,c in cov if y in band),sw=sw)
    return res

def flat_edge_line(a, cov=0.45, band=14, min_span=0.4, max_std=1.2):
    """贴上/下边的一条『平直』横墨：边缘行覆盖≥cov；在该带里逐列取最靠边的墨点，
    最长一段相邻列（≥min_span·W）其墨点高度标准差≤max_std（尺子画的线平，笔画有起伏）。"""
    ink=a<TH; h,w=ink.shape; res={}
    if h<10 or w<10: return res
    for side in ('top','bot'):
        b=ink[:band] if side=='top' else ink[::-1][:band]
        if b.mean(1).max()<cov: continue
        has=b.any(0); first=np.argmax(b,axis=0).astype(float)
        # 最长连续有墨列段
        best=(0,0);s=None
        for x in range(w+1):
            if x<w and has[x]:
                if s is None: s=x
            else:
                if s is not None and x-s>best[1]-best[0]: best=(s,x)
                s=None
        x0,x1=best
        if x1-x0<min_span*w: continue
        seg=first[x0:x1]
        # 去掉笔画竖下来的影响：用分位数间距
        q=np.percentile(seg,[10,90]); std=float(seg[(seg>=q[0])&(seg<=q[1])].std())
        if std<=max_std: res[side]=dict(span=(x1-x0)/w,std=std)
    return res

def side_frag(a, max_w=0.3, max_ink=0.2, min_gap=2, min_ink=0.005, axis=0):
    """左右（axis=0）或上下（axis=1）贴边、与主体隔开空白的一小条墨：邻字/邻行残笔。"""
    ink=a<TH; prof=ink.sum(axis); L=len(prof); tot=prof.sum(); res={}
    if tot==0: return res
    occ=prof>0
    for side in ('lo','hi'):
        p=occ if side=='lo' else occ[::-1]; q=prof if side=='lo' else prof[::-1]
        if not p[0] and not p[1]: continue
        x=0
        while x<L and p[x]: x+=1
        x1=x
        while x<L and not p[x]: x+=1
        gap=x-x1
        if x>=L or gap<min_gap: continue
        frac=q[:x1].sum()/tot
        if x1<=max_w*L and min_ink<=frac<=max_ink: res[side]=dict(w=x1/L,gap=gap,frac=float(frac))
    return res
