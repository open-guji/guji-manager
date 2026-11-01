# 批 1 阶段 B（一册）：自动钉位 → 目录页配篇题 → 格位表 → 改册 yaml。之后跑 run_vol.sh。
# 用法：python3 stageB.py <册>；可重跑（先删本册旧行）
import sys,os,json,subprocess,re
V=sys.argv[1]; os.environ['VOL']=V
S='/home/user/qtw-scripts/v'; B='/home/user/batch1'
D=os.path.expanduser('~/.guji-data/main/995ejelvk0')
def run(*a):
    r=subprocess.run(['python3',*a],cwd=S,capture_output=True,text=True,env=os.environ)
    print(r.stdout[-1500:],r.stderr[-1500:]); r.check_returncode()
run('auto_pins.py',f'{B}/pins_{V}.jsonl',f'{B}/cfg_{V}.json')
# 钉位表：去掉本册旧行，加正文钉位
pp=f'{D}/corpus/page_pins.jsonl'
rows=[l for l in open(pp) if json.loads(l)['book']!=V]
rows+=open(f'{B}/pins_{V}.jsonl').readlines()
open(pp,'w').write(''.join(rows))
# 目录页
run('toc_match.py',f'{B}/tocm_{V}.json')
run('toc_build.py',f'{B}/toc_{V}.txt',f'{B}/tocpins_{V}.jsonl',f'{B}/tocm_{V}.json')
gp=f'{D}/corpus/qtw_kanripo_grid.txt'
g=open(gp,encoding='utf-8').read()
g=re.sub(rf'#@ QTW_TOC_{V}_p\d+\n(?:(?!#@ ).*\n)*','',g)
t=open(f'{B}/toc_{V}.txt',encoding='utf-8').read()
t=re.sub(r'#@ QTW_TOC_\S+\n(?=#@ |$)','',t)            # 空段（空白页）不要
heads=set(re.findall(r'#@ (QTW_TOC_\S+)',t))
open(gp,'w',encoding='utf-8').write(g.rstrip('\n')+'\n'+t)
tp=[l for l in open(f'{B}/tocpins_{V}.jsonl') if json.loads(l)['head'] in heads]
open(pp,'a').write(''.join(tp))
print('目录页参照',len(heads))
# 格位表
run('make_qtw_layout.py',f'{B}/layout_{V}.jsonl')
lp=f'{D}/corpus/qtw_layout.jsonl'
rows=[l for l in open(lp) if json.loads(l)['vol']!=V]+open(f'{B}/layout_{V}.jsonl').readlines()
open(lp,'w').write(''.join(rows))
# 册 yaml
yp=f'{D}/books/{V}.yaml'; y=open(yp,encoding='utf-8').read()
if 'layout_prior' not in y:
    y=y.replace('params:\n','params:\n  row_segment:\n    layout_prior: corpus/qtw_layout.jsonl\n  align_ref:\n    page_pins: page_pins.jsonl\n',1)
    open(yp,'w',encoding='utf-8').write(y)
print('B done',V)
