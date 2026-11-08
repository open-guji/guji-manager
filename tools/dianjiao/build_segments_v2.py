#!/usr/bin/env python3
"""v2：整册出段，带上下文重叠。每段 ≤max 字，在「列未满(⏎)」处切；段前后各附 2 列只读上下文(◁/▷)。
用法：build_segments_v2.py CHAR_JSON QUEUE_JSONL LAYOUT_JSONL OUTDIR [--pages 36-204] [--max 1500] [--prefix T]
产出 OUTDIR/<前缀>NN.txt（段输入）、.base.txt（段内机器字流）、.cells.json（疑问格）、.idx.json（段内每字的 全册格序/anchor/机器字）"""
import json,argparse,os
ap=argparse.ArgumentParser();ap.add_argument('char');ap.add_argument('queue');ap.add_argument('layout');ap.add_argument('out')
ap.add_argument('--pages',default='1-204');ap.add_argument('--max',type=int,default=1500);ap.add_argument('--vol',default='004');ap.add_argument('--prefix',default='T')
a=ap.parse_args();lo,hi=map(int,a.pages.split('-'))
q={}
for l in open(a.queue):
    r=json.loads(l)
    for c in r['cells']:q[c]=r
lay={}
for l in open(a.layout):
    r=json.loads(l)
    if r['vol']==a.vol:lay[(r['page'],r['col'])]=r
d=json.load(open(a.char))
lines=[];g=0   # line: dict(kind,page,col,cells[(g,anchor,ch,cid)],ind,short)
for pg in d['pages']:
    p=pg['page']
    for col in pg['columns']:
        cs=[];
        for c in col['cells']:
            cs.append((g,c['a'],c['c'],f"{a.vol}:{c['a']}"));g+=1
        if p<lo or p>hi:continue
        slots=(lay.get((p,col['col'])) or {}).get('slots') or [1]
        lines.append(dict(page=p,col=col['col'],cells=cs,ind=min(slots)-1,short=len(cs)<22))
segs=[];cur=[];n=0
for i,L in enumerate(lines):
    cur.append(i);n+=len(L['cells'])
    if n>=a.max and L['short'] or n>=a.max+300:segs.append(cur);cur=[];n=0
if cur:segs.append(cur)
os.makedirs(a.out,exist_ok=True)
def plain(L):return ''.join(c[2] for c in L['cells'])
for si,idxs in enumerate(segs,1):
    name=f'{a.prefix}{si:02d}';out=[];base='';cells=[];idx=[];k=0;lastpage=None
    for t in range(max(0,idxs[0]-2),idxs[0]):out.append('◁'+plain(lines[t]))
    for i in idxs:
        L=lines[i]
        if L['page']!=lastpage:out.append(f"⟨p{L['page']}⟩");lastpage=L['page']
        s=''
        for (gi,anc,ch,cid) in L['cells']:
            idx.append((gi,anc,ch))
            if cid in q:
                k+=1;r=q[cid];s+=f"〔{k}:{'|'.join(r['members'])}〕"
                cells.append(dict(n=k,cell=cid,machine=ch,group=r['group'],cands=r['members'],l=r['l'],r=r['r'],ver=r['ver']))
            else:s+=ch
            base+=ch
        out.append('　'*L['ind']+s+('⏎' if L['short'] else ''))
    for t in range(idxs[-1]+1,min(len(lines),idxs[-1]+3)):out.append('▷'+plain(lines[t]))
    open(f'{a.out}/{name}.txt','w').write('\n'.join(out)+'\n')
    open(f'{a.out}/{name}.base.txt','w').write(base)
    json.dump(cells,open(f'{a.out}/{name}.cells.json','w'),ensure_ascii=False)
    json.dump(idx,open(f'{a.out}/{name}.idx.json','w'),ensure_ascii=False)
    print(name,len(base),'字',len(cells),'问')
