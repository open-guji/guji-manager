import json,sys,collections as C,glob,os
sys.path.insert(0,'/home/user/guji-manager'); sys.path.insert(0,'/home/user/open-guji-cv')
from guji_manager.review.reasons import book_cells, ref_missing
from open_guji_cv.utils.pua_lookup import PuaIndex, resolve_pua_code
from pathlib import Path
idx=PuaIndex.from_source(sorted(Path('/home/user/dzg').glob('000*.jsonl')))
print('pua idx',len(idx.stream),len(idx.codes))
raw=json.load(open('/tmp/ps/r01_dian_raw.json'))
t={r['code']:r for r in map(json.loads,open('/tmp/ps/pua_table.jsonl'))}
gp=set(json.load(open('/tmp/ps/glyph_pending.json'))['codes'])
byv=C.defaultdict(list)
for x in raw: byv[x['_vol']].append(x)
out=[]
for v,xs in sorted(byv.items()):
    name=f"vol{int(v):02d}"; root=f"/home/user/packs/{name}"
    cells=book_cells(root,name)
    for x in xs:
        c=cells.get(x['cell'])
        r={'vol':name,'cell':x['cell'],'why':x['why'],'ctx':x['ctx'].get('c'),'lib_top':[(a['c'],a['s']) for a in x['lib_top']],'stale':(x.get('stale') or {}).get('c'),'list_refc':x.get('refc')}
        if not c: r['miss']=True; out.append(r); continue
        code=c.pua_code or (resolve_pua_code(idx,c.ref_left,c.ref_right) if ref_missing(c.ref) else None)
        r.update(ref=c.ref,char=c.char,L=c.ref_left[-8:],R=c.ref_right[:8],code=code,doubts=c.doubts,ev={k:c.evidence.get(k) for k in('cov','ctx_margin','verdict','guard')})
        tr=t.get(code) if code else None
        r['verdict']=tr['verdict'] if tr else None
        r['tchar']=tr.get('char') if tr else None
        r['tcands']=[a['char'] for a in tr.get('cands',[])] if tr else []
        r['pending_reg']=code in gp if code else False
        out.append(r)
json.dump(out,open('/home/user/work/r01_dian.json','w'),ensure_ascii=False,indent=0)
print(len(out))
