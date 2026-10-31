# 核对：每页非空列字数 vs 参照每行字数，打印一致率和对不上的页。用法：VOL=05 python3 cmp_kanripo.py [显示几页]
#
"""每页非空列字数 vs Kanripo 每行字数（按顺序配对非空列与行）。"""
import json,re,sys,collections
from volcfg import *
pins=load_pins()
txt,_=load_txt()
han=lambda s: len(re.sub(r'[。，、：；！？「」『』\s]','',s))
stats=collections.Counter(); bad=[]
for pg,head in sorted(pins.items()):
    cols=json.load(open(f'{W}/row_segment/p{pg:04d}.json'))['cells']['columns']
    n=[]
    for c in cols:
        k=0;seen=set()
        for x in c['cells']:
            if x['kind']=='blank': continue
            key=x.get('slot') if x.get('sub') else (x.get('slot'),x.get('sub'))
            if x.get('sub'): 
                k+=1  # 每半格算一字（夹注）
            else: k+=1
        n.append(k if c['ok'] else -1)
    ne=[x for x in n if x!=0]
    lines=[han(l) for l in txt.get(head,[])]
    m=sum(1 for a,b in zip(ne,lines) if a==b)
    stats['pages']+=1; stats['cols']+=len(lines); stats['match']+=m
    if len(ne)!=len(lines) or m<len(lines): bad.append((pg,ne,lines))
print(dict(stats), round(stats['match']/stats['cols']*100,1))
for b in bad[:int(sys.argv[1]) if len(sys.argv)>1 else 15]: print(b)
print('bad pages',len(bad))
