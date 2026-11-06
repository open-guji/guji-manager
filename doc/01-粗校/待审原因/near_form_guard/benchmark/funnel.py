"""N01 漏斗与基准底表（用法：python funnel.py [siku sj qtw]，要 GUJI_DATA_TOKEN、装好 guji-manager 与 cv）：三书 ★main 包，每册取 seed_admit/align_ref/glyph_match，
抽出「形近处境」的格（候选前三＋机器字里有手工形近家族字，或库护栏 conflict/never_match），不管放行没放行。"""
import json, os, subprocess, shutil, sys, glob
from concurrent.futures import ThreadPoolExecutor
os.environ["GUJI_DATA_TOKEN"]=os.environ["GUJI_DATA_TOKEN_READ"]
from guji_manager._cv import connect
from open_guji_cv.clustering.confusable import NEVER_MATCH_FAMILIES
FAM=frozenset(c for p in NEVER_MATCH_FAMILIES for c in p)
BOOKS={"siku":("siku-zongmu","/home/user/guji-workspace/96mid1ogzk-欽定四庫全書總目武英殿刻本"),
       "sj":("988g3f0wsu","/home/user/ws/988g3f0wsu"),"qtw":("995ejelvk0","/home/user/ws/995ejelvk0")}
OUT=os.environ.get("N01_OUT","/tmp/n01_funnel"); os.makedirs(OUT,exist_ok=True)
def run(*a): return subprocess.run(a,capture_output=True,text=True)
def lay(p,k):
    try: return json.load(open(p,encoding="utf-8"))[k]
    except Exception: return None
def one(args):
    b,v=args; _,w=BOOKS[b]; rf=f"{OUT}/{b}_{v}.jsonl"
    if os.path.exists(rf): return b,v,'cached'
    L=[l.split("\t") for l in run("guji","products","pack","list",v,"-w",w).stdout.splitlines() if l.lstrip().startswith("★")]
    if not L: open(rf,"w").close(); return b,v,'nomain'
    lab=L[0][0].split("/")[-1].strip(); tmp=f"{OUT}/_tmp/{b}_{v}"
    shutil.rmtree(tmp,ignore_errors=True)
    run("guji","products","pack","fetch",v,"-w",w,"--label",lab,"--to",tmp)
    root=f"{tmp}/{v}" if os.path.isdir(f"{tmp}/{v}/seed_admit") else tmp
    n=0
    with open(rf,"w") as fo:
        for f in sorted(glob.glob(f"{root}/seed_admit/p*.json")):
            seed=lay(f,"seed_admit")
            if not seed: continue
            al=lay(f"{root}/align_ref/{os.path.basename(f)}","align_ref") or {}
            gm=lay(f"{root}/glyph_match/{os.path.basename(f)}","glyph_match") or {}
            ref={c["id"]:(c.get("align_char"),c.get("align_op")) for c in al.get("chars",[])}
            for c in al.get("coord") or []:
                if c.get("ref_char") and c["id"] not in ref: ref[c["id"]]=(c["ref_char"],"coord")
            cands={c["id"]:c.get("candidates") or [] for col in gm.get("columns",[]) for c in col.get("chars",[])}
            for col in seed.get("columns",[]):
                for ch in col.get("chars",[]):
                    d=ch.get("doubts") or []
                    if "excluded" in d: continue
                    cid=ch["id"]; cs=cands.get(cid,[]); ev=ch.get("evidence") or {}
                    top3=[x[0] for x in cs[:3]]
                    guard=ev.get("guard")
                    if not ((set(top3)|{ch.get("char")})&FAM or guard in("conflict","never_match")): continue
                    r,op=ref.get(cid,(None,None))
                    fo.write(json.dumps(dict(b=b,v=v,id=cid,admit=bool(ch.get("admit")),channel=ch.get("channel"),prov=ch.get("provenance"),
                        char=ch.get("char"),ref=r,op=op,cands=cs[:5],guard=guard,doubts=d,cov=ev.get("cov"),verdict=ev.get("verdict")),ensure_ascii=False)+"\n"); n+=1
    shutil.rmtree(tmp,ignore_errors=True)
    return b,v,n
jobs=[]
for b,(ws,w) in BOOKS.items():
    if len(sys.argv)>1 and b not in sys.argv[1:]: continue
    with connect() as con:
        cur=con.cursor(); cur.execute("select book from books where ws=%s order by book",(ws,)); vs=[r[0] for r in cur.fetchall()]
    jobs+=[(b,v) for v in vs]
print(len(jobs),flush=True)
with ThreadPoolExecutor(int(os.environ.get("J","6"))) as ex:
    for r in ex.map(one,jobs): print(*r,flush=True)
print("done")
