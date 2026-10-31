# 核对：全册与钉位页的放行率、cell_shrink 各类旗计数。用法：VOL=05 python3 metrics.py
#
import json,collections
import glob
from volcfg import *
PAGES=sorted(int(f[-9:-5]) for f in glob.glob(f'{W}/seed_admit/p*.json'))
a=r=0;body_a=body_r=0
pins=set(load_pins())
anch=0
for pg in PAGES:
    d=json.load(open(f'{W}/seed_admit/p{pg:04d}.json'))['seed_admit']
    a+=d['n_auto'];r+=d['n_review']
    if pg in pins: body_a+=d['n_auto'];body_r+=d['n_review']
cf=collections.Counter()
for pg in PAGES:
    s=json.load(open(f'{W}/cell_shrink/p{pg:04d}.json'))['char_index']
    if not s: continue
    for c in s['columns']:
        for x in c['chars']:
            for f in x['flags']: cf[f.split('：')[0][:20]]+=1
print(f'全册 放行 {a}/{a+r} = {100*a/(a+r):.1f}%  正文页 {body_a}/{body_a+body_r} = {100*body_a/(body_a+body_r):.1f}%')
print(dict(cf.most_common(8)))
