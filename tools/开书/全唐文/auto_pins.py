# 自动页钉位：每页 glyph_match 首选串与本册各卷 Kanripo 半叶比三字组重合，取有把握的页定每卷卷首页，
# 再按叶号推满（页 = 卷首页 + 2×(叶−1) + b）；NFKB_QTW 头只认直接配上的。没钉上的有字页按位置判目录页。
# 用法：VOL=06 python3 auto_pins.py <pins_out.jsonl> <cfg_out.json>
import json,re,sys,glob,collections,os
from volcfg import VOL,W,D,load_txt
yaml=open(os.path.expanduser(f'~/.guji-data/main/995ejelvk0/books/{VOL}.yaml'),encoding='utf-8').read()
j0,j1=map(int,re.search(r'^title:.*卷(\d+)[–-](\d+)',yaml,re.M).group(1,2))
txt,order=load_txt()
clean=lambda s: re.sub(r'[^㐀-鿿\U00020000-\U0003ffff]','',s)
def head_juan(h):
    m=re.match(r'KR4h0168_NKFB_(\d{4})-(\d+)([ab])$',h); return (int(m.group(1)),int(m.group(2)),m.group(3)) if m else None
# 候选半叶：本册各卷的标准头，加夹在其间（及最后一卷之后紧跟）的 NFKB 头
cand=[];inside=False
for h in order:
    hj=head_juan(h)
    if hj: inside = j0<=hj[0]<=j1
    elif h.startswith('NFKB_QTW') and not inside: continue
    if inside and (hj or h.startswith('NFKB_QTW')): cand.append(h)
tri=lambda s:{s[i:i+3] for i in range(len(s)-2)}
HT={h:tri(clean(''.join(txt[h]))) for h in cand}
pages=sorted(int(f[-9:-5]) for f in glob.glob(f'{W}/glyph_match/p*.json'))
ptxt={}
for p in pages:
    gm=json.load(open(f'{W}/glyph_match/p{p:04d}.json'))['glyph_match']
    s=''
    for c in gm['columns']:
        ch=sorted(c['chars'],key=lambda x:(x['slot'],x.get('sub') or ''))
        s+=''.join(x['candidates'][0][0] for x in ch if x['candidates'])
    ptxt[p]=s
best={}
for p in pages:
    t=tri(ptxt[p])
    if len(t)<6: continue
    sc=sorted(((len(t&HT[h])/len(t),h) for h in cand if HT[h]),reverse=True)
    if sc and sc[0][0]>=0.15 and (len(sc)==1 or sc[0][0]>=1.5*sc[1][0]): best[p]=sc[0]
starts=collections.defaultdict(collections.Counter)
for p,(s,h) in best.items():
    hj=head_juan(h)
    if hj: starts[hj[0]][p-2*(hj[1]-1)-(hj[2]=='b')]+=1
START={j:c.most_common(1)[0][0] for j,c in starts.items()}
print('卷首页',{j:(START[j],dict(starts[j].most_common(3))) for j in sorted(START)})
pins={}
for h in cand:
    hj=head_juan(h)
    if hj and hj[0] in START:
        p=START[hj[0]]+2*(hj[1]-1)+(hj[2]=='b')
        if p in ptxt: pins[p]=h
for p,(s,h) in best.items():
    if h.startswith('NFKB') and p not in pins: pins[p]=h
dis=[(p,best[p][1],pins.get(p)) for p in best if pins.get(p)!=best[p][1]]
print('直接配上',len(best),'与推算不符',len(dis),dis[:12])
# 每卷正文页范围＝[卷首页, 下一卷首页) 内钉上的页；之间没钉上、有字的页算目录页（归下一卷）
js=sorted(START); TOC={};BODY={}
prev_end=0
for k,j in enumerate(js):
    body=[p for p,h in pins.items() if (head_juan(h) or (0,))[0]==j or (h.startswith('NFKB') and START[j]<=p<(START[js[k+1]] if k+1<len(js) else 10**6))]
    bmin,bmax=min(body),max(body)
    TOC[j]=[p for p in range(prev_end+1,bmin) if p in ptxt and len(clean(ptxt[p]))>=4 and p not in pins]
    BODY[j]=[bmin,bmax+1]; prev_end=bmax
    # 卷尾短页/空白页：bmax 之后、下一卷目录之前
nopin=[p for p in pages if p not in pins and not any(p in v for v in TOC.values())]
print('目录页',TOC); print('正文',BODY)
print('没钉也不算目录的页（空白或缺半叶）',[(p,len(clean(ptxt[p]))) for p in nopin])
with open(sys.argv[1],'w') as f:
    for p in sorted(pins): f.write(json.dumps({"book":VOL,"page":p,"head":pins[p]})+'\n')
json.dump({'TOC':TOC,'BODY':BODY,'START':START},open(sys.argv[2],'w'))
