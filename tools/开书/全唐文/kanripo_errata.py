"""全唐文 Kanripo 勘误层（2026-11-03 Sheldon 定：不直接改参照本，错处记在我们这边）。

`kanripo_errata.tsv` 每行一条：id、file（book-text 章文件）、page（书影册页列）、kind（缺字／多字／断行／半叶头…）、
old、new（原文片段，⏎＝换行，⟦pb:ID⟧＝半叶头所在行首）、basis（看图依据）。
make_grid_corpus 生成逐列语料前，把每个章文件连同半叶头标记拼成一段文字，逐条把 old 换成 new（old 必须恰好出现一次，
否则报错停下，免得 Kanripo 改版后悄悄失效），再拆回行与半叶头。book-text 本身不动。
"""
import csv,os,re
HERE=os.path.dirname(os.path.abspath(__file__))
MARK=re.compile(r'^⟦pb:([^⟧]+)⟧')
def load(path=None):
    path=path or os.path.join(HERE,'kanripo_errata.tsv')
    if not os.path.exists(path): return []
    return list(csv.DictReader(open(path,encoding='utf-8'),delimiter='\t'))
def apply(fn,lines,pbs,errata):
    """lines：章文件逐行；pbs：{行号(1起): pb id}。返回 (新 lines, 新 pbs, 用上的条目 id)。"""
    es=[e for e in errata if e['file']==fn]
    if not es: return lines,pbs,[]
    text='\n'.join((f'⟦pb:{pbs[i]}⟧' if i in pbs else '')+l for i,l in enumerate(lines,1))
    used=[]
    for e in es:
        old,new=e['old'].replace('⏎','\n'),e['new'].replace('⏎','\n')
        n=text.count(old)
        if n!=1: raise SystemExit(f"勘误 {e['id']}（{fn}）：old 出现 {n} 次，须恰好 1 次")
        text=text.replace(old,new); used.append(e['id'])
    out=[];np={}
    for i,l in enumerate(text.split('\n'),1):
        m=MARK.match(l)
        if m: np[i]=m.group(1); l=l[m.end():]
        out.append(l)
    return out,np,used
