import sys, collections
sys.path.insert(0,'/home/user/z02')
from loadall import rows
from open_guji_cv.groups.registry import GROUPS
from open_guji_cv.groups.ctx_l1 import CtxL1Backend, TARGET
from open_guji_cv.groups.flow import rules_path
WANT=sys.argv[1:]
N={'㓂':'寇','冦':'寇','㑹':'會'}
by={}
for g,rid in (w.split(':') for w in WANT): 
    by.setdefault(g,[]).append(rid)
bk={g:{r.id:r for r in CtxL1Backend(rules_path(g),GROUPS[g].members).rules} for g in by}
L=collections.defaultdict(lambda:collections.Counter()); R=collections.defaultdict(lambda:collections.Counter())
for r in rows():
    g=r['g']
    if g not in by: continue
    ref=r.get('ref')
    if not ref or ref=='〓' or ref not in GROUPS[g].members: continue
    s=r['L'][-20:]+TARGET+r['R'][:20]
    for rid in by[g]:
        ru=bk[g][rid]
        if ru.pattern.search(s):
            ok=N.get(ref,ref)==N.get(ru.char,ru.char)
            L[(g,rid)][(r['L'][-1:],ok)]+=1; R[(g,rid)][(r['R'][:1],ok)]+=1
for k in L:
    print('==',k)
    for nm,D in (('左',L[k]),('右',R[k])):
        toks=collections.defaultdict(lambda:[0,0])
        for (t,ok),n in D.items(): toks[t][0 if ok else 1]+=n
        print(nm,' '.join(f"{t}:{a}/{b}" for t,(a,b) in sorted(toks.items(),key=lambda x:-(x[1][0]+x[1][1])) if b>0 or a>=15))
