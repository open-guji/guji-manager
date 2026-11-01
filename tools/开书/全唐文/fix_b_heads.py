# 按页内容挪 Kanripo 半叶头：卷 21–34 的 Kanripo 把 a/b 分界标晚了 2–3 行（a 面 10–11 行、b 面 6–7 行，我们的书每半叶 9 列），
# b 面页钉位因此整页错列（2026-11-01 pending-stats：册 08–11 约 5,300 格「列行对应不成立」）。
# 做法：对每个钉在 b 头上的页，拿本页各列（seed_admit 的字，不分放没放行）和逐列本比，在 ±6 行里找最像的起始行；
# 明显更好（平均相似度高 ≥0.15 且 ≥0.45）就把这个 b 头那一行挪到该处。只改本书语料，原 Kanripo 头名不变，钉位表不用改。
# 用法：python3 fix_b_heads.py <产物根> <逐列本> <page_pins.jsonl> 册 [册…] [--dry]
# 注意（2026-11-01 实跑）：
# - 只对 Kanripo 分界系统性出错的册跑（全唐文是卷20–34＝册08–11）。别的册零星挪 ±1 的没核实；册06 p142（双行小注页）被挪了 +6，看图是错的。
# - 跑前先查 pages.tsv 有没有越界的 pb（全唐文卷22/23 的 01a 被标在上一卷末，整个 a 面正文没进逐列本），先修那个。
# - 挪完的头要写回 book-text 的 pages.tsv（源数据），用 apply_pb_moves.py；用改后的 pages.tsv 重跑 make_grid_corpus.py 应与本脚本产出逐行一致。
import json,re,sys,difflib
prod,grid,pinsf,*rest=sys.argv[1:]
dry='--dry' in rest; vols=[v for v in rest if not v.startswith('--')]
cl=lambda s: re.sub(r'[^㐀-鿿\U00020000-\U0003ffff]','',s)
raw=open(grid,encoding='utf-8').read().split('\n')
def index():
    content=[];head_pos={}   # content[i]=(raw 行号, 净文本)；head_pos[头]=该头后第一条内容的 content 下标
    for ri,l in enumerate(raw):
        if l.startswith('#@ '): head_pos[l[3:].strip()]=len(content)
        elif l.strip(): content.append((ri,cl(l)))
    return content,head_pos
pins=[json.loads(l) for l in open(pinsf,encoding='utf-8') if l.strip()]
moves=[];stat={}
for v in vols:
    content,head_pos=index()
    for r in pins:
        if r['book']!=v or not re.search(r'NKFB_\d{4}-\d+b$',r['head']) or r['head'] not in head_pos: continue
        try: s=json.load(open(f"{prod}/{v}/seed_admit/p{int(r['page']):04d}.json",encoding='utf-8'))['seed_admit']
        except FileNotFoundError: continue
        cols=[''.join(x['char'] or '' for x in sorted(c['chars'],key=lambda x:str(x['slot']).zfill(4)) if not x.get('sub')) for c in s['columns']]
        cols=cols[:9]
        if sum(len(c)>=3 for c in cols)<3: continue
        L=head_pos[r['head']]
        def score(k):
            if L+k<0 or L+k+len(cols)>len(content): return -1
            rs=[difflib.SequenceMatcher(None,c,content[L+k+i][1]).ratio() for i,c in enumerate(cols) if len(c)>=3]
            return sum(rs)/len(rs)
        sc={k:score(k) for k in range(-6,7)}
        k=max(sc,key=sc.get)
        stat[(v,k if sc[k]-sc[0]>=0.15 and sc[k]>=0.45 else 0)]=stat.get((v,k if sc[k]-sc[0]>=0.15 and sc[k]>=0.45 else 0),0)+1
        hs=sorted(head_pos.values()); j=hs.index(L)
        lo=hs[j-1] if j else -1; hi=hs[j+1] if j+1<len(hs) else len(content)
        if k and sc[k]-sc[0]>=0.15 and sc[k]>=0.45 and lo<L+k<hi:   # 不越过前后两个头
            moves.append((r['head'],L+k,v,r['page'],k,round(sc[0],2),round(sc[k],2)))
    # 本册挪完再算下一册（下标会变）
    if not dry:
        for head,newL,*_ in [m for m in moves if m[2]==v]:
            hi=next(i for i,l in enumerate(raw) if l=='#@ '+head)
            line=raw.pop(hi)
            content,_hp=index()
            raw.insert(content[newL if newL<len(content) else -1][0],line)
        # 重算：pop 之后 content 下标不变（头不占 content），所以 newL 仍指向同一内容行
for m in moves: print(*m)
print('统计（册, 挪动行数）:',dict(sorted(stat.items(),key=str)))
if not dry:
    open(grid,'w',encoding='utf-8').write('\n'.join(raw))
    print('已写',grid,'挪了',len(moves),'个头')
