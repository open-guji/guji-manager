#!/usr/bin/env python3
"""把 swap/auto_cycle 导出的 r9c 新文本放进 book-text（增删格路径）。用法: manual_swap.py volNN [export_dir]
规则（总纲）：待审/机器新结果为 □ 而现行有字 → 保持现行字；其余按导出。写 char（行内替换）、cord、norm、fig 及变动的图。"""
import json,re,sys,glob,shutil,os
vol=sys.argv[1]; n=vol[3:]; ch=f'{int(n):03d}'
WS='/home/user/96mid1ogzk-si-ku-zong-mu/reports/'+vol+'/_cycle/'
E=sys.argv[2] if len(sys.argv)>2 and not sys.argv[2].startswith('--') else sorted(glob.glob(WS+'*/export'))[-1]
D=os.environ.get('BT','/home/user/book-text')+'/Book/g/z/k/96mid1ogzk/default/'
cells=lambda c:[(x['a'],x['c']) for p in c['pages'] for col in p['columns'] for x in col['cells']]
old=json.load(open(D+ch+'.char.json')); new=json.load(open(E+'/'+ch+'.char.json'))
o=dict(cells(old)); nn=cells(new)
added=[a for a,_ in nn if a not in o]; removed=[a for a in o if a not in dict(nn)]
restore={a:o[a] for a,c in nn if a in o and c=='□' and o[a] not in ('□',None)}
adopt=[(a,o[a],c) for a,c in nn if a in o and c!='□' and c!=o[a]]
print(vol,'cells old/new',len(o),len(nn),'added',added[:10],len(added),'removed',removed[:10],len(removed),'restore □→现字',len(restore),'adopt 机器改字',len(adopt),adopt[:8])
if '--dry' in sys.argv: sys.exit()
def _flat(o):
    if isinstance(o,dict): return not any(isinstance(v,(dict,list)) for v in o.values())
    if isinstance(o,list): return not any(isinstance(x,dict) for x in o)
    return True
def dumps(obj):
    def enc(o,ind):
        if _flat(o) or (isinstance(o,dict) and not o): return json.dumps(o,ensure_ascii=False)
        pad,sub=" "*ind," "*(ind+2)
        if isinstance(o,dict):
            body=",\n".join(f"{sub}{json.dumps(k,ensure_ascii=False)}: {enc(v,ind+2)}" for k,v in o.items())
            return "{\n"+body+"\n"+pad+"}"
        return "[\n"+",\n".join(sub+enc(x,ind+2) for x in o)+"\n"+pad+"]"
    return enc(obj,0)+"\n"
oldtxt=open(D+ch+'.char.json',encoding='utf-8').read()
assert dumps(json.loads(oldtxt))==oldtxt,'现行 char 格式与 dumps 不一致'
n_restored=0
for p in new['pages']:
    for col in p['columns']:
        for x in col['cells']:
            if x['a'] in restore:
                x['c']=restore[x['a']]; x.pop('lacuna',None); x.pop('guess_c',None); n_restored+=1
assert n_restored==len(restore),(n_restored,len(restore))
new['version']=old['version']
open(D+ch+'.char.json','w',encoding='utf-8').write(dumps(new))
for f in ('cord','norm','fig'):
    p=E+'/'+ch+'.'+f+'.json'
    if os.path.exists(p): shutil.copy(p,D+ch+'.'+f+'.json')
fd=E+'/fig/'+ch
if os.path.isdir(fd):
    os.makedirs(D+'fig/'+ch,exist_ok=True)
    for f in os.listdir(fd):
        t=D+'fig/'+ch+'/'+f
        if not os.path.exists(t) or open(t,'rb').read()!=open(fd+'/'+f,'rb').read(): shutil.copy(fd+'/'+f,t); print('fig',f)
print('written')
