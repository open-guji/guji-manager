# 目录页配篇题（第一步）：每列 glyph_match 首选字串去本卷正文 Kanripo 短行里找最像的一行。输入：products/04/glyph_match、page_pins、语料；脚本里 TOC/BODY 两张表写死册04 各卷目录页与正文页范围。输出：toc_match.json。
# 用法：VOL=05 python3 toc_match.py /tmp/claude/toc_match_05.json（目录页/正文页范围在 volcfg.py）
#
"""册04 目录页：每列识别出的字（glyph_match 首选）去本卷正文 Kanripo 的短行（篇题）里找最像的一行。"""
import json,re,difflib,sys
from volcfg import *
pins=load_pins()
txt,order=load_txt()
clean=lambda s: re.sub(r'[。，、：；！？「」『』\s]','',s)
res={}
for juan,pages in TOC.items():
    heads=[pins[p] for p in BODY[juan] if p in pins]
    i0,i1=order.index(heads[0]),order.index(heads[-1])
    cands=[clean(l) for h in order[i0:i1+1] for l in txt[h]]
    cands=[c for c in cands if 3<=len(c)<=24]
    for pg in pages:
        import os
        if not os.path.exists(f'{W}/glyph_match/p{pg:04d}.json'): continue
        gm=json.load(open(f'{W}/glyph_match/p{pg:04d}.json'))['glyph_match']
        cols=[]
        for c in gm['columns']:
            ch=sorted(c['chars'],key=lambda x:(x['slot'],x['sub'] or ''))
            s=''.join((x['candidates'][0][0] if x['candidates'] else '？') for x in ch)
            if len(s)<2: cols.append((c['col'],s,None,0)); continue
            best=max(cands,key=lambda t: difflib.SequenceMatcher(None,s,t).ratio())
            r=difflib.SequenceMatcher(None,s,best).ratio()
            cols.append((c['col'],s,best,round(r,2)))
        res[pg]=cols
json.dump(res,open(sys.argv[1],'w'),ensure_ascii=False)
for pg,cols in res.items():
    print(pg)
    for c in cols: print('  ',c)
