import json,subprocess,os,shutil,sys,collections
os.environ['GUJI_DATA_TOKEN']=os.environ['GUJI_DATA_TOKEN_READ']
rows=json.load(open('/tmp/ps/r01_dian_raw.json'))
vols=sorted({x['_vol'] for x in rows})
def run(*a): return subprocess.run(a,capture_output=True,text=True)
for v in vols:
    name=f"vol{int(v):02d}"; dst=f"/home/user/packs/{name}"
    if os.path.isdir(f"{dst}/{name}/seed_admit"): continue
    L=[l.split('\t') for l in run('guji','products','pack','list',name,'-w','/home/user/ws/siku').stdout.splitlines() if l.lstrip().startswith('★')]
    lab=L[0][0].split('/')[-1].strip()
    run('guji','products','pack','fetch',name,'-w','/home/user/ws/siku','--label',lab,'--to',dst)
    # keep only the layers needed
    for d in os.listdir(f"{dst}/{name}"):
        if d not in('seed_admit','align_ref','glyph_match'): shutil.rmtree(f"{dst}/{name}/{d}",ignore_errors=True)
    print(name,lab,flush=True)
