"""入人八 rr：各来源（整理本、现役对位、坐标对位、放行字、ctx、rr_img、ids）对目视真字的对错，以及几条候选放行规则的命中与误放。
需 items_new.json、seeds_new.json（目视标签 idx→truth，'?' 读不定）。"""
import json,sys,collections
sys.path.insert(0,'/home/user/open-guji-cv')
from open_guji_cv.groups.flow import _ref_pair_pick,_dissent_keep,_sname
its=json.load(open('items_new.json')); sd={r['idx']:r['truth'] for r in json.load(open('seeds_new.json'))}
c=lambda x:{'㑹':'會'}.get(x,x)
rr=[(i,r) for i,r in enumerate(its) if r['group']['id']=='rr']
st=collections.defaultdict(lambda:[0,0])
for i,r in rr:
    t=sd[i]
    if t=='?': continue
    for n,v in (('整理本',r['ref']),('现役对位',r['cur']),('坐标对位',r['coord']),('放行字',r['char'])):
        if v: st[n][0 if c(v)==t else 1]+=1
    for s in r['group']['solvers']:
        if s.get('char'): st[s['solver'].split(':')[-1]][0 if c(s['char'])==t else 1]+=1
for k,v in st.items(): print(f'{k}: 对{v[0]} 错{v[1]}')
res=[]
for i,r in rr:
    g=r['group']; tr=g['solvers']
    pick=(r['char'] if _dissent_keep('rr',tr,r['char'],r['ref'],c,1.0) else None) if g['mode']=='review' else _ref_pair_pick('rr',tr,r['ref'],c,1.5)
    if pick: res.append((i,pick,any(_sname(t)=='ctx' and t.get('char') and c(t['char'])==c(pick) for t in tr)))
for need in (False,True):
    s=[x for x in res if x[2] or not need]
    print('rr 开 dissent_keep/ref_pair','且要文意同意' if need else '(现行逻辑)',len(s),'对',sum(sd[i]==c(p) for i,p,_ in s),'错',sum(sd[i] not in('?',c(p)) for i,p,_ in s),'读不定',sum(sd[i]=='?' for i,p,_ in s))
