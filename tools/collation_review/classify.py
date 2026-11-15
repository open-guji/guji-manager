import csv,glob,json,re,collections,opencc
cc=opencc.OpenCC('t2s')
VAR=set();LOOSE=set();SIMP=set();DIST=set();REL=set()
for l in open('/home/user/open-guji-cv/config/hanzi/core/edges.tsv',encoding='utf-8'):
    c=l.rstrip('\n').split('\t')
    if len(c)<3: continue
    a,b,k=c[0],c[1],c[2]
    src=c[4] if len(c)>4 else ''
    if k in('variant','variant_partial','z'): LOOSE.add((a,b)); LOOSE.add((b,a))
    s={'variant':VAR if src in ('twedu','unihan:kSemanticVariant') else None,'z':VAR,'simp':SIMP,'distinct':DIST}.get(k)
    if s is not None: s.add((a,b)); s.add((b,a))
def U(cp): return chr(int(cp[2:],16))
for l in open('/tmp/claude-0/unihan/Unihan_Variants.txt',encoding='utf-8'):
    if l.startswith('#') or not l.strip(): continue
    cp,k,v=l.rstrip('\n').split('\t')
    a=U(cp)
    for t in v.split():
        b=U(t.split('<')[0])
        if k in('kZVariant','kSemanticVariant'): VAR.add((a,b));VAR.add((b,a))
        if k in('kSimplifiedVariant','kTraditionalVariant'): SIMP.add((a,b));SIMP.add((b,a))
gv=json.load(open('/home/user/ref/glyph-variants.json'))['pairs'].split('\n')
for p in gv:
    p=p.strip()
    if len(p)>=2: VAR.add((p[0],p[1]));VAR.add((p[1],p[0]))
import sys; sys.path.insert(0,'/home/user/cmp'); from rules import RULE_PAIRS
for (x,y),n in RULE_PAIRS.items():
    if '繁简' in n: SIMP.add((x,y))
def rare(ch): return ord(ch)>0x9FFF or 0x3400<=ord(ch)<=0x4DBF
def charkind(a,b):
    if a==b: return 'same'
    if (a,b) in DIST: return 'diff'
    if (a,b) in SIMP and not (a,b) in VAR: return 'simp'
    if (rare(a) or rare(b)) and (a,b) in LOOSE: return 'var'
    if cc.convert(a)==cc.convert(b): return 'simp'
    if (a,b) in VAR: return 'var'
    if (a,b) in SIMP: return 'simp'
    # 繁简后再查异体
    if (cc.convert(a),cc.convert(b)) in VAR or cc.convert(a)==b or cc.convert(b)==a: return 'var'
    return 'diff'
NUM=set('一二三四五六七八九十百')
def kind(base,ref):
    if ref is None: return None
    if base==ref: return 'same'
    if len(base)==len(ref):
        ks=[charkind(a,b) for a,b in zip(base,ref)]
        if all(k in('same','var','simp') for k in ks):
            return '异体' if 'var' in ks else '繁简'
        if base and all(ch in NUM for ch in base+ref) and base=='一': return '凡例编号'
        return '改字'
    if base=='一' and ref and all(ch in NUM for ch in ref): return '凡例编号'
    return '增删'
rows=[]
for f in sorted(glob.glob('/home/user/ai-team/domain/文本/参校审阅/殿本第1-5册/0*.tsv')):
    for r in csv.DictReader(open(f,encoding='utf-8',newline=''),delimiter='\t'):
        st=r['状态']
        if st in('规矩放过','搁置·异体','转格修复'): continue
        cls=r['三方类']; b=r['底本']; z=r['殆知阁']; w=r['维基']
        kz=kind(b,z) if cls[0] in 'ABD' or cls.startswith('H') else None
        kw=kind(b,w) if cls[0] in 'ACD' or cls.startswith('H') else None
        ks=[k for k in (kz,kw) if k and k!='same']
        if cls.startswith('C大段'): k='版本异文'
        elif not ks: k='?'
        elif any(x in('改字','增删') for x in ks): k='增删' if '增删' in ks else '改字'
        else: k=ks[0]
        r['类']=k; r['file']=f; rows.append(r)
json.dump(rows,open('/home/user/cmp/r3/rows.json','w'),ensure_ascii=False)
c=collections.Counter((r['类'],r['三方类'][:1]) for r in rows)
for k,v in sorted(c.items()): print(k,v)
print('合计',len(rows))
for k in('异体','繁简','改字','凡例编号'):
    xs=[r for r in rows if r['类']==k]
    print('==',k,len(xs)); print(' '.join(f"{r['底本']}/{r['维基'] if r['三方类'][0]!='B' else r['殆知阁']}" for r in xs[:60]))
