#!/usr/bin/env python3
"""A 路 text 字流与期望字流(base＋所判字)不符时的确定性修复：只做单字替换，增删另记。
用法：OUTDIR=... repair.py SEGDIR OUTDIR 名 → 写 OUTDIR/<名>.A.fixed.json（text 已修）并打印改动
期望字流＝机器字，疑问格处换成 A 所判字（同 check_out.py）。"""
import json,re,sys,os,difflib
seg,out,name=sys.argv[1:4]
os.environ['OUTDIR']=out
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import check_out
A=json.load(open(f'{out}/{name}.A.json'))
cells=json.load(open(f'{seg}/{name}.cells.json'));base=open(f'{seg}/{name}.base.txt').read()
inp=open(f'{seg}/{name}.txt').read()
stream=re.sub(r'⟨p\d+⟩','',''.join(l+'\n' for l in inp.split('\n') if not l.startswith(('◁','▷'))))
exp=list(base);k=0
pick={c['n']:c['char'] for c in A['cells']}
for m in re.finditer(r'〔(\d+):[^〕]*〕|[^\n　⏎]',stream):
    if m.group(1): exp[k]=pick.get(int(m.group(1)),exp[k])
    k+=1
exp=''.join(exp)
text=re.sub(r'⟨p\d+⟩','',A['text'])
PRE=re.compile(r'【(?:卷|題|作者|注)】|⟦(?:人|地|官|朝|号|號):|⟧|[，。、；：？！「」『』《》·\n]')
items=[];pos=0
for m in PRE.finditer(text):
    for ch in text[pos:m.start()]:items.append(('c',ch))
    items.append(('n',m.group(0)));pos=m.end()
for ch in text[pos:]:items.append(('c',ch))
out_chars=''.join(v for t,v in items if t=='c')
sm=difflib.SequenceMatcher(None,out_chars,exp,autojunk=False)
log=[];new=[];ci=0;cmap={}
ops=sm.get_opcodes()
repl={};drop=set();ins={}
for tag,i1,i2,j1,j2 in ops:
    if tag=='equal':continue
    log.append((tag,out_chars[i1:i2],exp[j1:j2],out_chars[max(0,i1-4):i1]))
    if tag=='replace' and i2-i1==j2-j1:
        for d in range(i2-i1):repl[i1+d]=exp[j1+d]
    else:
        for d in range(i1,i2):drop.add(d)
        if j2>j1:ins.setdefault(i1,'');ins[i1]+=exp[j1:j2]
ci=0;res=[]
for t,v in items:
    if t=='n':res.append(v);continue
    if ci in ins:res.append(ins.pop(ci))
    if ci not in drop:res.append(repl.get(ci,v))
    ci+=1
if ci in ins:res.append(ins.pop(ci))
A['text']=''.join(res);A['repair_log']=log
json.dump(A,open(f'{out}/{name}.A.fixed.json','w'),ensure_ascii=False)
print(name,'改动',len(log),log)
