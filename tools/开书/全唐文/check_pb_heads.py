# Kanripo 半叶分界检查（开新册前置步骤，只读不改）：对每个有页钉位的页，拿本页 seed_admit 各列和逐列本比，
# 在 ±W 行（缺省 30）里找最像的起始行，报「当前对不上、偏移 k 处明显更像」的页。fix_b_heads.py 只搜 ±6 且只管 b 头，漏掉了偏 8 行以上的页（册11 p116/p150/p154）。
# 用法：python3 check_pb_heads.py <产物根> <逐列本> <page_pins.jsonl> 册 [册…] [--w 30] [--json out.json]
import json,re,sys,difflib
args=sys.argv[1:]
W=30; out=None
if '--w' in args: i=args.index('--w'); W=int(args[i+1]); del args[i:i+2]
if '--json' in args: i=args.index('--json'); out=args[i+1]; del args[i:i+2]
prod,grid,pinsf,*vols=args
cl=lambda s: re.sub(r'[^㐀-鿿\U00020000-\U0003ffff]','',s)
content=[];hp={}
for l in open(grid,encoding='utf-8').read().split('\n'):
    if l.startswith('#@ '): hp[l[3:].strip()]=len(content)
    elif l.strip(): content.append(cl(l))
pins=[json.loads(l) for l in open(pinsf,encoding='utf-8') if l.strip()]
res=[]
for r in pins:
    v=str(r['book']).zfill(2)
    if v not in vols or r['head'] not in hp: continue
    try: s=json.load(open(f"{prod}/{v}/seed_admit/p{int(r['page']):04d}.json",encoding='utf-8'))['seed_admit']
    except FileNotFoundError: continue
    cols=[''.join(x['char'] or '' for x in sorted(c['chars'],key=lambda x:str(x['slot']).zfill(4)) if not x.get('sub')) for c in s['columns']][:9]
    use=[(i,c) for i,c in enumerate(cols) if len(c)>=3]
    if len(use)<3: continue
    L=hp[r['head']]
    def score(k):
        if L+k<0 or L+k+len(cols)>len(content): return -1
        return sum(difflib.SequenceMatcher(None,c,content[L+k+i]).ratio() for i,c in use)/len(use)
    sc={k:score(k) for k in range(-W,W+1)}
    k=max(sc,key=sc.get)
    if k!=0 and sc[k]-sc[0]>=0.15 and sc[k]>=0.45:
        res.append(dict(vol=v,page=r['page'],head=r['head'],k=k,s0=round(sc[0],2),sk=round(sc[k],2)))
for x in res: print(*x.values())
print('共',len(res),'页；偏移分布',{k:sum(1 for x in res if x['k']==k) for k in sorted({x['k'] for x in res})})
if out: json.dump(res,open(out,'w'),ensure_ascii=False,indent=1)
