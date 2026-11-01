# 每卷第 01a 半叶的首列是「欽定全唐文卷N…」卷名栏，Kanripo 没录，逐列本整页少一行 → 该页所有列都错 1 位（2026-11-01 册05–15 共 43 页、约 435 个 S 格）。
# 做法：在每个 `#@ …NKFB_NNNN-01a` 头后插一行「欽定全唐文卷<中文数>」占位列。已有则不重复插。只改逐列本。
# 用法：python3 add_juan_header.py <逐列本> <输出> [最小卷号，缺省 1]（册04 已定稿，卷3–6 不动，全唐文传 7）
import re,sys
src,out=sys.argv[1:3]
min_juan=int(sys.argv[3]) if len(sys.argv)>3 else 1
D='零一二三四五六七八九'
def cn(n):
    if n>=1000: return '一千'+(cn(n%1000) if n%1000 else '')
    if n<10: return D[n]
    if n<20: return '十'+(D[n%10] if n%10 else '')
    if n<100: return D[n//10]+'十'+(D[n%10] if n%10 else '')
    h=D[n//100]+'百'; r=n%100
    if r==0: return h
    if r<10: return h+'零'+D[r]
    return h+(D[r//10]+'十'+(D[r%10] if r%10 else '') if r>=20 else '一十'+(D[r%10] if r%10 else ''))
lines=open(src,encoding='utf-8').read().split('\n')
res=[];n=0;i=0
while i<len(lines):
    l=lines[i];res.append(l)
    m=re.match(r'#@ KR4h0168_NKFB_(\d{4})-01a$',l.strip())
    if m and int(m.group(1))>=min_juan:
        h='欽定全唐文卷'+cn(int(m.group(1)))
        if not (i+1<len(lines) and lines[i+1]==h): res.append(h);n+=1
    i+=1
open(out,'w',encoding='utf-8').write('\n'.join(res))
print('插入',n,'行')
