# 旧人裁找回落格：快审 HTML 里嵌的缩略字块与现格字块（同列 ±3 格）比 NCC，胜出明显的就是人当时看的字。输入：/tmp/claude/fakegs（由快审 HTML 解出的 patches/v2_<key>.png＋instances/review.jsonl，解法见 README）、现行 Step3 产物、数据目录 feedback/events。输出：补锚行 json（再按 README 写进 feedback/anchors/<册>.jsonl，之后 seed_admit 要 --force）。
# 用法：GUJI_WORKSPACE=<工作区> .venv/bin/python thumb_rebind.py <out.json>
#
"""首轮/二轮快审人裁 → 现行切分的格：拿快审页里嵌的缩略字块，与现格字块（同列 ±3 格）比相似度，
最像且明显胜出的那格就是人当时看的字。输出 anchors 行（bbox 取现格框）。"""
import json,sys,glob,re,os,io
import numpy as np
from PIL import Image
sys.path.insert(0,os.environ.get('CV','/home/user/open-guji/open-guji-cv'))
os.environ.setdefault('GUJI_WORKSPACE','/home/user/995ejelvk0-quan-tang-wen')
W=os.environ['GUJI_WORKSPACE']; VOL=os.environ.get('VOL','04')
FG='/tmp/claude/fakegs'
def thumb(im,h=52):
    w=max(8,round(im.width*h/im.height)); return im.resize((min(w,90),h),Image.LANCZOS)
def ncc(a,b):
    a=a.astype(np.float32).ravel();b=b.astype(np.float32).ravel()
    a-=a.mean();b-=b.mean(); d=np.sqrt((a*a).sum()*(b*b).sum())
    return float((a*b).sum()/d) if d>0 else 0.0
labels={json.loads(l)['instance_id'][3:]:json.loads(l)['label'] for l in open(f'{FG}/instances/review.jsonl')}
# 现格框
from open_guji_cv.products.store import ProductStore
from open_guji_cv.feedback.bindings import _cell_index
from open_guji_cv.report.slots import CELLS_KIND, cells_step
from open_guji_cv.core.spec import page_key
store=ProductStore(); step=cells_step(VOL)
evs=[json.loads(l) for f in sorted(glob.glob(os.path.expanduser('~/.guji-data/main/995ejelvk0/feedback/events/*.jsonl'))) for l in open(f) if l.strip()]
evs=[e for e in evs if e['kind']=='confirm' and e['target'].get('unit')=='cell' and not e['target'].get('anchor')]
idxc={}
def idx(pg):
    if pg not in idxc:
        c=store.read(VOL,step,page_key(pg),CELLS_KIND); idxc[pg]=_cell_index(c) if c is not None else {}
    return idxc[pg]
rows=[];stat={'ok':0,'weak':0,'nothumb':0,'nocand':0}
for e in evs:
    k=e['target']['key']; _,pg,col,sl=k.split(':'); pg,col=int(pg),int(col)
    m=re.fullmatch(r'(-?\d+)([ab]?)',sl); slot=int(m.group(1)); sub=m.group(2)
    f=f"{FG}/patches/v2_{k.replace(':','_')}.png"
    row={"event":e['id'],"key":k,"ts":e['ts'],"shape":(e.get('payload') or {}).get('shape'),"anchor":None,"evidence":{}}
    rows.append(row)
    if not os.path.exists(f): stat['nothumb']+=1; row['evidence']={"method":None,"reason":"无快审图块"}; continue
    t=np.array(Image.open(f).convert('L'))
    sc=[]
    for (c,s,sb),(bb,kind) in idx(pg).items():
        if c!=col or abs(s-slot)>3: continue
        pf=f"{W}/cache/{VOL}/char_patch/p{pg:04d}c{c:02d}s{s}{sb or ''}.png"
        if not os.path.exists(pf): continue
        cur=thumb(Image.open(pf).convert('L')).resize((t.shape[1],t.shape[0]),Image.LANCZOS)
        sc.append((ncc(t,np.array(cur)),(c,s,sb),bb))
    if not sc: stat['nocand']+=1; row['evidence']={"method":None,"reason":"同列 ±3 格无现格字块"}; continue
    sc.sort(key=lambda x:-x[0]); best=sc[0]; second=sc[1][0] if len(sc)>1 else 0
    if best[0]>=0.80 and best[0]-second>=0.10:
        stat['ok']+=1
        row['anchor']={"v":1,"space":"page_tr","bbox":best[2],"source":"backfill:review_thumb"}
        row['evidence']={"method":"review_thumb","at":f"{best[1][0]}:{best[1][1]}{best[1][2] or ''}","ncc":round(best[0],3),"ncc2":round(second,3)}
    else:
        stat['weak']+=1; row['evidence']={"method":None,"reason":f"缩略图比不出（{best[0]:.2f}／{second:.2f}）"}
print(stat,len(rows))
json.dump(rows,open(sys.argv[1],'w'),ensure_ascii=False)
