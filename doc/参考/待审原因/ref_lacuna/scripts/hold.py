import json,sys,collections as C,glob
sys.path.insert(0,'/home/user/guji-manager'); sys.path.insert(0,'/home/user/open-guji-cv')
from pathlib import Path
from open_guji_cv.utils.pua_lookup import PuaIndex, resolve_pua_code
from guji_manager.review.reasons import _load_layer, align_for_seed
idx=PuaIndex.from_source(sorted(Path('/home/user/dzg').glob('000*.jsonl')))
t={r['code']:r for r in map(json.loads,open('/tmp/ps/pua_table.jsonl'))}
res=[]
for vd in sorted(glob.glob('/home/user/packs/vol*/vol*')):
    v=vd.split('/')[-1]
    for f in sorted(glob.glob(vd+'/seed_admit/p*.json')):
        seed=_load_layer(Path(f),'seed_admit')
        if not seed: continue
        al=align_for_seed(seed,_load_layer(Path(vd)/'align_ref'/Path(f).name,'align_ref')) or {}
        ref={c['id']:c.get('align_char') for c in al.get('chars',[])}
        for c in al.get('coord') or []:
            if c.get('ref_char') and c['id'] not in ref: ref[c['id']]=c['ref_char']
        seq=[(ch,ref.get(ch['id']) or '□') for col in seed.get('columns',[]) for ch in col.get('chars',[]) if 'excluded' not in (ch.get('doubts') or [])]
        for i,(ch,r) in enumerate(seq):
            if r!='〓': continue
            L=''.join(x for _,x in seq[max(0,i-20):i]); R=''.join(x for _,x in seq[i+1:i+21])
            code=resolve_pua_code(idx,L,R)
            tr=t.get(code) if code else None
            res.append({'id':ch['id'],'admit':bool(ch.get('admit')),'ch':ch.get('char'),'chan':ch.get('channel'),'prov':ch.get('provenance'),'code':code,'verdict':tr['verdict'] if tr else None,'tchar':tr.get('char') if tr else None})
json.dump(res,open('hold.json','w'),ensure_ascii=False)
a=[r for r in res if r['admit'] and r['verdict']=='char']
print('all 〓',len(res),'admitted+char',len(a))
print(C.Counter((r['chan'],r['ch']==r['tchar']) for r in a).most_common())
for r in a:
    if r['ch']!=r['tchar']: print(r['id'],r['chan'],r['prov'],'放',r['ch'],'表',r['tchar'],r['code'])
