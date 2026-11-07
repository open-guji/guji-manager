"""把 extract_z.py 的输出（out_new/*.json，只含现行 dev 判法下的 Z02 格）合成 items_new.json。
用法：先 VOLS=<册号逗号分隔> J=5 python extract_z.py（OUT 目录在脚本里），再 python collect_items.py。"""
import json,glob,collections
its=[]
for f in sorted(glob.glob('out_new/*.json')):
    d=json.load(open(f))
    if 'z02' not in d: print(f,d.get('skip')); continue
    b=f.split('/')[-1].split('-')[0]
    for r in d['z02']: r['book']=b; its.append(r)
json.dump(its,open('items_new.json','w'),ensure_ascii=False)
print(len(its),dict(collections.Counter(r['book'] for r in its)))
