# 把 fix_b_heads.py 挪好的半叶头写回 book-text 的 pages.tsv，同时按挪动表从原逐列本生成新逐列本。
# moved.json＝[[头, 挪动行数], …]（逐列本前后对比得出）；只取卷 lo–hi 的头。pages.tsv 原文件是 CRLF，写回前要转。
# 用法：apply_pb_moves.py <原逐列本> <moved.json> <卷lo> <卷hi> <新逐列本> <book-text default 目录> <新pages.tsv>
import json,sys,csv,glob,os,re
src,mv,lo,hi,out,base,tsv_out=sys.argv[1:]
lo,hi=int(lo),int(hi)
raw=open(src,encoding='utf-8').read().split('\n')
moves={h:k for h,k in json.load(open(mv)) if lo<=int(h.split('_')[2][:4])<=hi}
# 拿掉要挪的头，记下原内容下标
cont=[];heads=[];n=0
for l in raw:
    if l.startswith('#@ '):
        h=l[3:].strip()
        heads.append((n,l))
    elif l.strip(): n+=1
newpos={}
for (n0,l) in heads:
    h=l[3:].strip()
    newpos[l]=n0+moves.get(h,0)
lines=[l for l in raw if not l.startswith('#@ ')]
# 重新插：按新下标，同下标保持原顺序
from collections import defaultdict
ins=defaultdict(list)
for (n0,l) in heads: ins[newpos[l]].append(l)
res=[];n=0
for l in lines:
    if l.strip():
        res+=ins.pop(n,[]); n+=1
    res.append(l)
for k in sorted(ins): res+=ins[k]
open(out,'w',encoding='utf-8').write('\n'.join(res))
# pages.tsv：内容下标 → (文件, 行号)，与 make_grid_corpus 同口径
rows=list(csv.reader(open(base+'/pages.tsv',encoding='utf-8'),delimiter='\t'))
pbset={(r[0],int(r[1])) for r in rows[1:]}
idx2=[];
for p in sorted(glob.glob(base+'/[0-9][0-9][0-9]*.md')):
    fn=os.path.basename(p);started=False
    for i,line in enumerate(open(p,encoding='utf-8').read().split('\n'),1):
        if (fn,i) in pbset: started=True
        if not started or line.startswith('#') or not line.strip(): continue
        idx2.append((fn,i))
old={}
n=0
for l in raw:
    if l.startswith('#@ '): old[l[3:].strip()]=n
    elif l.strip(): n+=1
ch=0
for r in rows[1:]:
    if r[2] in moves:
        f,i=idx2[old[r[2]]+moves[r[2]]]
        assert f==r[0],(r,f)
        r[1]=str(i);ch+=1
w=csv.writer(open(tsv_out,'w',encoding='utf-8',newline=''),delimiter='\t',lineterminator='\n')
w.writerows(rows)
print('moves',len(moves),'tsv changed',ch)
