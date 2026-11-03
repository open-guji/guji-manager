# 卷首卷名栏列补格位表行：每卷 01a 第 1 列「欽定全唐文卷N」（add_juan_header.py 补进语料的那行）在表里缺行时，
# row_segment 会把列下半的藏书印当字切满 22 格（09p7：10–21 格判遮挡进 O，22 格印泥认成「三」放行）。有表行时其余格是表空格，印泥记空。
# 格位按已跑产物里这一列实际认出卷名的格位定（卷名有抬头 -1 起的，不按字数硬套）：seed_admit 第 1 列放行字按序拼出卷名才补。
# 用法：python3 add_header_layout.py <格位表> <逐列语料> <page_pins.jsonl> <输出表> <册产物根>...（产物根下有 <册>/seed_admit/）
import json,sys,re,os
lay,grid,pins,out=sys.argv[1:5]; roots=sys.argv[5:]
rows=[json.loads(l) for l in open(lay,encoding='utf-8')]
have={(r['vol'],r['page'],r['col']) for r in rows}
G=open(grid,encoding='utf-8').read().split('\n'); first={}
for i,l in enumerate(G):
    if l.startswith('#@ '): first[l[3:].strip()]=G[i+1] if i+1<len(G) else ''
st={'补行':0,'已有':0,'对不上':0,'无产物':0}; add=[]
for p in map(json.loads,open(pins)):
    v,pg,h=p['book'],p['page'],p['head']
    if not h.endswith('-01a'): continue
    if (v,pg,1) in have: st['已有']+=1; continue
    hdr=re.sub(r'[^一-鿿]','',first.get(h,''))
    if not hdr.startswith('欽定全唐文卷'): continue
    f=next((os.path.join(r,v,'seed_admit',f'p{pg:04d}.json') for r in roots if os.path.exists(os.path.join(r,v,'seed_admit',f'p{pg:04d}.json'))),None)
    if not f: st['无产物']+=1; continue
    col=next((c for c in json.load(open(f))['seed_admit']['columns'] if c.get('col',None) in (1,None)),None)
    chars=sorted([c for c in col['chars'] if not c.get('sub')],key=lambda c:c['slot']) if col else []
    # 找连续一段放行字＝卷名（容许个别字没放行：按位置配，放行的都要对上，且至少一半放行）
    ok=None
    for k in range(len(chars)-len(hdr)+1):
        seg=chars[k:k+len(hdr)]
        adm=[(c,ch) for c,ch in zip(seg,hdr) if c.get('admit')]
        if len(adm)*2>=len(hdr) and all(c.get('char')==ch for c,ch in adm) and seg[0]['slot']<=1:
            ok=[c['slot'] for c in seg]; break
    if not ok: st['对不上']+=1; print('对不上',v,pg,hdr,''.join(c.get('char') or '·' for c in chars)); continue
    add.append({"vol":v,"page":pg,"col":1,"slots":ok,"notes":[],"half":[],"raised":1 if ok[0]<0 else 0}); st['补行']+=1
with open(out,'w',encoding='utf-8') as fo:
    for r in rows+add: fo.write(json.dumps(r,ensure_ascii=False)+'\n')
print(st); [print(' ',r['vol'],r['page'],r['slots']) for r in add]
