import sys,json,collections; sys.path.insert(0,'/home/user/z02')
from loadall import rows
from open_guji_cv.groups.flow import _ref_pair_pick,_dissent_keep,rules_path
from open_guji_cv.groups.registry import GROUPS
from open_guji_cv.groups.ctx_l1 import CtxL1Backend
from open_guji_cv.groups.protocol import JudgeInput, window_from_text
N={'㓂':'寇','冦':'寇','㑹':'會','𧰼':'象','岀':'出'}
canon=lambda c:N.get(c,c)
it=json.load(open('items.json')); sd={r['idx']:r for r in json.load(open('seeds.json'))}
scan={}
want={(r['vol'],r['cell']) for r in it}
for r in rows():
    k=(r['vol'],r['id'])
    if k in want and r['book']==('siku' if True else ''): scan[(r['book'],)+k]=r
bk={}
def l1(g,L,R):
    if g not in bk: bk[g]=CtxL1Backend(rules_path(g),GROUPS[g].members)
    v=bk[g].judge(GROUPS[g],JudgeInput(id='x',ref=None,window=window_from_text(L,R)))
    return v.char
part=collections.defaultdict(list)
for i,r in enumerate(it):
    g=r['group']; tr=g['solvers']; gid=g['id']; M=r['char']; R=r['ref']; mode=g['mode']
    chars={canon(t['char']) for t in tr if t.get('char')}|{canon(M)}
    raw={t['char'] for t in tr if t.get('char')}|{M}
    cls=None
    pm=[t for t in tr if ':' in t['solver'] and t.get('why') in ('abstain:llm_pending','cache_miss','abstain:llm_api_400')]
    if len(chars)==1 and len(raw)>1: cls='A 异形同字（解法给的字与放行字只差写法）'
    elif len(chars)==1 and mode=='joint' and pm: cls='D2 联合判：搭档组没有文意裁定'
    elif mode=='review' and _dissent_keep(gid,tr,M,R,canon,1.0): cls='B1 复核：只有弱图像票反对（整理本＝放行字）'
    elif mode=='review':
        # L1 规则孤证：ctx 是 L1 且是唯一反对者；重算新规则是否还命中
        dis=[t for t in tr if t.get('char') and canon(t['char'])!=canon(M)]
        if len(dis)==1 and dis[0]['solver'].split(':')[-1]=='ctx' and dis[0].get('via')=='ctx:ctx_l1' and canon(R or '')==canon(M):
            s=scan.get(('siku' if r['book']=='siku' else r['book'],r['vol'],r['cell']))
            if s:
                nc=l1(gid,s['L'][-20:],s['R'][:20])
                cls='B2 复核：L1 规则孤证误判（收窄规则后不再反对）' if nc!=dis[0]['char'] else 'B2x L1 规则孤证（收窄后仍命中）'
        if cls is None:
            ctxd=[t for t in dis if t['solver'].split(':')[-1]=='ctx']
            cls='C 复核：文意孤证反对（rr 入人八为主）' if len(dis)==len(ctxd)>=1 else 'C2 复核：其他'
    else:
        if _ref_pair_pick(gid,tr,R,canon,1.5): cls='D1 补放／联合判：整理本×本组解法一致，反对只有图像路'
        else:
            part_miss=[t for t in tr if ':' in t['solver'] and t.get('why') in ('abstain:llm_pending','cache_miss','abstain:llm_api_400')]
            cls='D2 联合判：搭档组没有文意裁定' if (mode=='joint' and part_miss) else 'D3 补放／联合判：其他（码位、搭档反对、整理本不一致）'
    part[cls].append(i)
tot=0
for k in sorted(part):
    ids=part[k]; t=collections.Counter()
    for i in ids:
        tr=sd[i]['truth']; M=it[i]['char']
        t['放行字对' if tr!='?' and canon(M)==tr else ('放行字错' if tr!='?' else '读不定')]+=1
    print(k,len(ids),dict(t),collections.Counter(it[i]['group']['id'] for i in ids).most_common(8))
    tot+=len(ids)
print(tot)
json.dump({k:v for k,v in part.items()},open('partition.json','w'),ensure_ascii=False)
