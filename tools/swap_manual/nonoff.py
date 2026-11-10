import subprocess,sys,json,re
f=sys.argv[1]
old=json.loads(subprocess.check_output(['git','show','HEAD:'+f]));new=json.load(open(f))
def key(d):
    out=[]
    for k in ('entities','punctuations'):
        for x in d.get(k,[]):
            y=json.loads(json.dumps(x))
            for kk in ('span','char_offset'):
                y.pop(kk,None)
            for kk in list(y):
                if 'offset' in kk: y.pop(kk)
            out.append(json.dumps(y,ensure_ascii=False,sort_keys=True))
    return out
a,b=key(old),key(new)
from collections import Counter
ca,cb=Counter(a),Counter(b)
dl=list((ca-cb).elements());ad=list((cb-ca).elements())
print(f.split('/')[-1],'entries',len(a),len(b),'removed',len(dl),'added',len(ad))
for x in dl[:6]: print(' -',x[:220])
for x in ad[:6]: print(' +',x[:220])
