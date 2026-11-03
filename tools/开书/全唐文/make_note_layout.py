# 逐列格位表补小注格：语料短小注改回双行（make_grid_corpus.py，2026-11-03）后，把表里对应格写进 notes／half，缺表行的满列小注列补一行。
# 用法：<cv venv 的 python> make_note_layout.py <旧语料> <新语料> <现格位表> <page_pins.jsonl> <册,册,…> <输出表>
#   旧语料＝中心库现役 qtw_kanripo_grid.txt（短小注是〓），新语料＝make_grid_corpus.py 新出的；只动这两份逐行不同的半叶。
"""规则（册07 碑志 14 页实测，待审 256→82、放行格看图 0 错）：
- 本页参照行数与新旧一致、且不少于本页表里的列数时，按「第 k 列＝本半叶第 k 行」配列；对不上的页，表行整页删掉（交给小注判据）；
- 有表行的列：新行的字位单元数（不含空格位）＝表行 slots 数，就按序把 n 单元的格写进 notes（两半都有字）或 half（只有右半）；
  单元数不等但新行恰好满 22 格位的，改成 slots 1–22 再标；都不是就删这一行；
- 没表行的列：本半叶 9 行、该行无空格位且满 22 单元，就补一行（slots 1–22）。
需要 open_guji_cv（用它的 parse_lines 解行，保证与 align_ref 同口径）。"""
import json,sys,collections
from open_guji_cv.steps.align_ref_coord import parse_lines
gA,gB,lay,pins,vols,out=sys.argv[1:7]
vols=set(vols.split(','))
N_BODY=22
def leaves(p):
    d={};cur=None
    for l in open(p,encoding='utf-8').read().split('\n'):
        if l.startswith('#@ '): cur=l[3:].strip(); d[cur]=[]
        elif cur is not None and l.strip(): d[cur].append(l)
    return d
def units(line): return parse_lines('#@ x\n'+line)[0].units
def mark(r,u):
    return dict(r,notes=sorted(set(r.get('notes',[]))|{s for s,x in zip(r['slots'],u) if x.kind=='n' and x.b}),
                half=sorted(set(r.get('half',[]))|{s for s,x in zip(r['slots'],u) if x.kind=='n' and not x.b}))
A=leaves(gA);B=leaves(gB)
pin={(p['book'],p['page']):p['head'] for p in map(json.loads,open(pins))}
rows=[json.loads(l) for l in open(lay)]
ncol=collections.Counter()
for r in rows: ncol[(r['vol'],r['page'])]=max(ncol[(r['vol'],r['page'])],r['col'])
st=collections.Counter();res=[]
for r in rows:
    h=pin.get((r['vol'],r['page']))
    la,lb=A.get(h,[]),B.get(h,[])
    if r['vol'] not in vols or la==lb: res.append(r); continue
    if len(la)!=len(lb) or len(lb)<ncol[(r['vol'],r['page'])]: st['删·整页配不上']+=1; continue
    i=r['col']-1
    if la[i]==lb[i]: res.append(r); continue
    u=[x for x in units(lb[i]) if x.kind!='b']
    if len(u)!=len(r['slots']):
        if len(u)!=N_BODY: st['删·格数不等']+=1; continue
        r=dict(r,slots=list(range(1,N_BODY+1)),raised=0); st['改满列']+=1
    res.append(mark(r,u)); st['标小注']+=1
have={(r['vol'],r['page'],r['col']) for r in res}
for (v,pg),h in sorted(pin.items()):
    if v not in vols: continue
    la,lb=A.get(h,[]),B.get(h,[])
    if la==lb or len(la)!=len(lb) or len(lb)!=9: continue
    for i,(x,y) in enumerate(zip(la,lb)):
        if x==y or (v,pg,i+1) in have: continue
        u=units(y)
        if any(w.kind=='b' for w in u) or len(u)!=N_BODY: st['不补·非满列']+=1; continue
        res.append(mark({"vol":v,"page":pg,"col":i+1,"slots":list(range(1,N_BODY+1)),"notes":[],"half":[],"raised":0},u)); st['补行']+=1
with open(out,'w',encoding='utf-8') as f:
    for r in res: f.write(json.dumps(r,ensure_ascii=False)+'\n')
print(dict(st),'行',len(rows),'→',len(res))
