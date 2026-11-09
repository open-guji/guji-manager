#!/usr/bin/env python3
"""A/B 判字 → llm_queue import 用答案行。放行＝两路 high、同字、字在候选内。
用法：to_answers.py SEGDIR OUTDIR 前缀 > answers.jsonl（同时写 OUTDIR/release_report.tsv）
行＝导出行(group,ver,l,r,members,cells)＋char/conf/why；未放行的格不输出。"""
import json,sys,glob,os
seg,out,pre=sys.argv[1:4]
rep=[]
for f in sorted(glob.glob(f'{seg}/{pre}*.cells.json')):
    name=os.path.basename(f).split('.')[0]
    try:A={c['n']:c for c in json.load(open(f'{out}/{name}.A.json'))['cells']};B={c['n']:c for c in json.load(open(f'{out}/{name}.B.json'))['cells']}
    except Exception as e: print('skip',name,e,file=sys.stderr);continue
    for c in json.load(open(f)):
        a,b=A.get(c['n']),B.get(c['n']);st='abstain'
        if a and b and a['char']==b['char'] and a['conf']==b['conf']=='high' and a['char'] in c['cands']:
            st='release'
            print(json.dumps(dict(group=c['group'],ver=c['ver'],l=c['l'],r=c['r'],members=c['cands'],cells=[c['cell']],char=a['char'],conf='high',why=('A:'+a['why']+' | B:'+b['why'])[:300]),ensure_ascii=False))
        rep.append((name,c['cell'],c['group'],c['machine'],a and a['char'],a and a['conf'],b and b['char'],b and b['conf'],st))
open(f'{out}/release_report_{pre}.tsv','w').write('seg\tcell\tgroup\tmachine\tA\tAc\tB\tBc\tstatus\n'+'\n'.join('\t'.join(str(x) for x in r) for r in rep)+'\n')
