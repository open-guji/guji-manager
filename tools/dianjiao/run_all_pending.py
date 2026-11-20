import json,random,os,sys,collections,concurrent.futures as cf
import anthropic
client=anthropic.Anthropic(api_key=os.environ['GUJI_ANTHROPIC_API_KEY'],max_retries=4)
SYS=open('run.py').read().split('SYS="""')[1].split('"""')[0]
P=json.load(open('../pending.json')); G=json.load(open('../gold.json'))
BAD=set('□〓▣')
def cands(r):
    s=[]
    for c in [r.get('cur'),r.get('ref')]+r.get('lib',[])+r.get('alt',[]):
        if c and len(c)==1 and c not in BAD and c not in s: s.append(c)
    return s[:6]
items=[]
seen=set()
for i,r in enumerate(G):
    if 'ref' not in r or not r.get('ctx_ok') or r['cur']!=r['human']: continue
    k=(r['vol'],r['cell'])
    if k in seen: continue
    seen.add(k); c=cands(r)
    if r['human'] not in c: continue
    items.append(dict(id=f'g{i}',kind='gold',reason=r['reason'],key=f"vol{r['vol']:02d}:{r['cell']}",L=r['L'],R=r['R'],cands=c,human=r['human'],cur=r['cur'],ref=r['ref']))
for i,r in enumerate(P):
    c=cands(r)
    if len(c)<2: continue
    items.append(dict(id=f'p{i}',kind='pend',reason=r['reason'],key=f"vol{r['vol']:02d}:{r['cell']}",L=r['L'],R=r['R'],cands=c,cur=r['cur'],ref=r.get('ref')))
print(collections.Counter(x['kind'] for x in items))
def ask(chunk,rev):
    lines=[f"{x['id']}｜候选：{'、'.join(x['cands'][::-1] if rev else x['cands'])}｜{x['L'][-20:]}【？】{x['R'][:20]}" for x in chunk]
    msg=client.messages.create(model='claude-opus-5-5',max_tokens=8000,system=SYS,output_config={"effort":"medium"},messages=[{"role":"user","content":"\n".join(lines)}])
    out={}
    for l in ''.join(b.text for b in msg.content if b.type=='text').splitlines():
        l=l.strip()
        if l.startswith('{'):
            try: o=json.loads(l); out[o['id']]=o
            except: pass
    return out
def run(rev):
    rs=items[:]; random.seed(rev+9); random.shuffle(rs)
    ch=[rs[i:i+25] for i in range(0,len(rs),25)]; res={}
    with cf.ThreadPoolExecutor(8) as ex:
        for o in ex.map(lambda c:ask(c,rev),ch): res.update(o)
    return res
A=run(0);B=run(1)
json.dump(dict(items=items,A=A,B=B),open('all_raw.json','w'),ensure_ascii=False)
print('done',len(A),len(B))
