#!/usr/bin/env python3
"""专名匹配：entity.json（conv 产出）→ 对 book-index Entity 的 target 状态。
用法：match.py ENT.json... --index /path/to/book-index [--alias extra.tsv] [--annot extra.tsv] -o OUT.json
规则：名称→异体归一(opencc t2s＋EXT)→别名表→按类型过滤→唯一=matched；同名多个时按注家表朝代选，选中记 by=annotator；其余 ambiguous；无=new_candidate。地／邦／官同名多条时，若恰有一条 concept 级则 matched(by=concept)。
书名（Work 层）不在 Entity 里，状态 no_work_layer，另接。人名唯一≠安全：单字名标 weak=True，须抽检。"""
import json,glob,sys,os,collections,argparse
import opencc
T=opencc.OpenCC('t2s')
EXT={'𤣥':'玄','隠':'隱','觧':'解','䝉':'蒙','𫝊':'傳','廵':'巡','髙':'高','夀':'壽','敎':'教','羙':'美','隂':'陰','歴':'歷','黒':'黑','懐':'懷','臯':'皋','㑹':'會','釡':'釜','𣏌':'杞','兠':'兜','蓻':'藝','蓺':'藝','冣':'最'}
def K(n): return T.convert(''.join(EXT.get(c,c) for c in n))
SUB={'人':{'people'},'地':{'place'},'邦':{'place','dynasty','collective'},'官':{'office'},'時':{'reign','dynasty'}}
HERE=os.path.dirname(os.path.abspath(__file__))
def tsv(p):
    r={}
    for l in open(p,encoding='utf8'):
        if l.startswith('#') or not l.strip(): continue
        f=l.rstrip('\n').split('\t');r[f[0]]=f[1:]
    return r
def build_index(root):
    idx=collections.defaultdict(list)
    for f in glob.glob(f'{root}/Entity/*/*/*/*.json'):
        try:d=json.load(open(f,encoding='utf8'))
        except Exception: continue
        names=[d.get('primary_name')]+[a if isinstance(a,str) else (a or {}).get('name') for a in d.get('alt_names') or []]
        rec=(d['id'],d.get('subtype'),d.get('dynasty') or '',d.get('primary_name'),d.get('place_level') or d.get('office_level') or '')
        for n in set(x for x in names if x): idx[K(n)].append(rec)
    return idx
def match(e,idx,alias,annot):
    t=e['tag'];name=e['text']
    if t in('书','書'): return dict(status='no_work_layer')
    key=name
    if name in alias and alias[name][1] in ('人',t): key=alias[name][0]
    c=[x for x in idx.get(K(key),[]) if x[1] in SUB.get(t,set())]
    by='alias' if key!=name else 'name'
    if not c: return dict(status='new_candidate')
    if len(c)>1 and t=='人' and name in annot:
        d=annot[name][0];c2=[x for x in c if d in x[2]]
        if len(c2)==1: c=c2;by='annotator'
    if len(c)>1 and t in ('地','邦','官'):
        c2=[x for x in c if x[4]=='concept']
        if len(c2)==1: c=c2;by='concept'   # 跨朝代概念条，朝代留给后续按上下文挂具体条
    st='matched' if len(c)==1 else 'ambiguous'
    r=dict(status=st,by=by,cands=[x[0] for x in c[:5]],n=len(c))
    if st=='matched' and t=='人' and len(name)==1 and by=='name': r['weak']=True
    return r
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('ents',nargs='+');ap.add_argument('--index',required=True)
    ap.add_argument('--alias');ap.add_argument('--annot');ap.add_argument('-o',required=True)
    a=ap.parse_args()
    alias=tsv(f'{HERE}/alias.tsv');annot=tsv(f'{HERE}/annotators.tsv')
    if a.alias: alias.update(tsv(a.alias))
    if a.annot: annot.update(tsv(a.annot))
    idx=build_index(a.index);out=[];st=collections.Counter()
    for f in a.ents:
        for e in json.load(open(f,encoding='utf8'))['entities']:
            e['target']=match(e,idx,alias,annot);st[(e['tag'],e['target']['status'],e['target'].get('by',''))]+=1;out.append(e)
    for k,v in sorted(st.items()): print(k,v)
    json.dump(out,open(a.o,'w',encoding='utf8'),ensure_ascii=False)
