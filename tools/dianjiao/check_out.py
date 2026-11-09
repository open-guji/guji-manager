#!/usr/bin/env python3
"""校验点校输出：把输出还原成汉字流，须等于 base 里非疑问格的字，疑问格处等于所判字且在候选内。
用法：check_out.py SEG_DIR NAME RUN   （读 SEG_DIR/NAME.txt、.cells.json、.base.txt 与 SEG_DIR/../out/NAME.RUN.json）"""
import json,re,sys,os
PUNC=set('，。、；：？！「」『』《》·　⏎\n ')
TAG=re.compile(r'⟦(人|地|官|朝|号|號|书):([^⟦⟧\n]+)⟧')
def run(segdir,name,tag):
    cells=json.load(open(f'{segdir}/{name}.cells.json'));base=open(f'{segdir}/{name}.base.txt').read()
    out=json.load(open(f'{os.environ.get("OUTDIR",segdir+"/../out")}/{name}.{tag}.json'))
    pick={c['n']:c for c in out['cells']}
    problems=[]
    # 期望字流：base 中疑问格位置换成所判字
    inp=open(f'{segdir}/{name}.txt').read()
    pos=[];i=0
    exp=list(base)
    # 找疑问格在 base 的位置：按 〔n:..〕 出现顺序对应输入流中的序号
    stream=re.sub(r'⟨p\d+⟩','',''.join(l+'\n' for l in inp.split('\n') if not l.startswith(('◁','▷'))))
    k=0;idx=[]
    for m in re.finditer(r'〔(\d+):[^〕]*〕|[^\n　⏎]',stream):
        if m.group(1): idx.append((int(m.group(1)),k))
        k+=1
    for n,k0 in idx:
        c=pick.get(n)
        if not c: problems.append(f'缺判 n={n}');continue
        cand=[x for x in next(x for x in cells if x['n']==n)['cands']]
        if c['char'] not in cand and c['char']!='□': problems.append(f'n={n} 判 {c["char"]} 不在候选')
        exp[k0]=c['char']
    exp=''.join(exp)
    if 'text' in out:
        t=TAG.sub(lambda m:m.group(2),out['text'])
        t=re.sub(r'【(卷|題|作者|注)】','',t);t=re.sub(r'⟨p\d+⟩','',t)
        s=''.join(ch for ch in t if ch not in PUNC)
        if s!=exp:
            j=next((j for j,(x,y) in enumerate(zip(s,exp)) if x!=y),min(len(s),len(exp)))
            problems.append(f'汉字流不一致 out={len(s)} exp={len(exp)} at={j} {s[max(0,j-6):j+6]!r}|{exp[max(0,j-6):j+6]!r}')
        if re.sub(r'[^⟦⟧]','',TAG.sub('',out['text'])): problems.append('标签不成对')
    return problems
if __name__=='__main__':
    p=run(sys.argv[1],sys.argv[2],sys.argv[3]);print('OK' if not p else '\n'.join(p));sys.exit(1 if p else 0)
