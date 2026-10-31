# 逐列格位表 v2（现用）：现切分有字格（cell_shrink）＋参照每行字数；扁条/tail_junk 记假字，只剩假字的列给空列，列与参照行 DP 对齐，印章段可丢。输出给册 yaml params.row_segment.layout_prior。
# 用法：VOL=05 python3 make_qtw_layout.py <out.jsonl>（输出本册各行，再追加进 <数据目录>/corpus/qtw_layout.jsonl；先跑一遍 Step1–4 得 cell_shrink，再生成表、再从 row_segment 重跑）
#
"""逐列格位表 v2：现切分有字格（cell_shrink）＋参照每行字数。
- 假字：flags 含 tail_junk/frame_bars，或扁条（高 < 0.4 格距且宽 > 0.7 列宽）——版框横线；
- 只有假字的列＝空列，表里给 slots []（row_segment 把表空格里的墨记空，印章同）；
- 有字列与参照行按序配对（列数对上才出这一页）；每列取字数＝参照字数、最紧凑、不含假字的一段；
- 含夹注格的列不出行。"""
import json,re,sys
from volcfg import *
pins=load_pins()
txt,_=load_txt()
han=lambda s: len(re.sub(r'[。，、：；！？「」『』<>\s]','',s))
P=205
def choose(good,n):
    if n<=0 or len(good)<n: return None
    best=min(range(len(good)-n+1),key=lambda i:(good[i+n-1]-good[i],i))
    keep=good[best:best+n]; drop=[x for x in good if x not in keep]
    if drop and (any(min(abs(x-k) for k in keep)<2 for x in drop) or (len(drop)>3 and any(min(abs(x-k) for k in keep)<3 for x in drop))):
        return None
    return keep
rows=[];st={'pages':0,'pages_skip':0,'cols':0,'empty':0,'skip':0}
skipped=[]
for pg,head in sorted(pins.items()):
    cs=json.load(open(f'{W}/cell_shrink/p{pg:04d}.json'))['char_index']
    if not cs: continue
    cols=[]
    for c in cs['columns']:
        ch=[x for x in c['chars'] if x['cell_type']!='blank']
        jz=any(x.get('sub') for x in ch)
        cw=max([x['bbox_col'][2] for x in ch]+[1])
        good=[];junk=[]
        for x in ch:
            j=('tail_junk' in x['flags'] or 'frame_bars' in x['flags'] or
               (x['height']<0.4*P and x['width']>0.7*cw and x['height']<x['width']/3))
            (junk if j else good).append(x['slot'])
        cols.append((c['col'],sorted(set(good)),jz))
    lines=[han(l) for l in txt.get(head,[]) if han(l)]
    text=[c for c in cols if c[1]]
    st['pages']+=1
    for col,good,jz in cols:
        if not good:
            rows.append({"vol":VOL,"page":pg,"col":col,"slots":[],"notes":[],"half":[],"raised":0}); st['empty']+=1
    # 列与参照行按序对齐（DP）：配对代价＝字数差，列可跳过（参照没录这一列：卷题、印章列），参照行也可跳过
    A,B=len(text),len(lines); INF=10**9
    cost=[[INF]*(B+1) for _ in range(A+1)]; bk={}
    cost[0][0]=0
    for i in range(A+1):
        for j in range(B+1):
            if cost[i][j]>=INF: continue
            for di,dj,c in ((1,1,(0 if choose(text[i][1],lines[j]) else 3) if i<A and j<B else None),(1,0,4),(0,1,4)):
                if c is None or i+di>A or j+dj>B: continue
                if cost[i][j]+c<cost[i+di][j+dj]: cost[i+di][j+dj]=cost[i][j]+c; bk[(i+di,j+dj)]=(i,j,di,dj)
    pairs=[]; i,j=A,B
    while (i,j)!=(0,0):
        pi,pj,di,dj=bk[(i,j)]
        if di and dj: pairs.append((text[pi],lines[pj]))
        i,j=pi,pj
    pairs.reverse()
    if len(pairs)<len(text): skipped.append((pg,len(text),len(lines),len(pairs)))
    for (col,good,jz),n in pairs:
        st['cols']+=1
        if jz: st['skip']+=1; continue
        keep=choose(good,n)
        if keep is None: st['skip']+=1; continue
        rows.append({"vol":VOL,"page":pg,"col":col,"slots":keep,"notes":[],"half":[],"raised":-min(0,min(keep))})
open(sys.argv[1],'w').write(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
print(st,len(rows)); print('skip pages',skipped)
