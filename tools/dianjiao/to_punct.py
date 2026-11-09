#!/usr/bin/env python3
"""A 路 text(含 【卷】【題】、标点、⟦类:专名⟧) → book-text 的 punct.json / entity.json 草稿。
字与格的对应：用 SEG/<段>.idx.json（全册格序、anchor、机器字；疑问格以 A 所判字为准，仅用于核对）。
用法：to_punct.py SEGDIR OUTDIR 前缀 BOOK_ID VOL > 写 OUTDIR/<VOL>.punct.draft.json / .entity.draft.json
标记：卷首→ '#'(heading,before)，篇题→ '##'(heading,before)，段间→ '\\n\\n'(break,after 上一字)，标点→ point，《》→ point before/after；
专名 类型 人 people 地 place 官 office 朝 dynasty 号/號 reign，target 先全记 new_candidate（挂库另行匹配）。"""
import json,sys,glob,os,re
seg,out,pre,book,vol=sys.argv[1:6]
OPEN=set('《「『');CLOSE=set('》」』');POINT=set('，。、；：？！')
TYPE={'人':'people','地':'place','官':'office','朝':'dynasty','号':'reign','號':'reign'}
TAG=re.compile(r'⟦(人|地|官|朝|号|號):([^⟦⟧\n]+)⟧')
puncts=[];ents=[];bad=[]
eid=0
for f in sorted(glob.glob(f'{seg}/{pre}*.idx.json')):
    name=os.path.basename(f).split('.')[0]
    try:A=json.load(open(f'{out}/{name}.A.fixed.json' if os.path.exists(f'{out}/{name}.A.fixed.json') else f'{out}/{name}.A.json'))
    except Exception as e: bad.append((name,'noA'));continue
    idx=json.load(open(f))          # [(g,anchor,machine_char)]
    cells={c['n']:c['char'] for c in A['cells']}
    ptr=0;pending_head=None;prev_line_end=None
    lines=[l for l in re.sub(r'⟨p\d+⟩','',A['text']).split('\n') if l.strip()]
    chars=[]    # (g,anchor,ch) per output char in order
    for li,line in enumerate(lines):
        head=None
        m=re.match(r'【(卷|題|作者|注)】',line)
        if m: head=m.group(1);line=line[m.end():]
        i=0;first=True;spans=[];pre_marks=[];
        # 先剥标签得到纯文字与标点序列
        buf=[];pos=0
        for tm in TAG.finditer(line): pass
        toks=[]   # (kind,val) kind: c char / p mark
        j=0
        while j<len(line):
            t=TAG.match(line,j)
            if t:
                start=len([x for x in toks if x[0]=='c']);
                for ch in t.group(2):
                    toks.append(('c',ch))
                spans.append((TYPE[t.group(1)],start,start+len(t.group(2)),t.group(2)))
                j=t.end();continue
            ch=line[j]
            toks.append(('p' if ch in POINT or ch in OPEN or ch in CLOSE else 'c',ch));j+=1
        # 映射到格
        ci=0;cell_of=[]
        for k,ch in toks:
            if k=='c':
                if ptr>=len(idx): bad.append((name,'overrun'));break
                g,anc,mch=idx[ptr];ptr+=1;cell_of.append((g,anc,mch))  # 第3项＝现行文本字（机器字）；所判字改进文本要走裁定库重放，不在此线
        c_i=0
        if head in('卷','題') and cell_of:
            g,anc,_=cell_of[0]
            puncts.append(dict(mark='#' if head=='卷' else '##',kind='heading',pos='before',char_offset=g,anchor=anc,source='claude:A31-dianjiao'))
        if prev_line_end and head is None and cell_of:
            pg,panc,pch=prev_line_end
            puncts.append(dict(mark='\n\n',kind='break',pos='after',char_offset=pg,pre_char=pch,anchor=panc,source='claude:A31-dianjiao'))
        elif prev_line_end and head is not None:
            pg,panc,pch=prev_line_end
            puncts.append(dict(mark='\n\n',kind='break',pos='after',char_offset=pg,pre_char=pch,anchor=panc,source='claude:A31-dianjiao'))
        ci=0
        for k,ch in toks:
            if k=='c': ci+=1;continue
            if ch in OPEN:
                if ci<len(cell_of):
                    g,anc,c0=cell_of[ci]
                    puncts.append(dict(mark=ch,kind='point',pos='before',char_offset=g,pre_char=c0,anchor=anc,source='claude:A31-dianjiao'))
            elif ci>0:
                g,anc,c0=cell_of[ci-1]
                puncts.append(dict(mark=ch,kind='point',pos='after',char_offset=g,pre_char=c0,anchor=anc,source='claude:A31-dianjiao'))
        for ty,s,e,txt in spans:
            if e<=len(cell_of):
                eid+=1;g0,a0,_=cell_of[s];g1,a1,_=cell_of[e-1];txt=''.join(x[2] for x in cell_of[s:e])
                ents.append(dict(id=f'e{eid:05d}',type=ty,text=txt,anchor=dict(start=a0,end=a1),span=dict(start_offset=g0,end_offset=g1+1),target=dict(status='new_candidate'),source='claude:A31-dianjiao'))
        if cell_of: prev_line_end=cell_of[-1]
    prev_line_end=None if False else prev_line_end
puncts.sort(key=lambda p:(p['char_offset'],0 if p['pos']=='before' else 1))
base=dict(book_id=book,volume=int(vol))
json.dump(dict(**{'$schema':'https://open-guji.org/schema/punct/v0.2.json','version':'0.1.0'},**base,punctuations=puncts),open(f'{out}/{vol}.{pre}.punct.draft.json','w'),ensure_ascii=False)
json.dump(dict(**{'$schema':'https://open-guji.org/schema/entity/v0.2.json','version':'0.1.0'},**base,entities=ents),open(f'{out}/{vol}.{pre}.entity.draft.json','w'),ensure_ascii=False)
print('puncts',len(puncts),'ents',len(ents),'bad',bad)
