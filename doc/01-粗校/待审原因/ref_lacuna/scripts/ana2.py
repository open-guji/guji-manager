import json,sys,collections as C
sys.path.insert(0,'/home/user/open-guji-cv')
from pathlib import Path
from open_guji_cv.utils.daizhige import UNMAPPED, build_halves
out=[];codes={}
for h in build_halves(sorted(Path('/home/user/dzg').glob('000*.jsonl'))):
    for col in h.cols:
        for run in col.get('runs',[]):
            if run.get('t')=='note':
                for side in('r','l'):
                    pos={(k,i):c for k,i,c in run.get('pua_'+side,[])}
                    for k,(_,s) in enumerate(run.get(side,[])):
                        for i,ch in enumerate(s):
                            if ch==UNMAPPED: codes[len(out)]=pos.get((k,i),'IMG')
                            out.append(ch)
            else:
                pos={i:c for i,c in run.get('pua',[])}
                for i,ch in enumerate(run.get('s','')):
                    if ch==UNMAPPED: codes[len(out)]=pos.get(i,'IMG')
                    out.append(ch)
s=''.join(out)
print('all 〓',len(codes),C.Counter(v=='IMG' for v in codes.values()))
def resolve(L,R,k=8):
    L,R=L[-k:],R[:k]; tot=len(L)+len(R)
    if tot<6: return None,'short',0
    best,hits=0,set()
    for p,cd in codes.items():
        sc=sum(1 for a,b in zip(reversed(L),reversed(s[max(0,p-len(L)):p])) if a==b)+sum(1 for a,b in zip(R,s[p+1:p+1+len(R)]) if a==b)
        if sc>best: best,hits=sc,{cd}
        elif sc==best: hits.add(cd)
    if best<0.75*tot: return None,'nomatch',best/tot
    if len(hits)!=1: return None,'ambig:'+','.join(sorted(hits)),best/tot
    return next(iter(hits)),'ok',best/tot
sys.path.insert(0,'/home/user/guji-manager')
from guji_manager.review.reasons import book_cells
o=json.load(open('r01_dian.json'))
cache={}
for r in o:
    if r.get('code'): r['how']='window6'; continue
    v=r['vol']
    if v not in cache: cache[v]=book_cells(f'/home/user/packs/{v}',v)
    c=cache[v][r['cell']]
    cd,how,ratio=resolve(c.ref_left,c.ref_right)
    r['code2']=cd; r['how']=how; r['ratio']=round(ratio,2); r['Lfull']=c.ref_left; r['Rfull']=c.ref_right
json.dump(o,open('r01_dian2.json','w'),ensure_ascii=False,indent=0)
print(C.Counter((r['how'] if not r.get('code') else 'w6', 'IMG' if r.get('code2')=='IMG' else ('code' if r.get('code2') else '-')) for r in o))
