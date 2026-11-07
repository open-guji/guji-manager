import json,subprocess,os,shutil,collections,glob,sys
sys.path.insert(0,'/home/user/guji-manager')
os.environ['GUJI_DATA_TOKEN']=os.environ['GUJI_DATA_TOKEN_READ']
from guji_manager._cv import connect
from guji_manager.review.reasons import reasons_for_pending, book_cells
from guji_manager.pending_stats import nonbody_of_yaml
B={'sj':'988g3f0wsu','qtw':'995ejelvk0'}
def run(*a): return subprocess.run(a,capture_output=True,text=True)
out=[]
with connect() as con:
    cur=con.cursor(); vols={}
    for k,ws in B.items():
        cur.execute("select book, raw from books where ws=%s order by book",(ws,)); vols[k]=[(b,nonbody_of_yaml(r)) for b,r in cur.fetchall()]
for k,ws in B.items():
    wsd=f'/home/user/ws/{k}'
    for v,nbp in vols[k]:
        L=[l.split('\t') for l in run('guji','products','pack','list',v,'-w',wsd).stdout.splitlines() if l.lstrip().startswith('★')]
        if not L: continue
        lab=L[0][0].split('/')[-1].strip(); dst=f'/home/user/packs/{k}-{v}'
        if not os.path.isdir(f'{dst}/{v}/seed_admit'):
            run('guji','products','pack','fetch',v,'-w',wsd,'--label',lab,'--to',dst)
            for d in os.listdir(f'{dst}/{v}'):
                if d not in('seed_admit','align_ref','glyph_match'): shutil.rmtree(f'{dst}/{v}/{d}',ignore_errors=True)
        cells=book_cells(dst,v)
        keys=[c for c in cells if c.split(':')[0].lstrip('0') not in (nbp or {})]
        rs=reasons_for_pending({'cells':[{'cell':c} for c in keys]},dst,v)
        for c,(r,d) in rs.items():
            if r.value=='ref_lacuna':
                C=cells[c]
                out.append({'book':k,'vol':v,'label':lab,'cell':c,'char':C.char,'ref':C.ref,'op':C.ref_op,'cands':C.cands[:5],'doubts':C.doubts,'ev':C.evidence,'L':C.ref_left,'R':C.ref_right,'detail':d})
        print(k,v,lab,len(out),flush=True)
json.dump(out,open('/home/user/work/r01_other.json','w'),ensure_ascii=False)
