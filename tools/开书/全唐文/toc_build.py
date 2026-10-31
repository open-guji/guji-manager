# 目录页配篇题（第二步，含补短题）：读 toc_match.json 生成目录页参照段（#@ QTW_TOC_<册>_pNNNN）与页钉位行；卷首「欽定全唐文卷N目錄」、帝号行（高祖/太宗＋卷次）按图补，长题按图上字数跨列拆，MANUAL 里放人看图定的列。
# 用法：VOL=05 python3 toc_build.py <toc_corpus.txt> <toc_pins.jsonl> [toc_match.json]，再把两份分别追加进语料与 page_pins.jsonl
#
"""由 toc_match.json 生成目录页参照：每列＝本卷正文 Kanripo 里配上的篇题（跨列的长题按图上字数拆），
卷首「欽定全唐文卷N目錄」按图补。输出语料追加段与页钉位行。"""
import json,re,sys,difflib
from volcfg import *
m=json.load(open(sys.argv[3] if len(sys.argv)>3 else f'/tmp/claude/toc_match_{VOL}.json'))
CN='〇一二三四五六七八九十'
#: 识别全错、自动配不上的列，人看图定（Kanripo 正文里有同名篇题）
sec=[];pins=[];stat={'title':0,'split':0,'head':0,'skip':0}
for pg,cols in sorted(m.items(),key=lambda x:int(x[0])):
    pg=int(pg); lines=[]; pend=None
    for col,s,best,r in cols:
        if not s: continue
        if (pg,col) in MANUAL: lines.append(MANUAL[(pg,col)]); stat['head']+=1; continue
        if pend:
            lines.append(pend[:len(s)]); pend=pend[len(s):] or None; stat['split']+=1; continue
        if '目錄' in s or s.startswith('欽定'):
            lines.append(f'欽定全唐文卷{CN[JUAN[pg]]}目錄'); stat['head']+=1; continue
        if re.fullmatch(r'(高祖|太宗)[一二三四五六七八九十]?', s):
            lines.append(s); stat['head']+=1; continue
        t=(best or '').replace('<','').replace('>','')
        cov=sum(b.size for b in difflib.SequenceMatcher(None,s,t).get_matching_blocks())/max(1,len(t))
        if best is None or len(s)<=2 or (r<0.4 and cov<0.6 and not (len(t)==len(s) and r>=0.3)): lines.append(''); stat['skip']+=1; continue
        if len(t)>len(s)+2:
            lines.append(t[:len(s)]); pend=t[len(s):]; stat['split']+=1
        else: lines.append(t); stat['title']+=1
    head=f'QTW_TOC_{VOL}_p{pg:04d}'
    sec.append(f'#@ {head}\n'+''.join(l+'\n' for l in lines if l))
    pins.append({"book":VOL,"page":pg,"head":head})
open(sys.argv[1],'w',encoding='utf-8').write(''.join(sec))
open(sys.argv[2],'w').write(''.join(json.dumps(p)+'\n' for p in pins))
print(stat)
